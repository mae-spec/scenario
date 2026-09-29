/* Comparateur de scénarios — interface web (aucune dépendance externe). */
"use strict";
(() => {
  const $app = document.getElementById("app");

  // ------------------------------------------------------------------ utilitaires
  function h(tag, attrs, ...children) {
    const el = document.createElement(tag);
    if (attrs) {
      for (const [k, v] of Object.entries(attrs)) {
        if (v === null || v === undefined || v === false) continue;
        if (k === "class") el.className = v;
        else if (k === "text") el.textContent = v;
        else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
        else if (k === "dataset") Object.assign(el.dataset, v);
        else if (k === "value") el.value = v;
        else if (k === "checked") el.checked = !!v;
        else el.setAttribute(k, v === true ? "" : v);
      }
    }
    append(el, children);
    return el;
  }
  function append(el, children) {
    for (const c of children.flat(Infinity)) {
      if (c === null || c === undefined || c === false) continue;
      el.append(c instanceof Node ? c : document.createTextNode(String(c)));
    }
    return el;
  }
  const nf = new Intl.NumberFormat("fr-FR");
  const fmt = (n) => (n === null || n === undefined ? "—" : nf.format(n));
  const fmtDate = (ts) => (ts ? new Date(ts * 1000).toLocaleString("fr-FR", { dateStyle: "medium", timeStyle: "short" }) : "");
  const pct = (x) => `${(x * 100).toFixed(1).replace(".", ",")} %`;
  const signed = (n) => (n > 0 ? `+${fmt(n)}` : n < 0 ? `−${fmt(-n)}` : "0");
  const fold = (s) => (s || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();

  function store(key, value) {
    try {
      if (value === undefined) return JSON.parse(localStorage.getItem("scn:" + key));
      localStorage.setItem("scn:" + key, JSON.stringify(value));
    } catch (_) { return null; }
    return value;
  }

  let toastTimer;
  function toast(msg, error = false) {
    const t = document.getElementById("toast");
    t.textContent = msg;
    t.className = "show" + (error ? " error" : "");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => (t.className = ""), error ? 6000 : 2500);
  }

  async function api(method, url, body) {
    const opt = { method, headers: {} };
    if (body !== undefined) {
      opt.headers["Content-Type"] = "application/json";
      opt.body = JSON.stringify(body);
    }
    const res = await fetch(url, opt);
    if (res.status === 204) return null;
    let data = null;
    try { data = await res.json(); } catch (_) { /* réponse vide */ }
    if (!res.ok) {
      let msg = (data && data.detail) || `Erreur ${res.status}`;
      if (Array.isArray(msg)) msg = msg.map((d) => d.msg).join(" ; ");
      const err = new Error(msg);
      err.status = res.status;
      throw err;
    }
    return data;
  }

  function uploadXHR(url, form, onProgress) {
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open("POST", url);
      xhr.upload.onprogress = (e) => e.lengthComputable && onProgress && onProgress(e.loaded / e.total);
      xhr.onload = () => {
        let data = null;
        try { data = JSON.parse(xhr.responseText); } catch (_) { /* */ }
        if (xhr.status >= 200 && xhr.status < 300) resolve(data);
        else {
          const err = new Error((data && data.detail) || `Erreur ${xhr.status}`);
          err.status = xhr.status;
          reject(err);
        }
      };
      xhr.onerror = () => reject(new Error("Connexion au serveur impossible."));
      xhr.send(form);
    });
  }

  const qs = (params) =>
    Object.entries(params)
      .filter(([, v]) => v !== undefined && v !== null && v !== "")
      .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`)
      .join("&");

  function downloadBlob(blob, name) {
    const url = URL.createObjectURL(blob);
    const a = h("a", { href: url, download: name });
    document.body.append(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 2000);
  }

  function setView(...nodes) {
    $app.replaceChildren(...nodes.flat(Infinity).filter((n) => n !== null && n !== undefined && n !== false));
    window.scrollTo(0, 0);
  }

  function errorView(err) {
    setView(h("div", { class: "error-box" }, err.message || String(err)), h("p", {}, h("a", { href: "#/" }, "← Retour aux projets")));
  }

  function dropzone({ label, accept, multiple = false, onFiles }) {
    const input = h("input", { type: "file", accept, class: "hidden", multiple });
    const zone = h("div", { class: "dropzone", tabindex: "0", role: "button" }, h("strong", {}, label), h("div", { class: "small" }, "Glissez un fichier ici ou cliquez pour choisir — Fountain, Final Draft (FDX), Word (DOCX), OpenDocument (ODT), PDF, texte"), input);
    zone.addEventListener("click", () => input.click());
    zone.addEventListener("keydown", (e) => (e.key === "Enter" || e.key === " ") && input.click());
    zone.addEventListener("dragover", (e) => { e.preventDefault(); zone.classList.add("over"); });
    zone.addEventListener("dragleave", () => zone.classList.remove("over"));
    zone.addEventListener("drop", (e) => {
      e.preventDefault();
      zone.classList.remove("over");
      if (e.dataTransfer.files.length) onFiles([...e.dataTransfer.files]);
    });
    input.addEventListener("change", () => { if (input.files.length) onFiles([...input.files]); input.value = ""; });
    return zone;
  }
  const ACCEPT = ".fountain,.spmd,.txt,.fdx,.docx,.odt,.pdf";

  // ------------------------------------------------------------------ routeur
  const routes = [
    [/^$/, viewProjects],
    [/^projet\/(\d+)$/, (m) => viewProject(+m[1])],
    [/^version\/(\d+)$/, (m) => viewVersion(+m[1])],
    [/^comparer\/(\d+)\/(\d+)$/, (m, q) => viewCompare(+m[1], +m[2], q)],
    [/^rapide$/, viewQuick],
    [/^aide$/, viewHelp],
  ];

  function route() {
    const raw = location.hash.replace(/^#\/?/, "");
    const [path, query] = raw.split("?");
    const q = new URLSearchParams(query || "");
    document.querySelectorAll(".topbar nav a").forEach((a) => {
      const target = a.getAttribute("href").replace(/^#\/?/, "");
      a.classList.toggle("active", target === path || (target === "" && /^(projet|version|comparer)/.test(path)));
    });
    for (const [re, fn] of routes) {
      const m = path.match(re);
      if (m) {
        Promise.resolve(fn(m, q)).catch(errorView);
        return;
      }
    }
    setView(h("p", {}, "Page introuvable. ", h("a", { href: "#/" }, "Retour")));
  }
  window.addEventListener("hashchange", route);

  // ------------------------------------------------------------------ projets
  async function viewProjects() {
    const projects = await api("GET", "/api/projects");
    const name = h("input", { type: "text", placeholder: "Titre du scénario", maxlength: "200", required: true });
    const desc = h("input", { type: "text", placeholder: "Description (facultatif)", maxlength: "5000" });
    const form = h("form", { class: "card row", onsubmit: async (e) => {
      e.preventDefault();
      if (!name.value.trim()) return;
      try {
        const p = await api("POST", "/api/projects", { name: name.value, description: desc.value });
        location.hash = `#/projet/${p.id}`;
      } catch (err) { toast(err.message, true); }
    } }, name, desc, h("button", { class: "primary", type: "submit" }, "Créer le projet"));

    const list = projects.length
      ? h("div", { class: "grid" }, projects.map((p) =>
          h("a", { class: "card project-card", href: `#/projet/${p.id}` },
            h("h3", {}, p.name),
            p.description ? h("div", { class: "muted small" }, p.description) : null,
            h("div", { class: "small muted" }, `${p.versions} version${p.versions > 1 ? "s" : ""} · modifié le ${fmtDate(p.updated_at)}`))))
      : h("div", { class: "empty-state card" }, h("p", {}, "Aucun projet pour l'instant."), h("p", { class: "small" }, "Créez un projet (un scénario), puis déposez-y ses versions successives."));

    setView(
      h("div", { class: "row spread" }, h("h1", {}, "Projets"), h("a", { class: "btn", href: "#/rapide" }, "Comparaison rapide de deux fichiers")),
      h("p", { class: "muted" }, "Chaque projet regroupe les versions successives d'un scénario. Les fichiers sont stockés uniquement sur ce serveur."),
      form, h("h2", {}, "Vos projets"), list);
  }

  async function viewProject(pid) {
    const [project, info] = await Promise.all([api("GET", `/api/projects/${pid}`), api("GET", "/api/info")]);
    const versions = project.versions;
    document.title = `${project.name} — Comparateur de scénarios`;

    // En-tête éditable
    const title = h("h1", {}, project.name);
    const header = h("div", { class: "row spread" },
      h("div", {}, h("div", { class: "small" }, h("a", { href: "#/" }, "← Projets")), title,
        project.description ? h("div", { class: "muted" }, project.description) : null),
      h("div", { class: "row" },
        h("button", { onclick: async () => {
          const n = prompt("Nouveau titre du projet :", project.name);
          if (n === null || !n.trim()) return;
          const d = prompt("Description :", project.description);
          await api("PATCH", `/api/projects/${pid}`, { name: n, description: d === null ? project.description : d });
          route();
        } }, "Renommer"),
        versions.length ? h("a", { class: "btn", href: `/api/projects/${pid}/archive`, download: "" }, "Archive ZIP") : null,
        h("button", { class: "danger", onclick: async () => {
          if (!confirm(`Supprimer définitivement le projet « ${project.name} » et ses ${versions.length} version(s) ?`)) return;
          await api("DELETE", `/api/projects/${pid}`);
          location.hash = "#/";
        } }, "Supprimer")));

    // Dépôt d'une version
    const label = h("input", { type: "text", placeholder: `Version ${versions.length + 1}`, maxlength: "200" });
    const date = h("input", { type: "date" });
    const notes = h("input", { type: "text", placeholder: "Notes (facultatif)", maxlength: "10000" });
    const bar = h("div");
    const progress = h("div", { class: "progress hidden" }, bar);
    async function send(files) {
      for (const f of files) {
        const form = new FormData();
        form.append("file", f);
        form.append("label", files.length > 1 ? f.name.replace(/\.[^.]+$/, "") : label.value);
        form.append("doc_date", date.value);
        form.append("notes", notes.value);
        progress.classList.remove("hidden");
        try {
          try {
            await uploadXHR(`/api/projects/${pid}/versions`, form, (p) => (bar.style.width = `${Math.round(p * 100)}%`));
          } catch (err) {
            if (err.status === 409 && confirm(`${err.message}\nL'ajouter quand même ?`)) {
              form.append("allow_duplicate", "true");
              await uploadXHR(`/api/projects/${pid}/versions`, form);
            } else throw err;
          }
          toast(`« ${f.name} » ajouté.`);
        } catch (err) {
          toast(`${f.name} : ${err.message}`, true);
        }
      }
      route();
    }
    const upload = h("div", { class: "card stack" },
      h("h2", { class: "no-margin" }, "Ajouter une version"),
      h("div", { class: "row" },
        h("label", { class: "field" }, "Nom de la version", label),
        h("label", { class: "field" }, "Date du document", date),
        h("label", { class: "field grow" }, "Notes", notes)),
      dropzone({ label: "Déposer une nouvelle version", accept: ACCEPT, multiple: true, onFiles: send }),
      progress,
      h("div", { class: "small muted" }, `Taille maximale : ${info.max_upload_mb} Mo. Plusieurs fichiers déposés ensemble sont ajoutés dans l'ordre, nommés d'après le fichier.`));

    // Tableau des versions
    let table;
    if (!versions.length) {
      table = h("div", { class: "empty-state card" }, "Aucune version. Déposez un premier fichier ci-dessus.");
    } else {
      const rows = versions.map((v, i) => {
        const s = v.stats || {};
        const warn = (s.warnings || []).length;
        return h("tr", {},
          h("td", { class: "num muted" }, i + 1),
          h("td", {}, h("a", { href: `#/version/${v.id}` }, h("strong", {}, v.label)),
            warn ? h("span", { class: "tag warn", title: s.warnings.join("\n") }, " ⚠ ", warn) : null,
            h("div", { class: "small muted" }, v.filename, v.notes ? ` — ${v.notes}` : "")),
          h("td", { class: "small nowrap" }, v.doc_date ? new Date(v.doc_date).toLocaleDateString("fr-FR") : h("span", { class: "muted" }, fmtDate(v.created_at))),
          h("td", { class: "num" }, fmt(s.scenes)),
          h("td", { class: "num" }, s.pages !== undefined ? `≈ ${String(s.pages).replace(".", ",")}` : "—"),
          h("td", { class: "num" }, fmt(s.dialogues)),
          h("td", { class: "num" }, fmt(s.words)),
          h("td", { class: "num" }, fmt((s.characters || []).length)),
          h("td", { class: "nowrap" },
            i > 0 ? h("a", { class: "btn small primary", href: `#/comparer/${versions[i - 1].id}/${v.id}`, title: "Comparer avec la version précédente" }, "↔ précédente") : null, " ",
            h("button", { class: "small icon", title: "Monter", disabled: i === 0, onclick: () => patchVersion(v.id, { move: "up" }) }, "↑"),
            h("button", { class: "small icon", title: "Descendre", disabled: i === versions.length - 1, onclick: () => patchVersion(v.id, { move: "down" }) }, "↓"),
            h("button", { class: "small icon", title: "Modifier le nom, la date, les notes", onclick: () => editVersion(v) }, "✎"),
            h("a", { class: "btn small icon", title: "Télécharger l'original", href: `/api/versions/${v.id}/original`, download: "" }, "⤓"),
            h("button", { class: "small icon danger", title: "Supprimer", onclick: async () => {
              if (!confirm(`Supprimer la version « ${v.label} » ?`)) return;
              await api("DELETE", `/api/versions/${v.id}`);
              route();
            } }, "✕")));
      });
      table = h("div", { class: "card table-wrap" }, h("table", { class: "data" },
        h("thead", {}, h("tr", {}, ["#", "Version", "Date", "Séq.", "Pages", "Répliques", "Mots", "Pers.", ""].map((t) => h("th", { class: /Séq|Pages|Répl|Mots|Pers/.test(t) ? "num" : "" }, t)))),
        h("tbody", {}, rows)));
    }

    // Sélecteur de comparaison libre
    let picker = null;
    if (versions.length >= 2) {
      const mk = (sel) => h("select", {}, versions.map((v, i) => h("option", { value: v.id, selected: i === sel ? "selected" : null }, `${i + 1}. ${v.label}`)));
      const sa = mk(versions.length - 2);
      const sb = mk(versions.length - 1);
      picker = h("div", { class: "card row" }, h("strong", {}, "Comparer :"), h("span", { class: "tag deleted" }, "A"), sa, "→", h("span", { class: "tag added" }, "B"), sb,
        h("button", { class: "primary", onclick: () => {
          if (sa.value === sb.value) return toast("Choisissez deux versions différentes.", true);
          location.hash = `#/comparer/${sa.value}/${sb.value}`;
        } }, "Comparer"));
    }

    const timelineBox = h("div");
    setView(header, h("div", { class: "stack" }, upload, picker, h("h2", {}, `Versions (${versions.length})`), table), timelineBox);
    if (versions.length >= 2) renderTimeline(pid, timelineBox);
  }

  async function patchVersion(vid, body) {
    try { await api("PATCH", `/api/versions/${vid}`, body); route(); } catch (err) { toast(err.message, true); }
  }

  function editVersion(v) {
    const label = prompt("Nom de la version :", v.label);
    if (label === null) return;
    const date = prompt("Date du document (AAAA-MM-JJ, facultatif) :", v.doc_date || "");
    if (date === null) return;
    const notes = prompt("Notes :", v.notes || "");
    if (notes === null) return;
    patchVersion(v.id, { label, doc_date: date, notes });
  }

  async function renderTimeline(pid, box) {
    box.replaceChildren(h("h2", {}, "Évolution"), h("p", { class: "muted" }, "Calcul des différences entre versions successives…"));
    let tl;
    try { tl = await api("GET", `/api/projects/${pid}/timeline`); } catch (err) {
      box.replaceChildren(h("div", { class: "error-box" }, err.message));
      return;
    }
    const byId = Object.fromEntries(tl.versions.map((v) => [v.id, v]));
    const maxChange = Math.max(0.0001, ...tl.steps.filter((s) => s.summary).map((s) => s.summary.change_ratio));
    const rows = tl.steps.map((st) => {
      const a = byId[st.a], b = byId[st.b];
      if (st.error) return h("tr", {}, h("td", {}, `${a.label} → ${b.label}`), h("td", { colspan: "7", class: "minus" }, st.error));
      const s = st.summary, sc = s.scenes, d = s.units.dialogue, ac = s.units.action;
      const bar = h("div", { class: "bar", title: pct(s.change_ratio) }, h("span", { class: "b-mod" }));
      bar.firstChild.style.width = `${Math.max(2, (s.change_ratio / maxChange) * 100)}%`;
      return h("tr", {},
        h("td", {}, h("a", { href: `#/comparer/${st.a}/${st.b}` }, `${a.label} → ${b.label}`),
          st.renames.length ? h("div", { class: "small muted" }, "Renommage : ", st.renames.map((r) => `${r.from} → ${r.to}`).join(", ")) : null),
        h("td", { class: "num" }, s.identical ? h("span", { class: "tag" }, "identiques") : `${sc.a} → ${sc.b}`),
        h("td", { class: "small" }, stepTags([["modified", sc.modified, "~"], ["added", sc.added, "+"], ["deleted", sc.deleted, "−"], ["moved", sc.moved, "⇅"]])),
        h("td", { class: "small" }, stepTags([["modified", d.modified, "~"], ["added", d.added, "+"], ["deleted", d.deleted, "−"]])),
        h("td", { class: "small" }, stepTags([["modified", ac.modified, "~"], ["added", ac.added, "+"], ["deleted", ac.deleted, "−"]])),
        h("td", { class: "num nowrap" }, h("span", { class: "plus" }, `+${fmt(s.words.added)}`), " / ", h("span", { class: "minus" }, `−${fmt(s.words.deleted)}`)),
        h("td", {}, h("div", { class: "row" }, bar, h("span", { class: "small" }, pct(s.change_ratio)))));
    });
    const chars = tl.characters.slice(0, 25);
    const charTable = h("table", { class: "data" },
      h("thead", {}, h("tr", {}, h("th", {}, "Personnage"), tl.versions.map((v, i) => h("th", { class: "num", title: v.label }, `${i + 1}. ${v.label.slice(0, 14)}`)))),
      h("tbody", {}, chars.map((c) => h("tr", {}, h("td", {}, c.name), c.values.map((x, i) => {
        const prev = i > 0 ? c.values[i - 1] : undefined;
        const lines = x ? x.lines : 0;
        const delta = i > 0 ? lines - (prev ? prev.lines : 0) : 0;
        return h("td", { class: "num", title: x ? `${x.words} mots` : "absent" }, x ? fmt(lines) : h("span", { class: "muted" }, "—"),
          delta ? h("span", { class: `small ${delta > 0 ? "plus" : "minus"}` }, ` (${signed(delta)})`) : null);
      })))));
    box.replaceChildren(
      h("h2", {}, "Évolution entre versions successives"),
      h("div", { class: "card table-wrap" }, h("table", { class: "data" },
        h("thead", {}, h("tr", {}, ["Étape", "Séquences", "Séq. ~ + − ⇅", "Répliques ~ + −", "Actions ~ + −", "Mots", "Changement"].map((t) => h("th", {}, t)))),
        h("tbody", {}, rows))),
      h("h2", {}, "Répliques par personnage et par version"),
      h("div", { class: "card table-wrap" }, charTable,
        tl.characters.length > chars.length ? h("p", { class: "small muted" }, `${tl.characters.length - chars.length} personnages secondaires non affichés.`) : null));
  }

  function stepTags(items) {
    const out = items.filter(([, n]) => n).map(([cls, n, sym]) => h("span", { class: `tag ${cls}` }, `${sym}${n}`));
    return out.length ? out.flatMap((x) => [x, " "]) : h("span", { class: "muted" }, "—");
  }

  // ------------------------------------------------------------------ lecture d'une version
  async function viewVersion(vid) {
    const v = await api("GET", `/api/versions/${vid}`);
    const sp = v.screenplay, s = v.stats;
    document.title = `${v.label} — Comparateur de scénarios`;
    const script = h("div", { class: "script" });
    const tp = Object.entries(sp.title_page || {});
    if (tp.length) script.append(h("div", { class: "ac muted" }, tp.map(([k, val]) => `${k} : ${val}`).join("\n")));
    let ordinal = 0;
    for (const sc of sp.scenes) {
      if (!sc.prologue) ordinal++;
      for (const sec of sc.sections) script.append(h("div", { class: "sh muted" }, `# ${sec}`));
      if (!sc.prologue) script.append(h("div", { class: "sh", id: `sc-${ordinal}` }, h("span", { class: "n" }, sc.number || ordinal), sc.heading));
      for (const u of sc.units) {
        if (u.kind === "dialogue") {
          script.append(h("div", { class: "ch" }, u.character, u.extension ? ` (${u.extension})` : "", u.dual ? " ^" : ""));
          for (const p of u.parts) script.append(h("div", { class: p.type === "paren" ? "pa" : "dl" }, p.text));
        } else if (u.kind === "transition") script.append(h("div", { class: "tr" }, u.text));
        else script.append(h("div", { class: "ac" }, u.text));
      }
    }
    const warnings = (s.warnings || []).map((w) => h("div", { class: "warning" }, "⚠ ", w));
    setView(
      h("div", { class: "small" }, h("a", { href: `#/projet/${v.project_id}` }, "← Retour au projet")),
      h("div", { class: "row spread" }, h("h1", {}, v.label),
        h("div", { class: "row" },
          h("a", { class: "btn", href: `/api/versions/${vid}/original`, download: "" }, "Fichier original"),
          h("a", { class: "btn", href: `/api/versions/${vid}/fountain`, download: "" }, "Exporter en Fountain"),
          h("button", { onclick: async () => {
            try { await api("POST", `/api/versions/${vid}/reparse`); toast("Analyse relancée."); route(); } catch (err) { toast(err.message, true); }
          } }, "Réanalyser"))),
      h("p", { class: "muted" }, `${v.filename} · format ${v.fmt.toUpperCase()} · ajouté le ${fmtDate(v.created_at)}`, v.notes ? ` · ${v.notes}` : ""),
      warnings,
      h("div", { class: "stats" },
        stat("Séquences", fmt(s.scenes)), stat("Pages (estim.)", `≈ ${String(s.pages).replace(".", ",")}`),
        stat("Répliques", fmt(s.dialogues)), stat("Blocs d'action", fmt(s.actions)),
        stat("Mots", fmt(s.words)), stat("Personnages", fmt(s.characters.length)), stat("Décors", fmt(s.locations))),
      h("h2", {}, "Personnages"),
      h("div", { class: "card table-wrap" }, h("table", { class: "data" },
        h("thead", {}, h("tr", {}, h("th", {}, "Personnage"), h("th", { class: "num" }, "Répliques"), h("th", { class: "num" }, "Mots"), h("th", { class: "num" }, "Séquences"))),
        h("tbody", {}, s.characters.map((c) => h("tr", {}, h("td", {}, c.name), h("td", { class: "num" }, fmt(c.lines)), h("td", { class: "num" }, fmt(c.words)), h("td", { class: "num" }, fmt(c.scenes))))))),
      h("h2", {}, "Texte analysé"),
      h("p", { class: "small muted" }, "Vérifiez ici que les entêtes, personnages et répliques ont été correctement reconnus : la qualité de la comparaison en dépend."),
      script);
  }

  function stat(label, value, delta) {
    return h("div", { class: "stat" }, h("div", { class: "l" }, label), h("div", { class: "v" }, value), delta ? h("div", { class: "d" }, delta) : null);
  }

  // ------------------------------------------------------------------ comparaison
  const OPT_KEYS = ["ignore_case", "ignore_punct", "normalize_typo"];

  async function viewCompare(a, b, q) {
    const opts = {
      ignore_case: q.get("ignore_case") === "true",
      ignore_punct: q.get("ignore_punct") === "true",
      normalize_typo: q.get("normalize_typo") !== "false",
    };
    setView(h("p", { class: "muted" }, "Comparaison en cours…"));
    const data = await api("GET", `/api/compare?${qs({ a, b, ...opts })}`);
    document.title = `${data.a.label} → ${data.b.label} — Comparateur de scénarios`;
    const exportUrl = (format) => `/api/compare/export?${qs({ a, b, format, ...opts })}`;
    renderCompare(data, {
      opts,
      back: h("a", { href: `#/projet/${data.b.project_id}` }, "← Retour au projet"),
      onOptions: (o) => (location.hash = `#/comparer/${a}/${b}?${qs(o)}`),
      onSwap: () => (location.hash = `#/comparer/${b}/${a}?${qs(opts)}`),
      exports: [
        h("a", { class: "btn", href: exportUrl("html"), download: "" }, "Rapport HTML"),
        h("a", { class: "btn", href: exportUrl("csv"), download: "" }, "CSV (tableur)"),
        h("a", { class: "btn", href: exportUrl("json"), download: "" }, "JSON"),
      ],
    });
  }

  function renderCompare(data, ctx) {
    const state = {
      tab: "scenes",
      statuses: new Set(store("statuses") || ["modified", "added", "deleted", "moved"]),
      kinds: new Set(store("kinds") || ["dialogue", "action", "transition"]),
      character: "",
      search: "",
      hideMinor: !!store("hideMinor"),
      context: !!store("context"),
      mode: store("mode") || "sbs",
      expanded: new Set(),
    };
    const s = data.summary;

    // -- En-tête
    const optBoxes = [
      ["ignore_case", "Ignorer la casse"],
      ["ignore_punct", "Ignorer la ponctuation"],
      ["normalize_typo", "Normaliser la typographie (’ « » … espaces insécables)"],
    ].map(([k, lab]) => {
      const cb = h("input", { type: "checkbox", checked: ctx.opts[k] });
      cb.addEventListener("change", () => ctx.onOptions({ ...ctx.opts, [k]: cb.checked }));
      return h("label", { class: "check" }, cb, lab);
    });
    const head = h("div", { class: "compare-head" },
      h("div", {}, ctx.back ? h("div", { class: "small" }, ctx.back) : null,
        h("div", { class: "versions-ab" }, h("span", { class: "pill a" }, "A : ", data.a.label), ctx.onSwap ? h("button", { class: "small", title: "Inverser A et B", onclick: ctx.onSwap }, "⇄") : "→", h("span", { class: "pill b" }, "B : ", data.b.label)),
        h("div", { class: "small muted" }, s.identical ? "Aucune différence détectée avec les options actuelles." : `Taux de changement : ${pct(s.change_ratio)}`, data.elapsed_ms !== undefined ? ` · calculé en ${data.elapsed_ms} ms` : "")),
      h("div", { class: "row no-print" }, ctx.exports, h("button", { onclick: () => window.print() }, "Imprimer / PDF")));

    const sc = s.scenes, dl = s.units.dialogue, ac = s.units.action;
    const cards = h("div", { class: "stats" },
      stat("Séquences", `${sc.a} → ${sc.b}`, h("span", {}, deltaSpan(sc.b - sc.a))),
      stat("Séq. modifiées", fmt(sc.modified), sc.heading_changed ? `dont ${sc.heading_changed} entête(s)` : null),
      stat("Séq. ajoutées / supprimées", h("span", {}, h("span", { class: "plus" }, `+${sc.added}`), " / ", h("span", { class: "minus" }, `−${sc.deleted}`))),
      stat("Séq. déplacées", fmt(sc.moved)),
      stat("Répliques", h("span", {}, h("span", { class: "plus" }, `+${dl.added}`), " ", h("span", { class: "minus" }, `−${dl.deleted}`), " ~", dl.modified), dl.reassigned ? `${dl.reassigned} réattribuée(s)` : (dl.moved ? `${dl.moved} déplacée(s)` : null)),
      stat("Actions", h("span", {}, h("span", { class: "plus" }, `+${ac.added}`), " ", h("span", { class: "minus" }, `−${ac.deleted}`), " ~", ac.modified), ac.moved ? `${ac.moved} déplacée(s)` : null),
      stat("Mots", h("span", {}, h("span", { class: "plus" }, `+${fmt(s.words.added)}`), " ", h("span", { class: "minus" }, `−${fmt(s.words.deleted)}`)), `${fmt(s.words.a)} → ${fmt(s.words.b)}`),
      stat("Pages (estim.)", `${String(s.pages.a).replace(".", ",")} → ${String(s.pages.b).replace(".", ",")}`, deltaSpan(Math.round((s.pages.b - s.pages.a) * 10) / 10)));

    const renames = data.renames.length
      ? h("div", { class: "warning" }, "Renommage probable : ", data.renames.map((r) => `${r.from} → ${r.to} (${r.lines} répliques)`).join(" ; "))
      : null;

    // -- Onglets
    const tabBtns = {};
    const tabs = h("div", { class: "tabs no-print" }, [["scenes", "Séquences"], ["characters", "Personnages"], ["structure", "Structure"]].map(([k, lab]) => {
      tabBtns[k] = h("button", { onclick: () => { state.tab = k; renderTab(); } }, lab);
      return tabBtns[k];
    }));
    const body = h("div");

    (ctx.mount || setView)(head, h("div", { class: "row small muted no-print" }, "Options :", optBoxes), cards, renames, tabs, body);

    function renderTab() {
      for (const [k, b] of Object.entries(tabBtns)) b.classList.toggle("active", k === state.tab);
      if (state.tab === "scenes") renderScenesTab();
      else if (state.tab === "characters") renderCharactersTab();
      else renderStructureTab();
    }

    // -- Filtres
    const isChange = (u) => {
      if (u.status === "unchanged" && !u.moved) return false;
      if (state.hideMinor && u.minor && !u.moved && !u.reassigned && !u.ext_changed) return false;
      return true;
    };
    const charOk = (u) => !state.character || (u.kind === "dialogue" && (u.character === state.character || u.character_a === state.character));
    const searchOk = (u) => !state.search || fold(`${u.text}\n${u.text_a || ""}\n${u.character || ""}\n${u.character_a || ""}`).includes(state.search);
    const unitVisible = (u) => isChange(u) && state.kinds.has(u.kind) && charOk(u) && searchOk(u);
    function sceneVisible(scn) {
      const st = scn.status;
      const statusOk = state.statuses.has(st) || (scn.moved && state.statuses.has("moved"));
      if (!statusOk) return false;
      if (st === "unchanged" && !scn.moved) {
        if (!state.character && !state.search) return true;
        return scn.units.some((u) => charOk(u) && searchOk(u)) || (!!state.search && fold(scn.heading_b || "").includes(state.search));
      }
      if (scn.units.some(unitVisible)) return true;
      if (scn.heading_changed && !(state.hideMinor && scn.heading_minor) && !state.character && (!state.search || fold(`${scn.heading_a} ${scn.heading_b}`).includes(state.search))) return true;
      if (scn.moved && !state.character && !state.search && state.statuses.has("moved")) return true;
      if (!state.character && state.search && fold(`${scn.heading_a || ""} ${scn.heading_b || ""}`).includes(state.search)) return true;
      return (st === "added" || st === "deleted") && !scn.units.length && !state.character && !state.search;
    }

    function renderScenesTab() {
      const chk = (set, key, value, label, cls) => {
        const cb = h("input", { type: "checkbox", checked: set.has(value) });
        cb.addEventListener("change", () => {
          cb.checked ? set.add(value) : set.delete(value);
          store(key, [...set]);
          drawScenes();
        });
        return h("label", { class: "check" }, cb, cls ? h("span", { class: `tag ${cls}` }, label) : label);
      };
      const toggle = (key, label) => {
        const cb = h("input", { type: "checkbox", checked: state[key] });
        cb.addEventListener("change", () => { state[key] = cb.checked; store(key, cb.checked); drawScenes(); });
        return h("label", { class: "check" }, cb, label);
      };
      const chars = [...new Set(data.characters.map((c) => c.name))];
      const charSel = h("select", { title: "Filtrer par personnage" }, h("option", { value: "" }, "Tous les personnages"), chars.map((c) => h("option", { value: c, selected: c === state.character ? "selected" : null }, c)));
      charSel.addEventListener("change", () => { state.character = charSel.value; drawScenes(); });
      const search = h("input", { type: "search", placeholder: "Rechercher…", value: state.search, size: "16" });
      let t;
      search.addEventListener("input", () => { clearTimeout(t); t = setTimeout(() => { state.search = fold(search.value.trim()); drawScenes(); }, 200); });
      const modeSel = h("select", { title: "Affichage" }, h("option", { value: "sbs" }, "Côte à côte"), h("option", { value: "unified" }, "Fusionné"));
      modeSel.value = state.mode;
      modeSel.addEventListener("change", () => { state.mode = modeSel.value; store("mode", state.mode); drawScenes(); });

      const toolbar = h("div", { class: "toolbar" },
        h("div", { class: "group" }, h("strong", { class: "small" }, "Séquences :"),
          chk(state.statuses, "statuses", "modified", "modifiées", "modified"), chk(state.statuses, "statuses", "added", "ajoutées", "added"),
          chk(state.statuses, "statuses", "deleted", "supprimées", "deleted"), chk(state.statuses, "statuses", "moved", "déplacées", "moved"),
          chk(state.statuses, "statuses", "unchanged", "inchangées")),
        h("div", { class: "sep" }),
        h("div", { class: "group" }, h("strong", { class: "small" }, "Éléments :"),
          chk(state.kinds, "kinds", "dialogue", "répliques"), chk(state.kinds, "kinds", "action", "actions"), chk(state.kinds, "kinds", "transition", "transitions")),
        h("div", { class: "sep" }),
        h("div", { class: "group" }, charSel, search, modeSel),
        h("div", { class: "group" }, toggle("hideMinor", "Masquer ponctuation/casse"), toggle("context", "Afficher le contexte")),
        h("div", { class: "group small muted" }, h("span", { class: "kbd" }, "j"), "/", h("span", { class: "kbd" }, "k"), " séquence suivante/précédente"));
      const index = h("nav", { class: "scene-index" });
      const list = h("div");
      const counter = h("div", { class: "small muted" });
      body.replaceChildren(toolbar, h("div", { class: "compare-layout" }, index, h("div", {}, counter, list)));

      function drawScenes() {
        const visible = data.scenes.filter(sceneVisible);
        counter.textContent = `${visible.length} séquence(s) affichée(s) sur ${data.scenes.length}`;
        index.replaceChildren(...visible.map((scn) => {
          const cls = scn.moved && scn.status === "unchanged" ? "s-moved" : `s-${scn.status}`;
          return h("a", { href: `#scene-${scn.id}`, class: cls, onclick: (e) => { e.preventDefault(); document.getElementById(`scene-${scn.id}`)?.scrollIntoView({ behavior: "smooth" }); } },
            h("span", { class: "n" }, sceneNum(scn)), h("span", { class: "h" }, sceneTitle(scn)));
        }));
        list.replaceChildren(...(visible.length ? visible.map(renderScene) : [h("div", { class: "empty-state card" }, s.identical ? "Les deux versions sont identiques." : "Aucune séquence ne correspond aux filtres.")]));
      }

      function renderScene(scn) {
        const tags = [h("span", { class: `tag ${scn.status}` }, { unchanged: "inchangée", modified: "modifiée", added: "ajoutée", deleted: "supprimée" }[scn.status])];
        if (scn.moved) tags.push(h("span", { class: "tag moved" }, "déplacée"));
        if (scn.renumbered) tags.push(h("span", { class: "tag" }, "renumérotée"));
        let heading;
        if (scn.prologue) heading = h("span", { class: "muted" }, "Ouverture (avant la première séquence)");
        else if (scn.heading_diff) heading = segsUnified(scn.heading_diff);
        else heading = scn.heading_b ?? scn.heading_a;
        const el = h("section", { class: `scene st-scene-${scn.status}`, id: `scene-${scn.id}` });
        const header = h("header", { title: "Cliquer pour replier / déplier" }, h("span", { class: "num" }, sceneNum(scn)), h("span", { class: "heading" }, heading), tags);
        header.addEventListener("click", () => el.classList.toggle("collapsed"));
        const meta = [];
        if (scn.chars_added && scn.chars_added.length) meta.push(h("span", {}, "Entrent dans la séquence : ", h("span", { class: "plus" }, scn.chars_added.join(", "))));
        if (scn.chars_removed && scn.chars_removed.length) meta.push(h("span", {}, "Ne parlent plus : ", h("span", { class: "minus" }, scn.chars_removed.join(", "))));
        if (scn.moved) meta.push(h("span", {}, `Position : séq. ${scn.label_a} dans A → séq. ${scn.label_b} dans B`));
        el.append(header);
        if (meta.length) el.append(h("div", { class: "scene-meta" }, meta));

        const units = h("div", { class: `units ${state.mode}` });
        const showAll = state.context || state.expanded.has(scn.id) || (scn.status === "unchanged" && !scn.moved);
        let hidden = 0;
        const flush = () => {
          if (!hidden) return;
          const n = hidden;
          units.append(h("div", { class: "ellipsis", onclick: () => { state.expanded.add(scn.id); el.replaceWith(renderScene(scn)); } }, `… ${n} élément${n > 1 ? "s" : ""} inchangé${n > 1 ? "s" : ""} (cliquer pour afficher)`));
          hidden = 0;
        };
        for (const u of scn.units) {
          const vis = unitVisible(u);
          if (!vis && !showAll) { hidden++; continue; }
          flush();
          units.append(renderUnit(u, !vis));
        }
        flush();
        if (scn.units.length) el.append(units);
        return el;
      }

      drawScenes();
      body._drawScenes = drawScenes;
    }

    function renderUnit(u, asContext) {
      const st = asContext ? "ctx" : u.status;
      const kindLabel = { dialogue: "Réplique", action: "Action", transition: "Transition" }[u.kind] || u.kind;
      const tags = [];
      if (!asContext) {
        if (u.moved) tags.push(h("span", { class: "tag moved" }, "déplacé dans la séquence"));
        if (u.moved_from) tags.push(h("span", { class: "tag moved" }, `déplacé depuis la séq. ${u.moved_from}`));
        if (u.moved_to) tags.push(h("span", { class: "tag moved" }, `déplacé vers la séq. ${u.moved_to}`));
        if (u.reassigned) tags.push(h("span", { class: "tag modified" }, "réattribuée"));
        if (u.ext_changed) tags.push(h("span", { class: "tag modified" }, "extension modifiée"));
        if (u.minor) tags.push(h("span", { class: "tag" }, "ponctuation / casse"));
        if (u.words_add || u.words_del) tags.push(h("span", { class: "small" }, h("span", { class: "plus" }, u.words_add ? `+${u.words_add}` : ""), " ", h("span", { class: "minus" }, u.words_del ? `−${u.words_del}` : "")));
      }
      const meta = h("div", { class: "kind-meta" }, kindLabel, tags);
      const who = (name, ext) => (u.kind === "dialogue" ? h("div", { class: "who" }, name, ext ? ` (${ext})` : "") : null);
      const aName = u.character_a || u.character;
      const aExt = u.ext_changed ? u.extension_a : u.extension;
      const hasA = u.status !== "added" || !!u.text_a;
      const hasB = u.status !== "deleted";
      const textA = u.text_a !== undefined ? u.text_a : u.text;

      if (state.mode === "unified") {
        let whoEl = null;
        if (u.kind === "dialogue") {
          whoEl = aName !== u.character || u.ext_changed
            ? h("div", { class: "who" }, h("del", {}, aName, aExt ? ` (${aExt})` : ""), " ", h("ins", {}, u.character, u.extension ? ` (${u.extension})` : ""))
            : who(u.character, u.extension);
        }
        const bodyEl = u.diff ? segsUnified(u.diff) : u.text;
        return h("div", { class: `u ${st} ${u.kind}` }, h("div", { class: "side" }, meta, whoEl, h("div", { class: "body" }, bodyEl)));
      }
      const left = hasA
        ? h("div", { class: "side side-a" }, meta, who(aName, aExt), h("div", { class: "body" }, u.diff ? segsSide(u.diff, "a") : textA))
        : h("div", { class: "side side-a empty" });
      const right = hasB
        ? h("div", { class: "side side-b" }, hasA ? h("div", { class: "kind-meta" }, " ") : meta, who(u.character, u.extension), h("div", { class: "body" }, u.diff ? segsSide(u.diff, "b") : u.text))
        : h("div", { class: "side side-b empty" });
      return h("div", { class: `u ${st} ${u.kind}` }, left, right);
    }

    function renderCharactersTab() {
      const maxW = Math.max(1, ...data.characters.map((c) => c.words_add + c.words_del));
      const rows = data.characters.map((c) => {
        const st = [];
        if (c.status === "new") st.push(h("span", { class: "tag added" }, c.renamed_from ? `renommé (ex-${c.renamed_from})` : "nouveau"));
        if (c.status === "removed") st.push(h("span", { class: "tag deleted" }, c.renamed_to ? `renommé en ${c.renamed_to}` : "disparu"));
        const bar = h("div", { class: "bar" }, h("span", { class: "b-add" }), h("span", { class: "b-del" }));
        bar.children[0].style.width = `${(c.words_add / maxW) * 100}%`;
        bar.children[1].style.width = `${(c.words_del / maxW) * 100}%`;
        return h("tr", {},
          h("td", {}, h("a", { href: "#", onclick: (e) => { e.preventDefault(); state.character = c.name; state.tab = "scenes"; renderTab(); } }, c.name), " ", st),
          h("td", { class: "num" }, fmt(c.a.lines)), h("td", { class: "num" }, fmt(c.b.lines)), h("td", { class: "num" }, deltaSpan(c.b.lines - c.a.lines)),
          h("td", { class: "num" }, fmt(c.a.words)), h("td", { class: "num" }, fmt(c.b.words)), h("td", { class: "num" }, deltaSpan(c.b.words - c.a.words)),
          h("td", { class: "num" }, fmt(c.a.scenes)), h("td", { class: "num" }, fmt(c.b.scenes)),
          h("td", { class: "num small" }, h("span", { class: "plus" }, `+${c.lines_added}`), " ", h("span", { class: "minus" }, `−${c.lines_deleted}`), ` ~${c.lines_modified}`),
          h("td", {}, h("div", { class: "row" }, bar, h("span", { class: "small nowrap" }, h("span", { class: "plus" }, `+${c.words_add}`), " ", h("span", { class: "minus" }, `−${c.words_del}`)))));
      });
      body.replaceChildren(
        h("p", { class: "muted small" }, "Cliquez sur un personnage pour n'afficher que ses répliques modifiées."),
        h("div", { class: "card table-wrap" }, h("table", { class: "data" },
          h("thead", {}, h("tr", {}, ["Personnage", "Répl. A", "Répl. B", "Δ", "Mots A", "Mots B", "Δ", "Séq. A", "Séq. B", "Répliques + − ~", "Mots ajoutés / supprimés"].map((t, i) => h("th", { class: i && i < 10 ? "num" : "" }, t)))),
          h("tbody", {}, rows))));
    }

    function renderStructureTab() {
      const maxWords = Math.max(1, ...data.scenes.map((x) => x.units.reduce((n, u) => n + (u.text || "").length, 0)));
      const strip = h("div", { class: "structure" }, data.scenes.map((scn) => {
        const len = scn.units.reduce((n, u) => n + (u.text || "").length, 0);
        const a = h("a", { href: "#", class: `s-${scn.status}${scn.moved ? " s-moved" : ""}`, title: `${sceneNum(scn)} — ${sceneTitle(scn)} (${scn.status})`,
          onclick: (e) => { e.preventDefault(); state.tab = "scenes"; state.statuses.add(scn.status); if (scn.moved) state.statuses.add("moved"); renderTab(); setTimeout(() => document.getElementById(`scene-${scn.id}`)?.scrollIntoView(), 30); } });
        a.style.width = `${6 + Math.round((len / maxWords) * 60)}px`;
        return a;
      }));
      const listOf = (title, items, fn) => items.length ? [h("h3", {}, `${title} (${items.length})`), h("ul", {}, items.map((x) => h("li", {}, fn(x))))] : [];
      const moved = data.scenes.filter((x) => x.moved);
      const added = data.scenes.filter((x) => x.status === "added");
      const deleted = data.scenes.filter((x) => x.status === "deleted");
      const headings = data.scenes.filter((x) => x.heading_changed);
      body.replaceChildren(
        h("p", { class: "muted small" }, "Chaque bloc représente une séquence dans l'ordre de la version B (les séquences supprimées sont insérées à leur ancienne place). La largeur est proportionnelle à la longueur."),
        h("div", { class: "legend" }, h("span", {}, h("i"), "inchangée"), h("span", {}, h("i", { class: "s-modified" }), "modifiée"), h("span", {}, h("i", { class: "s-added" }), "ajoutée"), h("span", {}, h("i", { class: "s-deleted" }), "supprimée"), h("span", {}, h("i", { class: "s-moved" }), "déplacée")),
        h("div", { class: "card" }, strip),
        h("div", { class: "card" },
          listOf("Séquences déplacées", moved, (x) => `${sceneTitle(x)} — séq. ${x.label_a} (A) → séq. ${x.label_b} (B)`),
          listOf("Séquences ajoutées", added, (x) => `Séq. ${x.label_b} — ${x.heading_b}`),
          listOf("Séquences supprimées", deleted, (x) => `Séq. ${x.label_a} — ${x.heading_a}`),
          listOf("Entêtes modifiés", headings, (x) => h("span", {}, `Séq. ${x.label_b} : `, segsUnified(x.heading_diff))),
          !moved.length && !added.length && !deleted.length && !headings.length ? h("p", { class: "muted" }, "La structure (ordre et liste des séquences) est inchangée.") : null));
    }

    renderTab();

    // Raccourcis clavier j / k
    const onKey = (e) => {
      if (!document.body.contains(body)) { document.removeEventListener("keydown", onKey); return; }
      if (state.tab !== "scenes" || /INPUT|SELECT|TEXTAREA/.test(document.activeElement?.tagName)) return;
      if (e.key !== "j" && e.key !== "k") return;
      const secs = [...body.querySelectorAll("section.scene")];
      const y = 140;
      const idx = secs.findIndex((s) => s.getBoundingClientRect().top > y + 5);
      let target;
      if (e.key === "j") target = idx === -1 ? null : secs[idx];
      else {
        const cur = idx === -1 ? secs.length : idx;
        target = secs[Math.max(0, cur - 2)];
        if (cur - 1 >= 0 && secs[cur - 1].getBoundingClientRect().top < y - 5) target = secs[cur - 1];
      }
      target?.scrollIntoView({ behavior: "smooth" });
    };
    document.addEventListener("keydown", onKey);
  }

  function sceneNum(scn) {
    if (scn.prologue) return "—";
    if (scn.label_a && scn.label_b && scn.label_a !== scn.label_b) return `${scn.label_a}→${scn.label_b}`;
    return scn.label_b || scn.label_a;
  }
  function sceneTitle(scn) {
    return scn.prologue ? "Ouverture" : scn.heading_b ?? scn.heading_a ?? "";
  }
  function deltaSpan(n) {
    if (!n) return h("span", { class: "muted" }, "=");
    return h("span", { class: n > 0 ? "plus" : "minus" }, signed(n));
  }
  function segsUnified(segs) {
    return segs.map(([op, a, b]) => (op === "=" ? b : op === "-" ? h("del", {}, a) : h("ins", {}, b)));
  }
  function segsSide(segs, side) {
    const out = [];
    for (const [op, a, b] of segs) {
      if (op === "=") out.push(side === "a" ? a : b);
      else if (op === "-" && side === "a") out.push(h("del", {}, a));
      else if (op === "+" && side === "b") out.push(h("ins", {}, b));
    }
    return out;
  }

  // ------------------------------------------------------------------ comparaison rapide
  function viewQuick() {
    const files = { a: null, b: null };
    const labels = { a: h("div", { class: "small muted" }, "Aucun fichier"), b: h("div", { class: "small muted" }, "Aucun fichier") };
    const opts = { ignore_case: false, ignore_punct: false, normalize_typo: true };
    const result = h("div");
    const mkZone = (k, title) => h("div", { class: "card stack" }, h("h3", {}, title),
      dropzone({ label: `Choisir la version ${k.toUpperCase()}`, accept: ACCEPT, onFiles: (fs) => { files[k] = fs[0]; labels[k].textContent = fs[0].name; labels[k].className = "small"; } }), labels[k]);
    const form = (format) => {
      const fd = new FormData();
      fd.append("file_a", files.a);
      fd.append("file_b", files.b);
      for (const k of OPT_KEYS) fd.append(k, String(opts[k]));
      fd.append("format", format);
      return fd;
    };
    async function run() {
      if (!files.a || !files.b) return toast("Choisissez deux fichiers.", true);
      result.replaceChildren(h("p", { class: "muted" }, "Comparaison en cours…"));
      try {
        const data = await uploadXHR("/api/quick-compare", form("json"));
        const exp = (format, label) => h("button", { onclick: async () => {
          try {
            const res = await fetch("/api/quick-compare", { method: "POST", body: form(format) });
            if (!res.ok) throw new Error(`Erreur ${res.status}`);
            downloadBlob(await res.blob(), `comparaison.${format}`);
          } catch (err) { toast(err.message, true); }
        } }, label);
        const holder = document.createElement("div");
        renderCompare(data, {
          opts,
          mount: (...nodes) => holder.replaceChildren(...nodes.flat(Infinity).filter(Boolean)),
          onOptions: (o) => { Object.assign(opts, o); run(); },
          exports: [exp("html", "Rapport HTML"), exp("csv", "CSV (tableur)")],
        });
        result.replaceChildren(holder);
      } catch (err) {
        result.replaceChildren(h("div", { class: "error-box" }, err.message));
      }
    }
    setView(
      h("h1", {}, "Comparaison rapide"),
      h("p", { class: "muted" }, "Comparez deux fichiers sans les enregistrer : ils sont analysés en mémoire sur le serveur puis oubliés."),
      h("div", { class: "grid" }, mkZone("a", "Version A (ancienne)"), mkZone("b", "Version B (nouvelle)")),
      h("p", {}, h("button", { class: "primary", onclick: run }, "Comparer")),
      result);
  }

  // ------------------------------------------------------------------ aide
  function viewHelp() {
    setView(h("div", { class: "help card" },
      h("h1", {}, "Aide"),
      h("h2", {}, "Formats acceptés"),
      h("ul", {},
        h("li", {}, h("strong", {}, "Final Draft (.fdx)"), " — le plus fiable : les types d'éléments sont lus directement."),
        h("li", {}, h("strong", {}, "Fountain (.fountain, .spmd)"), " — format texte des logiciels Highland, Slugline, Fade In, WriterDuet, Beat…"),
        h("li", {}, h("strong", {}, "Word (.docx) / OpenDocument (.odt)"), " — les styles de scénario (Séquence, Personnage, Dialogue…) sont utilisés s'ils existent ; sinon la mise en forme est devinée. Les modifications suivies sont lues dans leur état final."),
        h("li", {}, h("strong", {}, "PDF"), " — le texte est extrait en conservant la mise en page ; entêtes/pieds de page, numéros de page et mentions (SUITE) sont retirés. Les PDF scannés (images) ne sont pas lisibles."),
        h("li", {}, h("strong", {}, "Texte (.txt)"), " — export texte d'un logiciel de scénario.")),
      h("p", {}, "Après import, ouvrez la version pour vérifier le « texte analysé » : si des personnages ou entêtes sont mal reconnus, préférez un export FDX ou Fountain."),
      h("h2", {}, "Ce qui est détecté"),
      h("ul", {},
        h("li", {}, "Séquences ajoutées, supprimées, modifiées, déplacées (changement d'ordre), entêtes modifiés (lieu, moment), renumérotation."),
        h("li", {}, "Répliques ajoutées, supprimées, modifiées (mot à mot), réattribuées à un autre personnage, extension changée (OFF, V.O.)."),
        h("li", {}, "Actions/didascalies ajoutées, supprimées, modifiées ; transitions."),
        h("li", {}, "Éléments déplacés à l'intérieur d'une séquence ou d'une séquence à une autre."),
        h("li", {}, "Personnages : apparus, disparus, renommages probables, évolution du nombre de répliques et de mots."),
        h("li", {}, "Changements mineurs (ponctuation, casse) signalés et masquables.")),
      h("h2", {}, "Options de comparaison"),
      h("ul", {},
        h("li", {}, h("strong", {}, "Ignorer la casse"), " : « Bonjour » = « BONJOUR »."),
        h("li", {}, h("strong", {}, "Ignorer la ponctuation"), " : les virgules, points, tirets… ne comptent plus."),
        h("li", {}, h("strong", {}, "Normaliser la typographie"), " (activé par défaut) : apostrophes courbes/droites, guillemets « » / \" \", points de suspension, espaces insécables, tirets.")),
      h("p", {}, "Les retours à la ligne et les espaces multiples ne sont jamais considérés comme des changements."),
      h("h2", {}, "Confidentialité"),
      h("p", {}, "L'application fonctionne entièrement sur votre NAS : aucune police, bibliothèque ou statistique n'est chargée depuis Internet, et le serveur n'effectue aucune requête sortante. Les fichiers sont stockés dans le dossier de données du NAS (sous-dossier files/) et la base SQLite scenario.db."),
      h("h2", {}, "Raccourcis"),
      h("p", {}, h("span", { class: "kbd" }, "j"), " / ", h("span", { class: "kbd" }, "k"), " : séquence suivante / précédente dans une comparaison. Cliquer sur l'entête d'une séquence la replie.")));
  }

  route();
})();
