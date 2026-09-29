import base64
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from tests import builders as B

STATIC = Path(__file__).resolve().parent.parent / "app" / "static"


def settings(tmp_path, password=""):
    return Settings(data_dir=tmp_path, host="127.0.0.1", port=0, user="scenario", password=password,
                    max_upload_mb=1, trust_forwarded=False)


@pytest.fixture
def client(tmp_path):
    return TestClient(create_app(settings(tmp_path)))


def test_full_flow(client, fixture_bytes, v1):
    assert client.get("/api/health").json()["status"] == "ok"
    p = client.post("/api/projects", json={"name": "Le Phare"}).json()
    r1 = client.post(f"/api/projects/{p['id']}/versions", files={"file": ("v1.fountain", fixture_bytes("v1.fountain"))},
                     data={"label": "Premier jet"})
    assert r1.status_code == 201, r1.text
    r2 = client.post(f"/api/projects/{p['id']}/versions", files={"file": ("v2.pdf", B.to_pdf(v1, 20))})
    assert r2.status_code == 201
    r3 = client.post(f"/api/projects/{p['id']}/versions", files={"file": ("v3.fountain", fixture_bytes("v2.fountain"))})
    ids = [r1.json()["id"], r2.json()["id"], r3.json()["id"]]
    # doublon refusé puis accepté explicitement
    dup = client.post(f"/api/projects/{p['id']}/versions", files={"file": ("x.fountain", fixture_bytes("v1.fountain"))})
    assert dup.status_code == 409
    proj = client.get(f"/api/projects/{p['id']}").json()
    assert [v["label"] for v in proj["versions"]] == ["Premier jet", "Version 2", "Version 3"]

    same = client.get(f"/api/compare?a={ids[0]}&b={ids[1]}").json()
    assert same["summary"]["identical"]
    diff = client.get(f"/api/compare?a={ids[1]}&b={ids[2]}").json()
    assert diff["summary"]["scenes"]["added"] == 1

    tl = client.get(f"/api/projects/{p['id']}/timeline").json()
    assert len(tl["steps"]) == 2 and tl["steps"][0]["summary"]["identical"]

    html = client.get(f"/api/compare/export?a={ids[1]}&b={ids[2]}&format=html")
    assert html.status_code == 200 and "Comparaison de versions" in html.text
    assert "attachment" in html.headers["content-disposition"]
    csv = client.get(f"/api/compare/export?a={ids[1]}&b={ids[2]}&format=csv")
    assert csv.text.startswith("﻿Séq. A;")
    assert client.get(f"/api/versions/{ids[0]}/fountain").text.startswith("Title: Le Phare")
    assert client.get(f"/api/versions/{ids[0]}/original").content == fixture_bytes("v1.fountain")
    assert client.get(f"/api/projects/{p['id']}/archive").content[:2] == b"PK"

    # réordonner, renommer, supprimer
    client.patch(f"/api/versions/{ids[2]}", json={"move": "up", "label": "Troisième"})
    proj = client.get(f"/api/projects/{p['id']}").json()
    assert [v["id"] for v in proj["versions"]] == [ids[0], ids[2], ids[1]]
    assert proj["versions"][1]["label"] == "Troisième"
    assert client.delete(f"/api/versions/{ids[1]}").status_code == 204
    assert client.get(f"/api/versions/{ids[1]}").status_code == 404
    assert client.delete(f"/api/projects/{p['id']}").status_code == 204
    assert client.get("/api/projects").json() == []


def test_quick_compare(client, fixture_bytes):
    r = client.post("/api/quick-compare", files={"file_a": ("a.fountain", fixture_bytes("v1.fountain")),
                                                 "file_b": ("b.fountain", fixture_bytes("v2.fountain"))},
                    data={"ignore_case": "true"})
    assert r.status_code == 200
    assert r.json()["options"]["ignore_case"] is True
    r = client.post("/api/quick-compare", files={"file_a": ("a.fountain", fixture_bytes("v1.fountain")),
                                                 "file_b": ("b.fountain", fixture_bytes("v2.fountain"))},
                    data={"format": "csv"})
    assert r.headers["content-type"].startswith("text/csv")


def test_upload_errors(client):
    p = client.post("/api/projects", json={"name": "X"}).json()
    r = client.post(f"/api/projects/{p['id']}/versions", files={"file": ("x.pdf", b"%PDF-1.4 broken")})
    assert r.status_code == 422
    r = client.post(f"/api/projects/{p['id']}/versions", files={"file": ("big.txt", b"a" * (1024 * 1024 + 10))})
    assert r.status_code == 413
    assert client.post("/api/projects", json={"name": ""}).status_code == 422


def test_security_headers_and_no_docs(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "default-src 'self'" in r.headers["content-security-policy"]
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(path).status_code == 404


def test_basic_auth(tmp_path):
    c = TestClient(create_app(settings(tmp_path, password="s3cret")))
    assert c.get("/api/projects").status_code == 401
    assert c.get("/api/health").status_code == 200
    bad = base64.b64encode(b"scenario:nope").decode()
    assert c.get("/api/projects", headers={"Authorization": f"Basic {bad}"}).status_code == 401
    good = base64.b64encode(b"scenario:s3cret").decode()
    assert c.get("/api/projects", headers={"Authorization": f"Basic {good}"}).status_code == 200


def test_static_files_have_no_external_resources():
    """Garantie « rien en ligne » : aucune URL externe dans l'interface."""
    for f in STATIC.iterdir():
        text = f.read_text(encoding="utf-8")
        urls = re.findall(r"https?://[^\s\"')]+", text)
        assert [u for u in urls if "www.w3.org/2000/svg" not in u] == [], f.name
        assert "@import" not in text and "fonts.googleapis" not in text


def test_reparse_after_parser_upgrade(client, fixture_bytes, monkeypatch):
    p = client.post("/api/projects", json={"name": "X"}).json()
    v = client.post(f"/api/projects/{p['id']}/versions", files={"file": ("v1.fountain", fixture_bytes("v1.fountain"))}).json()
    import app.store as store_mod
    monkeypatch.setattr(store_mod, "PARSER_VERSION", 999)
    client.get(f"/api/versions/{v['id']}")
    row = client.app.state.store._q("SELECT parser_version FROM versions WHERE id=?", (v["id"],))[0]
    assert row["parser_version"] == 999


def test_offline_guard_blocks_outbound():
    import socket
    import subprocess
    import sys
    code = (
        "import socket, urllib.request\n"
        "from app import offline\n"
        "offline.install()\n"
        "for target in ('http://example.com', 'http://93.184.216.34'):\n"
        "    try:\n"
        "        urllib.request.urlopen(target, timeout=2)\n"
        "        print('LEAK', target)\n"
        "    except Exception as e:\n"
        "        print('blocked', type(e).__name__)\n"
        "s = socket.socket(); s.bind(('127.0.0.1', 0)); s.listen(1)\n"
        "c = socket.create_connection(s.getsockname()); print('loopback ok')\n"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                         cwd=Path(__file__).resolve().parent.parent, timeout=30)
    assert "LEAK" not in out.stdout, out.stdout
    assert out.stdout.count("blocked") == 2 and "loopback ok" in out.stdout, out.stdout + out.stderr
    del socket


def test_backup(client, fixture_bytes, tmp_path):
    import zipfile

    from app.backup import backup
    p = client.post("/api/projects", json={"name": "X"}).json()
    client.post(f"/api/projects/{p['id']}/versions", files={"file": ("v1.fountain", fixture_bytes("v1.fountain"))})
    z = backup(client.app.state.settings.data_dir, tmp_path / "bk")
    names = zipfile.ZipFile(z).namelist()
    assert "scenario.db" in names and any(n.startswith("files/") for n in names)
