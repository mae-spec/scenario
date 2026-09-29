"""Application web « Comparateur de scénarios » — 100 % locale.

Aucune ressource externe (CDN, polices, statistiques) n'est chargée et l'application
n'effectue aucune requête sortante : les scénarios restent sur le NAS.
"""
from __future__ import annotations

import base64
import binascii
import hmac
import io
import json
import os
import threading
import time
import zipfile
from collections import OrderedDict
from pathlib import Path
from urllib.parse import quote

import anyio
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, Response
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import __version__, offline
from .compare.engine import compare
from .compare.text import Options
from .config import Settings
from .report import render_csv, render_html
from .screenplay import PARSER_VERSION, SUPPORTED, ParseError, parse_file
from .screenplay.export import to_fountain
from .store import NotFound, Store

STATIC_DIR = Path(__file__).parent / "static"

CSP = ("default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; connect-src 'self'; "
       "font-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
REPORT_CSP = "default-src 'none'; style-src 'unsafe-inline'; img-src data:; frame-ancestors 'none'"


class ProjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=5000)


class ProjectPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)


class VersionPatch(BaseModel):
    label: str | None = Field(default=None, max_length=200)
    notes: str | None = Field(default=None, max_length=10000)
    doc_date: str | None = Field(default=None, max_length=50)
    move: str | None = Field(default=None, pattern="^(up|down)$")


class CompareCache:
    def __init__(self, size: int = 24):
        self.size = size
        self.data: OrderedDict = OrderedDict()
        self.lock = threading.Lock()

    def get(self, key):
        with self.lock:
            if key in self.data:
                self.data.move_to_end(key)
                return self.data[key]
        return None

    def put(self, key, value):
        with self.lock:
            self.data[key] = value
            self.data.move_to_end(key)
            while len(self.data) > self.size:
                self.data.popitem(last=False)


def _opts(ignore_case: bool = False, ignore_punct: bool = False, normalize_typo: bool = True) -> Options:
    return Options(ignore_case=ignore_case, ignore_punct=ignore_punct, normalize_typo=normalize_typo)


def _content_disposition(filename: str) -> str:
    ascii_name = "".join(c if c.isascii() and c.isprintable() and c not in '"\\;' else "_" for c in filename)
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename)}"


def _slug(s: str) -> str:
    keep = "".join(c if c.isalnum() or c in "-_" else "-" for c in s.strip())
    return "-".join(p for p in keep.split("-") if p)[:60] or "scenario"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    store = Store(settings.data_dir)
    cache = CompareCache()
    max_bytes = settings.max_upload_mb * 1024 * 1024

    # Pas de /docs ni /redoc : ils chargeraient Swagger depuis un CDN.
    app = FastAPI(title="Comparateur de scénarios", docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(GZipMiddleware, minimum_size=2048)
    app.state.store = store
    app.state.settings = settings

    expected_auth = None
    if settings.password:
        expected_auth = base64.b64encode(f"{settings.user}:{settings.password}".encode()).decode()

    @app.middleware("http")
    async def security(request: Request, call_next):
        if expected_auth and request.url.path != "/api/health":
            header = request.headers.get("authorization", "")
            ok = False
            if header.lower().startswith("basic "):
                try:
                    given = header[6:].strip()
                    base64.b64decode(given, validate=True)
                    ok = hmac.compare_digest(given.encode(), expected_auth.encode())
                except (binascii.Error, ValueError):
                    ok = False
            if not ok:
                return PlainTextResponse("Authentification requise", status_code=401,
                                         headers={"WWW-Authenticate": 'Basic realm="Scenario", charset="UTF-8"'})
        response = await call_next(request)
        response.headers.setdefault("Content-Security-Policy", CSP)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        if request.url.path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
        return response

    @app.exception_handler(NotFound)
    async def not_found(_: Request, exc: NotFound):
        return JSONResponse({"detail": str(exc)}, status_code=404)

    @app.exception_handler(ParseError)
    async def parse_error(_: Request, exc: ParseError):
        return JSONResponse({"detail": str(exc)}, status_code=422)

    async def read_upload(f: UploadFile) -> bytes:
        data = await f.read(max_bytes + 1)
        if len(data) > max_bytes:
            raise HTTPException(413, f"Fichier trop volumineux (max {settings.max_upload_mb} Mo).")
        if not data:
            raise HTTPException(400, "Fichier vide.")
        return data

    def run_compare(a_id: int, b_id: int, opts: Options) -> tuple[dict, dict, dict]:
        va, vb = store.get_version(a_id), store.get_version(b_id)
        key = (a_id, va["sha256"], b_id, vb["sha256"], PARSER_VERSION, opts.key)
        result = cache.get(key)
        if result is None:
            result = compare(store.screenplay(a_id), store.screenplay(b_id), opts)
            cache.put(key, result)
        return result, va, vb

    # -- Général ------------------------------------------------------------
    @app.get("/api/health")
    def health():
        return {"status": "ok", "version": __version__}

    @app.get("/api/info")
    def info():
        return {"version": __version__, "parser_version": PARSER_VERSION, "formats": SUPPORTED,
                "max_upload_mb": settings.max_upload_mb, "auth": bool(settings.password)}

    # -- Projets ------------------------------------------------------------
    @app.get("/api/projects")
    def list_projects():
        return store.list_projects()

    @app.post("/api/projects", status_code=201)
    def create_project(body: ProjectIn):
        return store.create_project(body.name, body.description)

    @app.get("/api/projects/{pid}")
    def get_project(pid: int):
        return {**store.get_project(pid), "versions": store.list_versions(pid)}

    @app.patch("/api/projects/{pid}")
    def patch_project(pid: int, body: ProjectPatch):
        return store.update_project(pid, body.name, body.description)

    @app.delete("/api/projects/{pid}", status_code=204)
    def delete_project(pid: int):
        store.delete_project(pid)
        return Response(status_code=204)

    @app.get("/api/projects/{pid}/timeline")
    def timeline(pid: int, ignore_case: bool = False, ignore_punct: bool = False, normalize_typo: bool = True):
        versions = store.list_versions(pid)
        opts = _opts(ignore_case, ignore_punct, normalize_typo)
        steps = []
        for va, vb in zip(versions, versions[1:]):
            try:
                result, _, _ = run_compare(va["id"], vb["id"], opts)
            except ParseError as exc:
                steps.append({"a": va["id"], "b": vb["id"], "error": str(exc)})
                continue
            steps.append({"a": va["id"], "b": vb["id"], "summary": result["summary"], "renames": result["renames"]})
        names: dict[str, list] = {}
        for k, v in enumerate(versions):
            for c in v["stats"].get("characters", []):
                names.setdefault(c["name"], [None] * len(versions))[k] = {"lines": c["lines"], "words": c["words"]}
        characters = sorted(
            ({"name": n, "values": vals} for n, vals in names.items()),
            key=lambda c: -sum((x or {}).get("lines", 0) for x in c["values"]),
        )
        return {"versions": versions, "steps": steps, "characters": characters}

    @app.get("/api/projects/{pid}/archive")
    def archive(pid: int):
        project = store.get_project(pid)
        versions = store.list_versions(pid)
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("projet.json", json.dumps({"project": project, "versions": versions}, ensure_ascii=False,
                                                 indent=2))
            for k, v in enumerate(versions, start=1):
                name, path = store.original(v["id"])
                if path.exists():
                    z.write(path, f"{k:02d} - {_slug(v['label'])} - {name}")
        return Response(buf.getvalue(), media_type="application/zip", headers={
            "Content-Disposition": _content_disposition(f"{_slug(project['name'])}-archive.zip")})

    # -- Versions -----------------------------------------------------------
    @app.post("/api/projects/{pid}/versions", status_code=201)
    async def upload_version(pid: int, file: UploadFile = File(...), label: str = Form(""),
                             notes: str = Form(""), doc_date: str = Form(""), allow_duplicate: bool = Form(False)):
        store.get_project(pid)
        data = await read_upload(file)
        if not allow_duplicate:
            dup = store.find_duplicate(pid, data)
            if dup:
                raise HTTPException(409, f"Ce fichier est identique à la version « {dup['label']} ».")
        return await anyio.to_thread.run_sync(
            lambda: store.add_version(pid, file.filename or "document.txt", data, label[:200], notes[:10000],
                                      doc_date[:50]))

    @app.get("/api/versions/{vid}")
    def get_version(vid: int):
        v = store.get_version(vid)
        sp = store.screenplay(vid)
        return {**v, "screenplay": sp.to_dict()}

    @app.patch("/api/versions/{vid}")
    def patch_version(vid: int, body: VersionPatch):
        return store.update_version(vid, **body.model_dump())

    @app.delete("/api/versions/{vid}", status_code=204)
    def delete_version(vid: int):
        store.delete_version(vid)
        return Response(status_code=204)

    @app.post("/api/versions/{vid}/reparse")
    def reparse(vid: int):
        store.reparse(vid)
        return store.get_version(vid)

    @app.get("/api/versions/{vid}/original")
    def original(vid: int):
        name, path = store.original(vid)
        if not path.exists():
            raise HTTPException(404, "Fichier original manquant.")
        return FileResponse(path, media_type="application/octet-stream",
                            headers={"Content-Disposition": _content_disposition(name)})

    @app.get("/api/versions/{vid}/fountain")
    def fountain(vid: int):
        v = store.get_version(vid)
        text = to_fountain(store.screenplay(vid))
        return Response(text, media_type="text/plain; charset=utf-8", headers={
            "Content-Disposition": _content_disposition(f"{_slug(v['label'])}.fountain")})

    # -- Comparaison --------------------------------------------------------
    @app.get("/api/compare")
    def compare_versions(a: int, b: int, ignore_case: bool = False, ignore_punct: bool = False,
                         normalize_typo: bool = True):
        t0 = time.perf_counter()
        result, va, vb = run_compare(a, b, _opts(ignore_case, ignore_punct, normalize_typo))
        return {**result, "a": va, "b": vb, "elapsed_ms": round((time.perf_counter() - t0) * 1000)}

    def _export(result: dict, title_a: str, title_b: str, project: str, fmt: str, include_unchanged: bool):
        base = f"comparaison-{_slug(title_a)}-vs-{_slug(title_b)}"
        if fmt == "csv":
            return Response(render_csv(result), media_type="text/csv; charset=utf-8",
                            headers={"Content-Disposition": _content_disposition(base + ".csv")})
        if fmt == "json":
            return Response(json.dumps(result, ensure_ascii=False, indent=1), media_type="application/json",
                            headers={"Content-Disposition": _content_disposition(base + ".json")})
        html = render_html(result, title_a, title_b, project, include_unchanged)
        return Response(html, media_type="text/html; charset=utf-8", headers={
            "Content-Disposition": _content_disposition(base + ".html"), "Content-Security-Policy": REPORT_CSP})

    @app.get("/api/compare/export")
    def export(a: int, b: int, format: str = "html", include_unchanged: bool = False, ignore_case: bool = False,
               ignore_punct: bool = False, normalize_typo: bool = True):
        if format not in ("html", "csv", "json"):
            raise HTTPException(400, "Format d'export inconnu.")
        result, va, vb = run_compare(a, b, _opts(ignore_case, ignore_punct, normalize_typo))
        project = store.get_project(vb["project_id"])["name"] if va["project_id"] == vb["project_id"] else ""
        return _export(result, va["label"], vb["label"], project, format, include_unchanged)

    @app.post("/api/quick-compare")
    async def quick_compare(file_a: UploadFile = File(...), file_b: UploadFile = File(...),
                            ignore_case: bool = Form(False), ignore_punct: bool = Form(False),
                            normalize_typo: bool = Form(True), format: str = Form("json"),
                            include_unchanged: bool = Form(False)):
        da, db = await read_upload(file_a), await read_upload(file_b)
        opts = _opts(ignore_case, ignore_punct, normalize_typo)

        def work():
            spa = parse_file(file_a.filename or "a.txt", da)
            spb = parse_file(file_b.filename or "b.txt", db)
            return compare(spa, spb, opts)

        result = await anyio.to_thread.run_sync(work)
        na, nb = file_a.filename or "A", file_b.filename or "B"
        if format in ("html", "csv"):
            return _export(result, na, nb, "", format, include_unchanged)
        return {**result, "a": {"label": na, "filename": na}, "b": {"label": nb, "filename": nb}}

    # -- Interface ------------------------------------------------------------
    @app.api_route("/", methods=["GET", "HEAD"], include_in_schema=False)
    def index():
        return FileResponse(STATIC_DIR / "index.html", headers={"Cache-Control": "no-cache"})

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    return app


def run() -> None:  # pragma: no cover - point d'entrée
    import uvicorn

    settings = Settings.from_env()
    if os.environ.get("SCENARIO_ALLOW_OUTBOUND", "").lower() not in ("1", "true", "yes", "oui"):
        offline.install()
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port,
                proxy_headers=settings.trust_forwarded, server_header=False, log_level="info")


if __name__ == "__main__":  # pragma: no cover
    run()
