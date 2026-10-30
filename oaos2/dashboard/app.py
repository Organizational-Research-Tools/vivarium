"""Serve the local dashboard for run inspection, annotation, and launch setup.

Read routes build views from saved runs and library settings. Write routes save
researcher annotations, edit library YAML, and dispatch launches through the
workbench. They do not rewrite trace files. scripts/dashboard.py binds to
127.0.0.1, so the browser connects on the same machine.
Requires the dashboard extra. See docs/DASHBOARD.md for routes and operation."""

from __future__ import annotations

import gzip
import json
import re
import threading
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from oaos2.archive import cite as citelib
from oaos2.archive import design as designlib
from oaos2.archive import exchanges as exchangelib
from oaos2.archive import work as worklib
from oaos2.archive.renderers import derived_renderer_for, task_pack_id_of
from oaos2.dashboard import agents as agentlib
from oaos2.dashboard import live as livelib
from oaos2.dashboard import organization as orglib
from oaos2.archive.clock import day_index
from oaos2.archive.items import build_items
from oaos2.archive.renderers import registered_filenames
from oaos2.dashboard import annotate, attention, cases, crosscell, diagnostics, frozen, ledger, provenance, workbench
from oaos2.dashboard import events as ev
from oaos2.dashboard import removal, renderers, store, studies as studylib
from oaos2.dashboard.cache import RegistryCache
from oaos2.dashboard.reports import ReportStore
from oaos2.dashboard.search import SearchIndex
from oaos2.pricing.ledger import validate_spending_cap

# Status → (status-role, glyph). Color is role-based and never alone: the chip
# always pairs glyph + label text (dataviz status rule).
STATUS_CHIP = {
    "passed": ("good", "✓"),
    "completed": ("neutral", "○"),
    "failed_score": ("neutral", "✕"),   # a valid scored outcome, not an error
    "unscored": ("warning", "○"),
    "invalid_archive": ("critical", "!"),
    "run_failed": ("critical", "✕"),
    "stalled": ("serious", "◷"),
    "incomplete": ("serious", "…"),
    "idle": ("serious", "⏸"),
    "empty": ("muted", "∅"),
}

# The only files servable from a run's derived/ slot — the foundation's closed
# list plus whatever report filenames packs have REGISTERED (archive/renderers)
# and their error records, so the file-serving route can never be steered at
# anything else and no pack filename is named here.
_DERIVED_WHITELIST = frozenset({"clean.txt", "full.txt", "agent_centric.txt",
                                "file_lineage.txt", "metrics.json", "RENDER_ERROR.txt"})


def _derived_servable(name: str) -> bool:
    if name in _DERIVED_WHITELIST or name in registered_filenames():
        return True
    return (name.startswith("RENDER_ERROR.") and name.endswith(".txt")
            and name[len("RENDER_ERROR."):-len(".txt")] in registered_filenames())


_REGISTRY_OUTCOMES = frozenset({
    "passed", "partial_score", "scored", "retained_fraction", "n_repaired", "outcome",
    "n_unresolved", "n_covered_unhandled", "n_choice_wrong", "n_choice_undetermined",
})


def _registry_reading_rows(rows: list[dict], *, blind: bool = False,
                           experiment: str | None = None, lineage: str | None = None):
    """Choose blinding before outcome/status filters, then remove verdicts.

    A completed arm must stay blind while another arm in its experiment is
    running. The same rows feed HTML, facets, aggregates, and the CSV export.
    This does not restrict deliberate access to the underlying local archive.
    """
    scope = store.filter_rows(rows, experiment=experiment, lineage=lineage)
    blind = bool(blind) or any(r.get("mode") == "confirmatory"
                              and r.get("status") == "incomplete" for r in scope)
    if not blind:
        return rows, False
    safe = []
    for row in rows:
        safe.append({**row, **{field: None for field in _REGISTRY_OUTCOMES},
                     "status": "completed" if row.get("status") in ("passed", "failed_score")
                     else row.get("status")})
    return safe, True


def _declared_studies() -> list[dict]:
    return studylib.load_studies(provenance.library_dir() / "studies.yaml")


def _study_documents() -> dict[str, Path]:
    """Current study index, preregistrations, and results from the repository.

    This bounded catalogue supplies both the links and the read-route allowlist.
    It never resolves a browser-supplied filesystem path.
    """
    root = Path(__file__).resolve().parents[2] / "docs" / "experiments"
    evidence = Path(__file__).resolve().parents[2] / "library" / "experiments" / "evidence"
    candidates = [root / "README.md", *root.glob("*prereg*.md"), *root.glob("*results*.md"),
                  # the studies' designs and their coding documents
                  *root.glob("*design*.md"), *root.glob("*cod*.md")]
    # A study's declared record is servable too; the name comes from the library file.
    candidates += [root / st["record"] for st in _declared_studies() if st.get("record")]
    roots = {root.resolve(), evidence.resolve()}
    return {p.name: p for p in sorted(set(candidates))
            if p.is_file() and p.resolve().parent in roots}


# Host names that address this computer; "testserver" is the test client's.
LOCAL_HOSTS = frozenset({"127.0.0.1", "localhost", "[::1]", "testserver"})


def _host_name(netloc: str) -> str:
    """The host of a Host header or URL netloc, without the port (``[::1]:8722`` -> ``[::1]``)."""
    netloc = netloc.strip().lower()
    if netloc.startswith("["):
        return netloc[: netloc.find("]") + 1]
    return netloc.split(":", 1)[0]


def _inside(run_dir: Path, path: Path) -> bool:
    """Whether ``path``, with any symbolic link followed, still lies inside ``run_dir`` (an archive from elsewhere
    may hold a link that points out of it; security audit, October 29, 2026)."""
    try:
        path.resolve().relative_to(Path(run_dir).resolve())
    except (OSError, ValueError):
        return False
    return True


def create_app(runs_root: Path) -> FastAPI:
    runs_root = Path(runs_root)
    from oaos2.dashboard import glossary
    app = FastAPI(title="oaos2 dashboard", docs_url=None, redoc_url=None)
    app.add_middleware(GZipMiddleware, minimum_size=4096)  # a flow page is ~15× smaller gzipped

    @app.middleware("http")
    async def _this_computer_only(request: Request, call_next):
        """The dashboard serves only this computer (security audit, October 29, 2026): a request must name a local
        host, which defeats DNS rebinding, and a request that changes something must not come from another site's
        page (a browser's Origin or Referer naming a host other than the local one is refused)."""
        if _host_name(request.headers.get("host", "")) not in LOCAL_HOSTS:
            return PlainTextResponse("refused: the dashboard serves only this computer", status_code=403)
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            source = request.headers.get("origin") or request.headers.get("referer")
            if source and _host_name(urlsplit(source).netloc) not in LOCAL_HOSTS:
                return PlainTextResponse("refused: a request from another site's page", status_code=403)
        return await call_next(request)
    templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
    templates.env.globals["STATUS_CHIP"] = STATUS_CHIP
    templates.env.globals["PROVENANCE_CHIP"] = provenance.PROVENANCE_CHIP
    templates.env.globals["GLOSSARY"] = glossary.GLOSSARY
    templates.env.globals["STATUS_HELP"] = glossary.STATUS_HELP
    templates.env.globals["PROVENANCE_HELP"] = glossary.PROVENANCE_HELP
    templates.env.globals["SEVERITY_HELP"] = glossary.SEVERITY_HELP
    cache = RegistryCache(runs_root)
    reports = ReportStore(runs_root)
    search_index = SearchIndex(runs_root)

    def run_tabs(run_ref: str) -> dict:
        """The run-dependent tabs of the rail: Days only for a clocked run; the work
        tab under the pack's registered label, else the case dossier."""
        run_dir = store.resolve_run_dir(runs_root, run_ref)
        manifest = store._read_json(run_dir / "manifest.json") if run_dir else None
        ext = (manifest or {}).get("extensions") or {}
        adapter = worklib.work_adapter_for((manifest or {}).get("task_pack_id"))
        work = ({"label": adapter.label, "href": f"/run/{run_ref}/work"} if adapter
                else {"label": "Cases", "href": f"/run/{run_ref}/cases"})
        # Live only for a run that may still be written: the same reading as the /live
        # list (not finalized, no terminal event, not idle); the page itself still
        # opens for any run.
        unfinished = bool(run_dir) and livelib.is_unfinished(
            run_dir, idle_after_s=store.IDLE_AFTER_HOURS * 3600)
        return {"has_clock": bool(ext.get("clock") or ext.get("clock_spec")), "work": work,
                "has_live": unfinished}

    templates.env.globals["run_tabs"] = run_tabs

    def verdict_note(pack_id: str | None) -> str:
        """The pack's one-line statement of what its pass/fail counts, if it gives one."""
        renderer = derived_renderer_for(pack_id) if pack_id else None
        return getattr(renderer, "verdict_note", "") or ""

    templates.env.globals["verdict_note"] = verdict_note

    def depth_label(depth: str, has_board: bool) -> str:
        """The Story/Live depth names. The first level is the board's posts only when the
        run had a board; otherwise it holds milestones, lifecycle and problems."""
        return {"forum": "the forum" if has_board else "milestones only",
                "notes": "+ notes, handoffs, notices", "said": "+ what agents said",
                "everything": "+ tools and thinking"}.get(depth, depth)

    templates.env.globals["depth_label"] = depth_label

    def had_board(run_dir: Path, events: list[dict]) -> bool:
        """Whether the run had a board: someone posted, or a role was granted posting."""
        if any(e.get("event_class") == "board.posted" for e in events):
            return True
        manifest = store._read_json(run_dir / "manifest.json") or {}
        roles = designlib.organization_of(manifest)["roles"]
        return any("post" in (r.get("comm_grants") or []) for r in roles.values())

    def _detail(run_dir: Path, events: list[dict]) -> dict:
        return store.run_detail(run_dir, events, reports=reports)

    def _fmt_usd(v) -> str:
        return "" if v is None else f"${v:,.2f}"

    def _fmt_score(v) -> str:
        return "" if v is None else f"{v:.3f}"

    def _shortid(s, n: int = 30) -> str:
        s = str(s or "")
        return s if len(s) <= n else s[: n - 12] + "…" + s[-11:]

    templates.env.filters["usd"] = _fmt_usd

    def _fmt_usd_lb(v, n_unknown=0) -> str:
        """Cost, marked as a lower bound when some model calls ended with unknown usage."""
        text = _fmt_usd(v) if v is not None else "—"
        return f"≥ {text}" if n_unknown else text

    templates.env.filters["usd_lb"] = _fmt_usd_lb
    templates.env.filters["score"] = _fmt_score
    templates.env.filters["shortid"] = _shortid

    def _wbr(text) -> str:
        """Escaped text that may wrap after underscores (long run and lineage names)."""
        from markupsafe import Markup, escape
        return Markup(str(escape(str(text or ""))).replace("_", "_<wbr>"))

    templates.env.filters["wbr"] = _wbr

    def _rows(rebuild: bool = False) -> list[dict]:
        rows = provenance.annotate_rows(store.list_runs(runs_root, cache=cache, rebuild=rebuild))
        declared = _declared_studies()
        for r in rows:
            r["study"] = (studylib.study_of(r.get("lineage"), declared) or {}).get("id")
            r["started"] = _run_time(r)
            r["started_label"] = _when(r["started"])
            r["left_out"] = frozen.left_out_of_dataset(Path(r["run_dir"]).name if r.get("run_dir") else None)
            r["eligibility"] = _with_dataset(r.get("eligibility"), frozen.frozen_for(r.get("run_id")),
                                             r["left_out"])
        return rows

    async def _form(request: Request):
        """Read the dashboard's simple URL-encoded forms without an optional parser.

        Starlette delegates even application/x-www-form-urlencoded bodies to
        python-multipart.  The dashboard extra declares it, but read/launch UI
        should not fail merely because a minimal local venv omitted that extra.
        Multipart requests still use Starlette's normal parser.
        """
        content_type = request.headers.get("content-type", "").split(";", 1)[0]
        if content_type == "application/x-www-form-urlencoded":
            parsed = parse_qs((await request.body()).decode("utf-8"), keep_blank_values=True)
            return {key: values[-1] for key, values in parsed.items()}
        return await request.form()

    @app.get("/", response_class=HTMLResponse)
    def overview_page(request: Request):
        """Integrated plain-language front door plus a live archive snapshot."""
        if request.url.query:  # preserve old filtered-registry bookmarks
            return RedirectResponse(f"/runs?{request.url.query}", status_code=307)
        rows = _rows()
        # every run, newest first: the page filters, sorts and pages them in place
        recent = sorted(rows, key=lambda r: (r.get("started") or 0.0, _row_recency(r)), reverse=True)
        lib = workbench.list_library()
        return templates.TemplateResponse(request, "guide.html", {
            "rows": rows, "recent": recent, "tiles": _tiles(rows),
            "lineages": sorted({r.get("lineage") for r in rows if r.get("lineage")}),
            "packs": sorted({r.get("task_pack_id") for r in rows if r.get("task_pack_id")}),
            "n_designs": len(lib["experiments"]),
            "in_flight_n": sum(1 for r in rows if r.get("status") == "incomplete"),
            "current_n": sum(1 for r in rows if r.get("provenance") == "current"),
        })

    @app.get("/runs", response_class=HTMLResponse)
    def runs_page(request: Request, status: str | None = None, experiment: str | None = None,
                  organization: str | None = None, model: str | None = None,
                  difficulty: str | None = None, mode: str | None = None,
                  clock: str | None = None, prov: str | None = None, lineage: str | None = None,
                  q: str | None = None, rebuild: bool = False, blind: int = 0,
                  scope: str | None = None, attn: int = 0, flat: int = 0,
                  study: str | None = None, sort: str = "newest", group: int = 1):
        asked_blind = bool(blind)
        rows, blind = _registry_reading_rows(_rows(rebuild), blind=bool(blind),
                                            experiment=experiment, lineage=lineage)
        if blind and status in ("passed", "failed_score"):
            status = "completed"
        scope = scope if scope in SCOPES else None
        # Say which open confirmatory runs force the blind reading, so an abandoned run is visible.
        holding = ([] if asked_blind or not blind else
                   [r for r in store.filter_rows(rows, experiment=experiment, lineage=lineage)
                    if r.get("mode") == "confirmatory" and r.get("status") == "incomplete"])
        active = {"status": status, "lineage": lineage, "experiment": experiment,
                  "organization": organization, "model": model, "difficulty": difficulty,
                  "mode": mode, "clock": clock}
        filtered = store.filter_rows(rows, q=q, **active)
        if prov:
            filtered = [r for r in filtered if r.get("provenance") == prov]
        if scope:
            filtered = [r for r in filtered if r.get("mode") in SCOPES[scope]]
        if study:
            filtered = [r for r in filtered if r.get("study") == study]
        for r in filtered:
            r["attention"] = attention.row_attention(r)
        if attn:
            filtered = [r for r in filtered if r["attention"]]
        sort = sort if sort in SORTS else "newest"
        filtered = sorted(filtered, key=SORTS[sort][0], reverse=SORTS[sort][1])
        # Facets describe the lineage or experiment being read, so the menus stay short.
        facet_rows = store.filter_rows(rows, lineage=lineage, experiment=experiment)
        facets = store.facet_values(facet_rows)
        facets["prov"] = sorted({r.get("provenance") for r in facet_rows if r.get("provenance")})
        narrowed = any(active.values()) or bool(prov or q or attn or study)
        index = not narrowed and not flat and len(filtered) > INDEX_THRESHOLD
        designs = [d for d in workbench.list_library()["experiments"] if "error" not in d]
        return templates.TemplateResponse(request, "runs.html", {
            "blind": blind,
            "view_url": request.url.include_query_params(status=status or "", blind=1 if blind else 0),
            "runs_root": str(runs_root),
            "rows": filtered,
            "groups": _experiment_groups(filtered) if group else [{"stem": None, "runs": [{"row": r}]}
                                                                  for r in filtered],
            "group": bool(group),
            "n_total": len(rows),
            "facets": facets,  # facets over ALL rows, not the filtered view
            "active": {**active, "prov": prov, "study": study}, "q": q or "",
            "arms": store.arm_summary(filtered) if (lineage or experiment) else [],
            "tiles": {**_tiles(filtered), "attention": sum(1 for r in filtered if r["attention"])},
            "sections": _mode_sections(filtered, designs, _study_documents()),
            "lineage_index": (_study_index(_lineage_index(filtered, designs, _study_documents()),
                                           _declared_studies(), _study_documents()) if index else None),
            "single_lineage": bool(lineage or experiment or study),
            "scope": scope, "attn": bool(attn), "study": study, "sort": sort,
            "n_lineages": len({r.get("lineage") for r in filtered}),
            "lineage_head": (_lineage_groups(filtered, designs, _study_documents())[0]
                             if lineage and filtered else None),
            "studies": [st for st in _declared_studies() if any(r.get("study") == st["id"] for r in rows)],
            "blind_held_by": sorted({r.get("lineage") or "—" for r in holding}), "blind_held_n": len(holding),
        })

    @app.get("/study-records", response_class=HTMLResponse)
    def study_records_page(request: Request):
        records = [{"name": name, "title": path.read_text().splitlines()[0].lstrip("# ")}
                   for name, path in _study_documents().items()]
        return templates.TemplateResponse(request, "study_records.html", {"records": records})

    @app.get("/study-records/{name}", response_class=HTMLResponse)
    def study_record_page(request: Request, name: str):
        path = _study_documents().get(name)
        if path is None:
            raise HTTPException(404)
        return templates.TemplateResponse(request, "study_record.html", {
            "name": name, "content": path.read_text(),
        })

    @app.get("/registry.csv")
    def registry_csv(status: str | None = None, experiment: str | None = None,
                     organization: str | None = None, model: str | None = None,
                     difficulty: str | None = None, mode: str | None = None,
                     clock: str | None = None, prov: str | None = None,
                     lineage: str | None = None, q: str | None = None, blind: int = 0,
                     study: str | None = None):
        import csv
        import io
        rows, blind = _registry_reading_rows(_rows(), blind=bool(blind),
                                            experiment=experiment, lineage=lineage)
        if blind and status in ("passed", "failed_score"):
            status = "completed"
        rows = store.filter_rows(rows, q=q, status=status, experiment=experiment,
                                 organization=organization, model=model, difficulty=difficulty,
                                 mode=mode, clock=clock, lineage=lineage)
        if prov:
            rows = [r for r in rows if r.get("provenance") == prov]
        if study:  # the same study filter as the runs page
            rows = [r for r in rows if r.get("study") == study]
        buf = io.StringIO()
        if rows:
            fields = [k for k in rows[0] if k != "provenance_reasons"]
            w = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
            w.writeheader()
            for r in rows:
                w.writerow({k: (";".join(v) if isinstance(v, list) else v)
                            for k, v in r.items() if k in fields})
        return Response(buf.getvalue(), media_type="text/csv")

    @app.get("/experiment/{experiment_id}/cases", response_class=HTMLResponse)
    def experiment_cases_page(request: Request, experiment_id: str, by: str = "arm",
                              mode: str = "open"):
        rows = [r for r in _rows() if r.get("experiment_id") == experiment_id]
        if not rows:
            raise HTTPException(404)
        m = crosscell.matrix(rows, reports, by="rep" if by == "rep" else "arm")
        return templates.TemplateResponse(request, "crosscell.html", {
            "experiment_id": experiment_id, "m": m, "by": "rep" if by == "rep" else "arm",
            "blind": mode == "blind",
        })

    @app.get("/experiment/{experiment_id}", response_class=HTMLResponse)
    def experiment_page(request: Request, experiment_id: str):
        rows = [r for r in _rows() if r.get("experiment_id") == experiment_id]
        if not rows:
            raise HTTPException(404)
        designs = [d for d in workbench.list_library()["experiments"] if "error" not in d]
        design = _design_for([experiment_id], designs)
        prereg_ref, prereg_href = _prereg_link(design, _study_documents())
        modes = sorted({r.get("mode") or "none" for r in rows})
        return templates.TemplateResponse(request, "experiment.html", {
            "experiment_id": experiment_id,
            "pivot": _experiment_pivot(rows),
            "rows": rows,
            "tiles": _tiles(rows),
            "evidence": frozen.evidence_for({r.get("run_id") for r in rows if r.get("run_id")}),
            "modes": modes, "registered": all(m in REGISTERED_MODES for m in modes),
            "material_versions": attention.material_versions(rows),
            "n_attention": sum(1 for r in rows if attention.row_attention(r)),
            "design": (design or {}).get("name"), "prereg_ref": prereg_ref, "prereg_href": prereg_href,
        })

    # Registered before the run page: {run_ref:path} is greedy, order decides.
    @app.get("/run/{run_ref:path}/derived/{name}", response_class=PlainTextResponse)
    def derived_file(run_ref: str, name: str):
        run_dir = store.resolve_run_dir(runs_root, run_ref)
        if run_dir is None or not _derived_servable(name):
            raise HTTPException(404)
        path = run_dir / "derived" / name
        if not path.exists() or not _inside(run_dir, path):
            raise HTTPException(404)
        return path.read_text()

    def _run_dir_or_404(run_ref: str) -> Path:
        run_dir = store.resolve_run_dir(runs_root, run_ref)
        if run_dir is None:
            raise HTTPException(404)
        return run_dir

    @app.get("/run/{run_ref:path}/trace", response_class=HTMLResponse)
    def trace_page(request: Request, run_ref: str, view: str = "clean",
                   agent: str | None = None, event_class: str | None = None,
                   family: str | None = None, channel: str | None = None,
                   audience: str | None = None, phase: str | None = None,
                   turn: str | None = None, q: str | None = None,
                   day: int | None = None, page: int = 1, page_size: int = 500):
        run_dir = _run_dir_or_404(run_ref)
        all_events = ev.load_events(run_dir)
        active = {"agent": agent, "event_class": event_class, "family": family,
                  "channel": channel, "audience": audience, "phase": phase, "turn": turn}
        filtered = ev.filter_events(all_events, q=q, **active)
        day_of = day_index(all_events)
        if day is not None and day_of:
            filtered = [e for e in filtered if day_of.get(e.get("event_id")) == day]
        rows = _trace_rows(run_dir, filtered, view)
        for r in rows:
            r["day"] = day_of.get(r["e"].get("event_id")) if day_of else None
        page_size = max(1, min(page_size, 2000))
        n_pages = max(1, -(-len(rows) // page_size))
        page = max(1, min(page, n_pages))
        return templates.TemplateResponse(request, "trace.html", {
            "run_ref": run_ref, "view": view if view in ("clean", "full") else "clean",
            "rows": rows[(page - 1) * page_size: page * page_size],
            "n_rows": len(rows), "n_events": len(all_events),
            "page": page, "n_pages": n_pages, "page_size": page_size,
            "facets": ev.facets(all_events), "active": active, "q": q or "",
            "days": sorted(set(day_of.values())) if day_of else [], "day": day,
            "ann": annotate.links_by_event(run_dir),  # margin marks (§4.7)
        })

    def _cell_label(run_dir: Path) -> str:
        """The condition a citation is read under: preset · tier · clock · rep, from the
        manifest — never from the run id's naming convention alone."""
        m = store._read_json(run_dir / "manifest.json") or {}
        ext = m.get("extensions") or {}
        parts = [m.get("organization_id"), ext.get("difficulty"),
                (ext.get("clock_spec") or ext.get("clock") or {}).get("schedule_variant")
                or ext.get("environment_schedule_variant")]
        rep = re.search(r"__rep(\d+)__", m.get("run_id") or "")
        if rep:
            parts.append(f"rep{rep.group(1)}")
        return " · ".join(str(p) for p in parts if p)

    @app.get("/run/{run_ref:path}/cite/submitted/{name}", response_class=PlainTextResponse)
    def cite_submitted(run_ref: str, name: str, quote: str = "", note: str = ""):
        run_dir = _run_dir_or_404(run_ref)
        if not re.fullmatch(r"[A-Za-z0-9_.\-]+", name):
            raise HTTPException(404)
        path = next((p for p in (run_dir / "captured" / "submitted" / name,
                                 run_dir / "submitted" / name) if p.is_file() and _inside(run_dir, p)), None)
        if path is None:
            raise HTTPException(404)
        citation = citelib.file_citation(run_ref, f"submitted/{name}", path.read_bytes())
        if not quote:
            return citation
        return citelib.excerpt_markdown(citation=citation, quote=quote,
                                        cell=_cell_label(run_dir), note=note)

    @app.get("/run/{run_ref:path}/cite/{event_id}", response_class=PlainTextResponse)
    def cite_event(run_ref: str, event_id: str, quote: str = "", note: str = ""):
        """The citation line for one event (plain text, copy-ready); with ``quote``,
        the excerpt block a reader pastes into a memo. No server is needed to
        resolve it later — scripts/cite.py does."""
        run_dir = _run_dir_or_404(run_ref)
        event = ev.event_index(run_dir).get(event_id)
        if event is None:
            raise HTTPException(404)
        day = day_index(ev.load_events(run_dir)).get(event_id)
        citation = citelib.event_citation(run_ref, event, day)
        if not quote:
            return citation
        return citelib.excerpt_markdown(citation=citation, quote=quote,
                                        cell=_cell_label(run_dir), note=note)

    @app.get("/run/{run_ref:path}/event/{event_id}", response_class=HTMLResponse)
    def event_page(request: Request, run_ref: str, event_id: str):
        run_dir = _run_dir_or_404(run_ref)
        by_id = ev.event_index(run_dir)
        event = by_id.get(event_id)
        if event is None:
            raise HTTPException(404)
        all_events = ev.load_events(run_dir)
        day = day_index(all_events).get(event_id)
        citation = citelib.event_citation(run_ref, event, day)
        children = ev.children_of(all_events, event_id)
        idx = next((i for i, x in enumerate(all_events)
                    if x.get("event_id") == event_id), None)
        prev_e = all_events[idx - 1] if idx else None
        next_e = all_events[idx + 1] if idx is not None and idx + 1 < len(all_events) else None
        return templates.TemplateResponse(request, "event.html", {
            "run_ref": run_ref, "e": event, "summary": ev.summary(event),
            "citation": citation, "day": day, "cell": _cell_label(run_dir),
            "prev_e": prev_e, "next_e": next_e,
            "notable": renderers.notable_text(run_dir, event),
            "payload_json": json.dumps(event.get("payload") or {}, indent=2, sort_keys=True),
            "parents": [(p, ev.summary(p)) for p in ev.parents_of(by_id, event)],
            "children": [(c, ev.summary(c)) for c in children[:50]],
            "n_children": len(children),
            "ancestry": [(d, a, ev.summary(a)) for d, a in ev.ancestry_outline(by_id, event_id)],
            "raw_digest": ev.raw_ref_digest(event),
            "schemas": annotate.load_schemas(runs_root),
            "links": annotate.links_by_event(run_dir).get(event_id, []),
        })

    @app.get("/run/{run_ref:path}/audit", response_class=HTMLResponse)
    def audit_page(request: Request, run_ref: str):
        run_dir = _run_dir_or_404(run_ref)
        all_events = ev.load_events(run_dir)
        trouble = [(e, ev.summary(e)) for e in all_events
                   if store.is_audit_class(e.get("event_class"))]
        interventions = [(e, ev.summary(e)) for e in all_events
                         if e.get("event_class") == "intervention.recorded"]
        cost_rows, cum = [], 0.0
        for e in all_events:
            if e.get("event_class") == "cost.recorded":
                c = (e.get("payload") or {}).get("cost_usd", 0.0) or 0.0
                cum += c
                cost_rows.append((e, c, cum))
        infra = {}
        for e in all_events:
            if e.get("channel") == "infrastructure" or e.get("audience") == "infrastructure":
                cls = e.get("event_class") or "?"
                infra[cls] = infra.get(cls, 0) + 1
        detail = _detail(run_dir, all_events)
        cap = ((detail["manifest"] or {}).get("extensions") or {}).get("cap_usd")
        return templates.TemplateResponse(request, "audit.html", {
            "run_ref": run_ref, "d": detail,
            "findings": diagnostics.diagnose(run_dir, all_events, detail),
            "trouble": trouble, "interventions": interventions,
            "cost_rows": cost_rows, "cost_total": cum,
            "cost_chart": _cost_chart(cost_rows, cap, all_events),
            "infra": dict(sorted(infra.items())),
        })

    @app.get("/run/{run_ref:path}/item/{event_id}", response_class=PlainTextResponse)
    def item_page(run_ref: str, event_id: str):
        """One flow item's full content — the fetch target behind "show all", so a
        page never inlines a lateral cell's half-megabyte of filing bodies."""
        run_dir = _run_dir_or_404(run_ref)
        event = ev.event_index(run_dir).get(event_id)
        if event is None:
            raise HTTPException(404)
        return ev.item_text(run_dir, event)

    @app.get("/run/{run_ref:path}/flow", response_class=HTMLResponse)
    def flow_page(request: Request, run_ref: str, level: str = "reasoning",
                  agent: str | None = None, day: int | None = None, page: int = 1):
        run_dir = _run_dir_or_404(run_ref)
        all_events = ev.load_events(run_dir)
        detail = _detail(run_dir, all_events)
        findings = diagnostics.diagnose(run_dir, all_events, detail)
        # finding lookup so a flow item can carry its diagnosis inline
        by_event: dict[str, dict] = {}
        for f in findings:
            for eid in f["event_ids"]:
                by_event.setdefault(eid, f)
        day_of = day_index(all_events)
        days = sorted({d for d in day_of.values()}) if day_of else []
        events = [e for e in all_events
                  if (not agent or e.get("agent_id") == agent)
                  and (day is None or day_of.get(e.get("event_id")) == day)]
        pack = task_pack_id_of(run_dir)
        items = ev.flow_items(run_dir, events, level,
                              milestones=exchangelib.milestone_rows(pack, all_events),
                              exchanges=exchangelib.exchange_rows(pack, all_events))
        for item in items:
            item["finding"] = by_event.get(item["e"].get("event_id"))
        groups = ev.flow_groups(items, day_of)
        # Pages: one per DAY on a clocked run (a page break lands between days,
        # never inside one); otherwise by turn-groups, never splitting a turn.
        if days and day is None:
            pages: list[list[dict]] = []
            for g in groups:
                if not pages or pages[-1][0]["day"] != g["day"]:
                    pages.append([g])
                else:
                    pages[-1].append(g)
        else:
            per_page = 120
            pages = [groups[i:i + per_page] for i in range(0, len(groups), per_page)] or [[]]
        n_pages = max(1, len(pages))
        page = max(1, min(page, n_pages))
        visible = pages[page - 1]
        visible_ids = {item["e"].get("event_id") for g in visible for item in g["items"]}
        return templates.TemplateResponse(request, "flow.html", {
            "run_ref": run_ref, "groups": visible,
            "level": level if level in ev.FLOW_LEVELS else "reasoning",
            "levels": ev.FLOW_LEVELS,
            "agent": agent or "", "agents": detail["metrics"].get("agents") or [],
            "agent_slot": agent_slot(detail["metrics"].get("agents") or []),
            "days": days, "day": day, "page_day": visible[0]["day"] if visible else None,
            "paged_by_day": bool(days and day is None),
            "n_items": len(items), "page": page, "n_pages": n_pages,
            "minimap": _flow_minimap(pages),
            "findings": [(f, f["event_ids"][0] if f["event_ids"] else None,
                          bool(set(f["event_ids"]) & visible_ids)) for f in findings],
        })

    @app.get("/run/{run_ref:path}/cases", response_class=HTMLResponse)
    def cases_page(request: Request, run_ref: str, lens: int = 0):
        run_dir = _run_dir_or_404(run_ref)
        all_events = ev.load_events(run_dir)
        detail = _detail(run_dir, all_events)
        idx = cases.cases_index(run_dir, all_events, detail["manifest"] or {}, detail["task_report"])
        return templates.TemplateResponse(request, "cases.html", {
            "run_ref": run_ref, "idx": idx, "lens": bool(lens),
            "report_meta": detail["task_report_meta"],
            "aslot": agent_slot(detail["metrics"].get("agents") or []),
        })

    @app.get("/run/{run_ref:path}/casebook.md", response_class=PlainTextResponse)
    def casebook_page(run_ref: str, mode: str = "blind"):
        run_dir = _run_dir_or_404(run_ref)
        all_events = ev.load_events(run_dir)
        detail = _detail(run_dir, all_events)
        return cases.casebook_markdown(run_dir, run_ref, all_events, detail["manifest"] or {},
                                       detail["task_report"], mode=mode)

    @app.get("/run/{run_ref:path}/case/{item_id}", response_class=HTMLResponse)
    def case_page(request: Request, run_ref: str, item_id: str, mode: str = "blind",
                  key: int = 0, lens: int = 0):
        run_dir = _run_dir_or_404(run_ref)
        all_events = ev.load_events(run_dir)
        detail = _detail(run_dir, all_events)
        dossier = cases.case_dossier(run_dir, run_ref, all_events, detail["manifest"] or {},
                                     detail["task_report"], item_id, mode=mode,
                                     reveal_key=bool(key), lens=bool(lens))
        if dossier is None:
            raise HTTPException(404)
        return templates.TemplateResponse(request, "case.html", {
            "run_ref": run_ref, "c": dossier, "item_id": item_id,
            "schemas": annotate.load_schemas(runs_root),
            "links": [ln for ln in annotate.links_for_run(run_dir)
                      if set(ln.get("event_ids") or []) & set(dossier["annotate_ids"])],
            "aslot": agent_slot(detail["metrics"].get("agents") or []),
        })

    @app.get("/run/{run_ref:path}/days", response_class=HTMLResponse)
    def days_page(request: Request, run_ref: str):
        run_dir = _run_dir_or_404(run_ref)
        all_events = ev.load_events(run_dir)
        detail = _detail(run_dir, all_events)
        manifest = detail["manifest"] or {}
        design = designlib.run_design(run_dir, manifest)
        items = build_items(run_dir, all_events, manifest=manifest, report=detail["task_report"])["items"]
        return templates.TemplateResponse(request, "days.html", {
            "run_ref": run_ref, "L": ledger.build_ledger(all_events, design, items),
            "aslot": agent_slot(detail["metrics"].get("agents") or []),
        })

    @app.get("/run/{run_ref:path}/design", response_class=HTMLResponse)
    def design_page(request: Request, run_ref: str):
        """Track A: the condition as realized for this run (archive/design.py)."""
        run_dir = _run_dir_or_404(run_ref)
        all_events = ev.load_events(run_dir)
        detail = _detail(run_dir, all_events)
        manifest = detail["manifest"] or {}
        design = designlib.run_design(run_dir, manifest)
        items = build_items(run_dir, all_events, manifest=manifest, report=detail["task_report"])["items"]
        real = designlib.realization(all_events, design, items)
        me = detail["record"]
        siblings = [r for r in _rows()
                    if r.get("experiment_id") == me.get("experiment_id")
                    and r.get("run_ref") != run_ref
                    and r.get("organization_id") != me.get("organization_id")
                    and designlib.cell_of({"run_id": r.get("run_id")})["rep"]
                    == designlib.cell_of({"run_id": me.get("run_id")})["rep"]][:6]
        return templates.TemplateResponse(request, "design.html", {
            "run_ref": run_ref, "design": design, "real": real, "siblings": siblings,
            "aslot": agent_slot(detail["metrics"].get("agents") or []),
        })

    @app.get("/design/diff", response_class=HTMLResponse)
    def design_diff_page(request: Request, a: str, b: str):
        da = _run_dir_or_404(a)
        db = _run_dir_or_404(b)
        diff = designlib.arm_diff(designlib.run_design(da), designlib.run_design(db))
        return templates.TemplateResponse(request, "design_diff.html",
                                          {"a": a, "b": b, "diff": diff})

    @app.get("/run/{run_ref:path}/organization", response_class=HTMLResponse)
    def organization_page(request: Request, run_ref: str):
        """Who is here, what each may do, who dealt with whom (DASHBOARD.md §4.2b)."""
        run_dir = _run_dir_or_404(run_ref)
        all_events = ev.load_events(run_dir)
        manifest = store._read_json(run_dir / "manifest.json") or {}
        design = designlib.run_design(run_dir, manifest)
        sw = ev.swimlane(all_events)
        rows = exchangelib.exchange_rows(manifest.get("task_pack_id"), all_events)
        me = store.run_record(run_dir, events=all_events)
        siblings = [r for r in _rows()
                    if r.get("experiment_id") == me.get("experiment_id")
                    and r.get("run_ref") != run_ref
                    and r.get("organization_id") != me.get("organization_id")][:4]
        return templates.TemplateResponse(request, "organization.html", {
            "run_ref": run_ref, "design": design,
            "g": orglib.graph(all_events, rows, sw["agents"]),
            "m": orglib.grant_matrix(design),
            "svg": _swimlane_svg(sw), "aslot": agent_slot(sw["agents"]), "siblings": siblings,
        })

    @app.get("/run/{run_ref:path}/agents", response_class=HTMLResponse)
    def agents_page(request: Request, run_ref: str):
        run_dir = _run_dir_or_404(run_ref)
        all_events = ev.load_events(run_dir)
        manifest = store._read_json(run_dir / "manifest.json") or {}
        design = designlib.run_design(run_dir, manifest)
        agents = ev.swimlane(all_events)["agents"]
        rows = exchangelib.exchange_rows(manifest.get("task_pack_id"), all_events)
        ms = exchangelib.milestone_rows(manifest.get("task_pack_id"), all_events)
        return templates.TemplateResponse(request, "agents.html", {
            "run_ref": run_ref, "profiles": agentlib.profiles(all_events, rows, design, agents, ms),
            "aslot": agent_slot(agents),
        })

    @app.get("/run/{run_ref:path}/agent/{agent_id}", response_class=HTMLResponse)
    def agent_page(request: Request, run_ref: str, agent_id: str):
        run_dir = _run_dir_or_404(run_ref)
        all_events = ev.load_events(run_dir)
        manifest = store._read_json(run_dir / "manifest.json") or {}
        design = designlib.run_design(run_dir, manifest)
        agents = ev.swimlane(all_events)["agents"]
        rows = exchangelib.exchange_rows(manifest.get("task_pack_id"), all_events)
        ms = exchangelib.milestone_rows(manifest.get("task_pack_id"), all_events)
        profile = next((p for p in agentlib.profiles(all_events, rows, design, agents, ms)
                        if p["agent"] == agent_id), None)
        if profile is None:
            raise HTTPException(404)
        notes = [e for e in all_events if e.get("event_class") == "message.sent"
                 and (e.get("payload") or {}).get("kind") == "note"]
        return templates.TemplateResponse(request, "agent.html", {
            "run_ref": run_ref, "a": profile, "aslot": agent_slot(agents),
            "inbox": [e for e in notes if (e.get("payload") or {}).get("to") == agent_id],
            "outbox": [e for e in notes if e.get("agent_id") == agent_id],
            "envelope": (design.get("envelopes") or {}).get(agent_id),
        })

    @app.get("/run/{run_ref:path}/work", response_class=HTMLResponse)
    def work_page(request: Request, run_ref: str):
        """The pack's registered account of what the run worked on (DASHBOARD.md §4.2c)."""
        run_dir = _run_dir_or_404(run_ref)
        all_events = ev.load_events(run_dir)
        pack = task_pack_id_of(run_dir)
        adapter = worklib.work_adapter_for(pack)
        if adapter is None:
            return RedirectResponse(f"/run/{run_ref}/cases", status_code=307)
        report = reports.get(run_dir, all_events)
        return templates.TemplateResponse(request, "work.html", {
            "run_ref": run_ref, "label": adapter.label,
            "sections": worklib.work_sections(pack, run_dir, all_events, report["report"]),
            "rmeta": {k: report.get(k) for k in ("source", "identity", "filename", "error", "superseded_file", "stale_keys")},
        })

    def _reading(detail: dict) -> tuple[dict, dict]:
        """Provenance plus the split between run conditions and archive notes (§4.9a)."""
        manifest = detail["manifest"] or {}
        ext = manifest.get("extensions") or {}
        prov = provenance.classify({
            "task_pack_id": manifest.get("task_pack_id"),
            "organization_id": manifest.get("organization_id"),
            "experiment_id": manifest.get("experiment_id"),
            "reference_sha256": ext.get("reference_sha256"),
            "hidden_reference_sha256s": ext.get("hidden_reference_sha256s"),
            "task_manifest_sha256": ext.get("task_manifest_sha256"),
        })
        report = attention.report_state(detail["record"], prov.get("provenance"),
                                        detail.get("task_report_meta"))
        return prov, {
            "conditions": attention.run_conditions(detail["record"]),
            "report": report,
            "notes": attention.archive_notes(detail["record"], prov.get("provenance"),
                                             prov.get("provenance_reasons"), report,
                                             source_dirty=bool(ext.get("source_dirty"))),
        }

    @app.get("/run/{run_ref:path}/record", response_class=HTMLResponse)
    def record_page(request: Request, run_ref: str):
        """The verification layer in one place (DASHBOARD.md §4.2e)."""
        run_dir = _run_dir_or_404(run_ref)
        all_events = ev.load_events(run_dir)
        detail = _detail(run_dir, all_events)
        prov, reading = _reading(detail)
        return templates.TemplateResponse(request, "record.html", {
            "run_ref": run_ref, "d": detail, "prov": prov, "reading": reading,
            "findings": diagnostics.diagnose(run_dir, all_events, detail),
            "manifest_json": json.dumps(detail["manifest"], indent=2, sort_keys=True)
            if detail["manifest"] else None,
            "config_json": json.dumps(detail["resolved_config"], indent=2, sort_keys=True)
            if detail["resolved_config"] else None,
        })

    @app.get("/run/{run_ref:path}/story", response_class=HTMLResponse)
    def story_page(request: Request, run_ref: str, depth: str = "notes",
                   agent: str | None = None, page: int = 1):
        """The organization's life in order (DASHBOARD.md §4.2a): the forum as the spine."""
        from oaos2.dashboard import story as storylib
        run_dir = _run_dir_or_404(run_ref)
        all_events = ev.load_events(run_dir)
        pack = task_pack_id_of(run_dir)
        items = storylib.story_items(
            all_events, exchanges=exchangelib.exchange_rows(pack, all_events),
            milestones=exchangelib.milestone_rows(pack, all_events),
            depth=depth, agent=agent or None)
        shown, pages = storylib.paginate(items, page)
        agents = [a for a in ev.swimlane(all_events)["agents"]]
        return templates.TemplateResponse(request, "story.html", {
            "run_ref": run_ref, "items": shown, "n_items": len(items), "kinds": storylib.counts(items),
            "depth": depth if depth in storylib.STORY_DEPTHS else "notes",
            "depths": storylib.STORY_DEPTHS, "agent": agent or "", "agents": agents,
            "page": page, "pages": pages, "aslot": agent_slot(agents),
            "has_board": had_board(run_dir, all_events),
        })

    # --- the live view (DASHBOARD.md §4.2f): follow a run while it is written -- #

    _live_memo: dict = {}
    _live_lock = threading.Lock()  # sync handlers run in a thread pool

    def _live(run_ref: str, *, depth: str, by: str, group: str, after: int | None,
              view: str = "feed") -> dict:
        """The live page's data. Derived state is memoized on the tail's version, so
        polls that find nothing new cost one stat per stream."""
        from oaos2.dashboard import story as storylib
        run_dir = _run_dir_or_404(run_ref)
        depth = depth if depth in storylib.STORY_DEPTHS else "said"
        by = by if by in livelib.GROUP_BYS else "auto"
        events, version = livelib.tail_events(run_dir)
        key = (str(run_dir), version, depth, by)
        with _live_lock:
            hit = _live_memo.get(str(run_dir))
        if hit is None or hit[0] != key:
            manifest = store._read_json(run_dir / "manifest.json") or {}
            pack = manifest.get("task_pack_id")
            roles = designlib.organization_of(manifest)["roles"]
            xs = exchangelib.exchange_rows(pack, events)
            ms = exchangelib.milestone_rows(pack, events)
            items = storylib.story_items(events, exchanges=xs, milestones=ms,
                                         depth=depth)
            state = livelib.live_state(run_dir, events, roles=roles, exchanges=xs, by=by,
                                       milestones=ms)
            state["can_post"] = any("post" in (r.get("comm_grants") or []) for r in roles.values()) \
                or any(it["kind"] == "post" for it in items)
            hit = (key, items, state, {})
            with _live_lock:
                _live_memo[str(run_dir)] = hit
                while len(_live_memo) > 8:
                    _live_memo.pop(next(iter(_live_memo)))
        _, items, state, lane_memo = hit
        state = livelib.live_clock(state, run_dir)  # elapsed times move while nothing is written
        group = group if group in {g["name"] for g in state["groups"]} else ""
        out = {"s": state, "depth": depth, "by": by, "group": group, "view": view,
               "aslot": agent_slot(state["agents"]), "recent": livelib.RECENT}
        if view != "lanes":
            out["items"] = livelib.feed_items(items, after=after, member=state["member"],
                                              group=group or None)
            return out
        lanes, index = livelib.lanes_of(state["agents"], state["member"], board=state["can_post"])
        if group not in lane_memo:  # rows for the whole run, kept until the streams change
            kept = livelib.feed_items(items, after=-1, member=state["member"], group=group or None)
            lane_memo[group] = livelib.lane_rows(kept, events, lanes=lanes, index=index)
        rows = livelib.rows_after(lane_memo[group], after)
        members = [[a for a in state["agents"] if index[a] == i] for i in range(len(lanes))]
        out.update({"rows": rows, "items": [r["item"] for r in rows],
                    "lanes": [{"name": n, "members": members[i]} for i, n in enumerate(lanes)],
                    "lanes_key": "|".join(lanes)})
        return out

    def _render(name: str, ctx: dict) -> str:
        return templates.get_template(name).render(ctx)

    @app.get("/run/{run_ref:path}/live", response_class=HTMLResponse)
    def live_page(request: Request, run_ref: str, depth: str = "said", by: str = "auto",
                  group: str = "", view: str = "lanes"):
        from oaos2.dashboard import story as storylib
        view = view if view in ("lanes", "feed") else "lanes"
        d = _live(run_ref, depth=depth, by=by, group=group, after=None, view=view)
        ctx = {"run_ref": run_ref, **d}
        return templates.TemplateResponse(request, "live.html", {
            **ctx, "feed_html": _render("_live_lanes.html" if view == "lanes" else "_live_items.html", ctx),
            "last_seq": d["s"]["last_seq"], "depths": storylib.STORY_DEPTHS,
            "group_bys": livelib.GROUP_BYS, "feed_first": livelib.FEED_FIRST,
            "interval_ms": livelib.POLL_MS,
        })

    @app.get("/run/{run_ref:path}/replay", response_class=HTMLResponse)
    def replay_page(request: Request, run_ref: str, depth: str = "notes", by: str = "auto"):
        """Watch how the run's work unfolded (DASHBOARD.md §4.2g): a moving window over
        the saved record, with busy agents, directed acts and the lanes revealed in time."""
        from oaos2.dashboard import replay as replaylib
        from oaos2.dashboard import story as storylib
        run_dir = _run_dir_or_404(run_ref)
        events = ev.load_events(run_dir)
        manifest = store._read_json(run_dir / "manifest.json") or {}
        pack = manifest.get("task_pack_id")
        depth = depth if depth in storylib.STORY_DEPTHS else "notes"
        by = by if by in livelib.GROUP_BYS else "auto"
        roles = designlib.organization_of(manifest)["roles"]
        xs = exchangelib.exchange_rows(pack, events)
        items = storylib.story_items(events, exchanges=xs, milestones=exchangelib.milestone_rows(pack, events),
                                     depth=depth)
        agents = [a for a in ev.swimlane(events)["agents"] if a != "coordination"]
        for a in roles:
            if a not in agents:
                agents.append(a)
        used, member = livelib.groups(agents, roles, by)
        board = had_board(run_dir, events)
        lanes, index = livelib.lanes_of(agents, member, board=board)
        rows = livelib.lane_rows(livelib.feed_items(items, after=-1, member=member), events,
                                 lanes=lanes, index=index)
        cap = 4000
        ctx = {"run_ref": run_ref, "rows": rows[:cap], "aslot": agent_slot(agents)}
        return templates.TemplateResponse(request, "replay.html", {
            **ctx, "lanes_html": templates.get_template("_live_lanes.html").render(ctx),
            "n_rows": len(rows), "cap": cap, "depth": depth, "by": by, "group_by": used,
            "depths": storylib.STORY_DEPTHS, "group_bys": livelib.GROUP_BYS, "has_board": board,
            "lanes": [{"name": n, "members": [a for a in agents if index[a] == i]} for i, n in enumerate(lanes)],
            "data": replaylib.replay_data(events, xs, agents),
        })

    @app.get("/run/{run_ref:path}/live.json")
    def live_json(run_ref: str, after: int = -1, depth: str = "said", by: str = "auto",
                  group: str = "", view: str = "lanes"):
        view = view if view in ("lanes", "feed") else "lanes"
        d = _live(run_ref, depth=depth, by=by, group=group, after=after, view=view)
        ctx = {"run_ref": run_ref, **d}
        env = templates.env
        panels = env.get_template("_live_panels.html").render(ctx)
        rows = "_live_lanes.html" if view == "lanes" else "_live_items.html"
        return {"last_seq": d["s"]["last_seq"], "ended": d["s"]["ended"],
                "n_new": len(d["items"]), "panels_html": panels, "lanes_key": d.get("lanes_key"),
                "feed_html": env.get_template(rows).render(ctx) if d["items"] else ""}

    @app.get("/run/{run_ref:path}/comms", response_class=HTMLResponse)
    def comms_page(request: Request, run_ref: str):
        run_dir = _run_dir_or_404(run_ref)
        all_events = ev.load_events(run_dir)
        rows = exchangelib.exchange_rows(task_pack_id_of(run_dir), all_events)
        comms = ev.comm_view(all_events, exchanges=rows)
        sw = ev.swimlane(all_events)
        return templates.TemplateResponse(request, "comms.html", {
            "run_ref": run_ref, "c": comms,
            "svg": _swimlane_svg(sw),
            "aslot": agent_slot(sw["agents"]),
            "schemas": annotate.load_schemas(runs_root),
        })

    @app.get("/run/{run_ref:path}/files", response_class=HTMLResponse)
    def files_page(request: Request, run_ref: str):
        from oaos2.archive.lineage import file_lineage
        run_dir = _run_dir_or_404(run_ref)
        lineage = file_lineage(run_dir, ev.load_events(run_dir))
        return templates.TemplateResponse(request, "files.html", {
            "run_ref": run_ref,
            "lineage": {path: lineage[path] for path in sorted(lineage)},
        })

    @app.get("/run/{run_ref:path}/annotations", response_class=HTMLResponse)
    def run_annotations_page(request: Request, run_ref: str):
        run_dir = _run_dir_or_404(run_ref)
        links = annotate.links_for_run(run_dir)
        by_ns: dict[str, list[dict]] = {}
        for link in links:
            by_ns.setdefault(link.get("namespace") or "?", []).append(link)
        return templates.TemplateResponse(request, "annotations_run.html", {
            "run_ref": run_ref, "by_ns": dict(sorted(by_ns.items())),
            "schemas": annotate.load_schemas(runs_root),
        })

    @app.post("/run/{run_ref:path}/annotate")
    async def annotate_event(request: Request, run_ref: str):
        run_dir = _run_dir_or_404(run_ref)
        form = await _form(request)
        event_ids = [s.strip() for s in str(form.get("event_ids", "")).split(",") if s.strip()]
        by_id = ev.event_index(run_dir)
        unknown = [i for i in event_ids if i not in by_id]
        if unknown:
            raise HTTPException(400, f"unknown event ids: {unknown}")
        item_id = str(form.get("item_id", "")).strip()
        mode = str(form.get("mode", "")).strip() or None
        try:
            annotate.write_link(runs_root, run_dir,
                                label_schema_ref=str(form.get("label_schema_ref", "")),
                                event_ids=event_ids, note=str(form.get("note", "")),
                                extra={"mode": mode, "item_id": item_id or None})
        except Exception as exc:
            raise HTTPException(400, f"annotation rejected: {exc}")
        wanted = str(form.get("back", "")).strip()
        if item_id:
            back = f"/run/{run_ref}/case/{item_id}" + (f"?mode={mode}" if mode == "open" else "")
        elif wanted.startswith(f"/run/{run_ref}/") and "//" not in wanted:
            back = wanted  # a page of this run only — never an arbitrary redirect target
        else:
            back = f"/run/{run_ref}/event/{event_ids[0]}" if event_ids else f"/run/{run_ref}/annotations"
        return RedirectResponse(back, status_code=303)

    @app.get("/run/{run_ref:path}/rawpayload/{digest}", response_class=PlainTextResponse)
    def raw_payload(run_ref: str, digest: str):
        run_dir = _run_dir_or_404(run_ref)
        # Content-addressed name only — never a path (mirrors raw_store's layout).
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise HTTPException(404)
        path = run_dir / "raw" / f"{digest}.json.gz"
        if not path.exists():
            raise HTTPException(404)
        try:
            with gzip.open(path, "rb") as f:
                return json.dumps(json.loads(f.read()), indent=2, sort_keys=True)
        except (OSError, ValueError):
            raise HTTPException(404)

    @app.get("/run/{run_ref:path}", response_class=HTMLResponse)
    def run_page(request: Request, run_ref: str):
        run_dir = store.resolve_run_dir(runs_root, run_ref)
        if run_dir is None:
            raise HTTPException(404)
        all_events = ev.load_events(run_dir)
        detail = _detail(run_dir, all_events)
        manifest = detail["manifest"] or {}
        prov, reading = _reading(detail)
        findings = diagnostics.diagnose(run_dir, all_events, detail)
        frozen_row = frozen.frozen_for(detail["record"].get("run_id"))
        left_out = frozen.left_out_of_dataset(run_dir.name)
        detail["record"]["eligibility"] = _with_dataset(detail["record"].get("eligibility"), frozen_row, left_out)
        rendered_rf = ((detail["task_report"] or {}).get("summary") or {}).get("retained_fraction")
        renderer = derived_renderer_for(manifest.get("task_pack_id"))
        report_summary = None
        if renderer is not None and detail["task_report"] is not None:
            try:
                report_summary = renderer.summary(detail["task_report"])
            except Exception as exc:  # noqa: BLE001 — a summary failure is shown, not fatal
                report_summary = {"summary_error": f"{type(exc).__name__}: {exc}"[:200]}
        frozen_mismatch = (frozen_row is not None and rendered_rf is not None
                           and frozen_row.get("retained_fraction") is not None
                           and abs(frozen_row["retained_fraction"] - rendered_rf) > 1e-6)
        dead, protected = removal.removable({**detail["record"], "run_dir": str(run_dir),
                                             "in_frozen_dataset": frozen_row is not None})
        return templates.TemplateResponse(request, "run.html", {
            "run_ref": run_ref,
            "d": detail,
            "dead": dead, "dead_protected": protected,
            "frozen": frozen_row, "frozen_mismatch": frozen_mismatch, "left_out": left_out,
            "report_summary": report_summary,
            "svg": _swimlane_svg(ev.swimlane(all_events), compact=True),
            "prov": prov, "reading": reading,
            "started_label": _when(_run_time({**detail["record"], "run_dir": str(run_dir)})),
            "findings_n": len(findings),
            "has_board": had_board(run_dir, all_events),
            "findings_worst": findings[0] if findings else None,
            "n_annotations": sum(len(v) for v in annotate.links_by_event(run_dir).values()),
            "manifest_json": json.dumps(detail["manifest"], indent=2, sort_keys=True)
            if detail["manifest"] else None,
            "config_json": json.dumps(detail["resolved_config"], indent=2, sort_keys=True)
            if detail["resolved_config"] else None,
        })

    # --- root-level workbenches (annotations / library / launch) ------------- #

    def _dead_rows() -> tuple[list[dict], list[dict]]:
        """Dead runs (DASHBOARD.md §4.9c), split into removable and protected, newest first."""
        can, kept = [], []
        for r in sorted(_rows(), key=lambda r: (r.get("started") or 0.0), reverse=True):
            r["in_frozen_dataset"] = frozen.frozen_for(r.get("run_id")) is not None
            dead, protected = removal.removable(r)
            if dead:
                r["dead_reason"], r["protected_reason"] = dead, protected
                (kept if protected else can).append(r)
        return can, kept

    @app.get("/cleanup", response_class=HTMLResponse)
    def cleanup_page(request: Request, msg: str | None = None):
        """Remove dead runs from the archive the dashboard reads, or restore them."""
        can, kept = _dead_rows()
        removed = removal.list_removed(runs_root)
        for r in removed:
            r["at_label"] = _when(r["at"])
        return templates.TemplateResponse(request, "cleanup.html", {
            "can": can, "kept": kept, "removed": removed, "msg": msg,
            "quiet_minutes": removal.QUIET_MINUTES, "removed_dir": removal.REMOVED_DIR})

    @app.post("/cleanup/remove")
    async def cleanup_remove(request: Request):
        # every checked box arrives under the same name; _form keeps only the last value
        refs = parse_qs((await request.body()).decode("utf-8")).get("run_ref", [])
        if not refs:
            return RedirectResponse("/cleanup?msg=nothing+selected", status_code=303)
        # decided again here, from the archive as it stands now, never from the page
        can = {r["run_ref"]: r for r in _dead_rows()[0]}
        refused = [ref for ref in refs if ref not in can]
        if refused:
            raise HTTPException(400, f"not removable now (finished writing? protected? already gone?): {refused}")
        for ref in refs:
            r = can[ref]
            removal.remove_run(runs_root, Path(r["run_dir"]), ref,
                               reason=r["dead_reason"], status=r.get("status"))
        _rows(rebuild=False)  # the scan drops the moved runs from the registry cache
        n = len(refs)
        return RedirectResponse(f"/cleanup?msg=removed+{n}+run{'s' if n != 1 else ''}", status_code=303)

    @app.post("/cleanup/restore")
    async def cleanup_restore(request: Request):
        form = await _form(request)
        ref = str(form.get("run_ref", ""))
        try:
            removal.restore_run(runs_root, ref)
        except (FileNotFoundError, FileExistsError) as exc:
            raise HTTPException(400, str(exc))
        return RedirectResponse("/cleanup?msg=restored+1+run", status_code=303)

    @app.get("/live", response_class=HTMLResponse)
    def live_index(request: Request):
        """Unfinished runs the archive has not read as idle (DASHBOARD.md §4.2f)."""
        return templates.TemplateResponse(request, "live_index.html", {
            "rows": livelib.in_flight(_rows()), "idle_hours": store.IDLE_AFTER_HOURS})

    @app.get("/guide")
    def guide_page():
        return RedirectResponse("/", status_code=307)

    @app.get("/annotations", response_class=HTMLResponse)
    def annotations_page(request: Request, msg: str | None = None):
        rows = _rows()
        coverage = []
        for r in rows:
            run_dir = Path(r["run_dir"])
            links = annotate.links_for_run(run_dir)
            if links:
                ns: dict[str, int] = {}
                for link in links:
                    ns[link.get("namespace") or "?"] = ns.get(link.get("namespace") or "?", 0) + 1
                coverage.append({"row": r, "n": len(links), "namespaces": dict(sorted(ns.items()))})
        return templates.TemplateResponse(request, "annotations.html", {
            "schemas": annotate.load_schemas(runs_root), "coverage": coverage,
            "msg": msg,
        })

    @app.post("/annotations/schema")
    async def add_schema(request: Request):
        from oaos2.annotations.label_registry import LabelSchema
        form = await _form(request)
        try:
            schema = LabelSchema(
                label_schema_ref=str(form.get("label_schema_ref", "")).strip(),
                namespace=str(form.get("namespace", "")).strip(),
                arity=str(form.get("arity", "unary")),
                relation_kind=str(form.get("relation_kind", "")).strip() or None,
                description=str(form.get("description", "")).strip(),
            )
            if not schema.label_schema_ref or not schema.namespace:
                raise ValueError("label_schema_ref and namespace are required")
            annotate.save_schema(runs_root, schema)
        except Exception as exc:
            raise HTTPException(400, f"schema rejected: {exc}")
        return RedirectResponse("/annotations", status_code=303)

    @app.get("/search", response_class=HTMLResponse)
    def search_page(request: Request, q: str = "", lineage: str = "", experiment: str = "",
                    kind: str = ""):
        rows = _rows()
        lineages = sorted({r.get("lineage") for r in rows if r.get("lineage")})
        experiments = sorted({r.get("experiment_id") for r in rows if r.get("experiment_id")})
        ctx = {"q": q, "lineage": lineage, "experiment": experiment, "kind": kind,
               "lineages": lineages, "experiments": experiments, "results": None,
               "note": None, "scope_n": 0, "built": None}
        if not q.strip():
            ctx["note"] = "Pick a lineage or an experiment and search; the index is built per run on first use."
            return templates.TemplateResponse(request, "search.html", ctx)
        if not lineage and not experiment:
            ctx["note"] = "A scope is required (a lineage or an experiment) so a search never indexes the whole archive at once."
            return templates.TemplateResponse(request, "search.html", ctx)
        scope = [r for r in rows if (not lineage or r.get("lineage") == lineage)
                 and (not experiment or r.get("experiment_id") == experiment)]
        ctx["scope_n"] = len(scope)
        ctx["built"] = search_index.ensure(scope, ev.load_events)
        results = search_index.query(q, [r["run_dir"] for r in scope])
        if kind:
            results = [r for r in results if r.get("kind") == kind or r.get("error")]
        ctx["results"] = results
        return templates.TemplateResponse(request, "search.html", ctx)

    @app.get("/codebook", response_class=HTMLResponse)
    def codebook_page(request: Request):
        from oaos2.annotations.codebook import load_all_codebooks
        return templates.TemplateResponse(request, "codebook.html", {
            "books": load_all_codebooks(), "mine": annotate.researcher_schemas(runs_root)})

    @app.get("/library", response_class=HTMLResponse)
    def library_page(request: Request):
        lib = workbench.list_library()
        return templates.TemplateResponse(request, "library.html", {
            "lib": lib, "families": workbench.organization_families(lib["organizations"])})

    @app.get("/library/edit", response_class=HTMLResponse)
    def edit_page(request: Request, f: str, msg: str | None = None, ok: str | None = None):
        path = workbench.resolve_library_file(f)
        if path is None:
            raise HTTPException(404)
        return templates.TemplateResponse(request, "edit.html", {
            "rel": f, "content": path.read_text(), "msg": msg, "ok": ok == "1",
        })

    @app.post("/library/edit")
    async def edit_save(request: Request):
        form = await _form(request)
        rel = str(form.get("f", ""))
        saved, message = workbench.save_validated(rel, str(form.get("content", "")))
        from urllib.parse import quote
        return RedirectResponse(
            f"/library/edit?f={quote(rel)}&msg={quote(message)}&ok={'1' if saved else '0'}",
            status_code=303)

    @app.get("/launch", response_class=HTMLResponse)
    def launch_page(request: Request, msg: str | None = None):
        designs = [e for e in workbench.list_library()["experiments"] if "error" not in e]
        return templates.TemplateResponse(request, "launch.html", {
            "designs": designs, "launches": workbench.list_launches(runs_root),
            "msg": msg, "confirm_phrase": LIVE_CONFIRM_PHRASE,
        })

    @app.post("/launch")
    async def launch_post(request: Request):
        form = await _form(request)
        design = str(form.get("design", ""))
        execution = str(form.get("execution", "offline"))
        reps = int(form.get("reps") or 0) or None
        known = {e["name"] for e in workbench.list_library()["experiments"]}
        if design not in known:
            raise HTTPException(400, f"unknown design {design!r}")
        if execution == "live":
            # The hard spend gate (DASHBOARD.md §4.8): typed phrase + explicit cap.
            # The runner's own gates (confirmatory prereg, per-cell caps) still apply.
            if str(form.get("confirm", "")) != LIVE_CONFIRM_PHRASE:
                raise HTTPException(400,
                                    f"live launch refused: type {LIVE_CONFIRM_PHRASE!r} to confirm spend")
            try:
                cap_usd = validate_spending_cap(form.get("cap_usd"))
            except (TypeError, ValueError):
                raise HTTPException(400, "live launch refused: a finite, positive per-cell cap_usd is required")
            workbench.launch(runs_root, design=design, execution="live",
                             reps=reps, cap_usd=cap_usd)
        else:
            workbench.launch(runs_root, design=design, execution="offline", reps=reps)
        return RedirectResponse("/launch?msg=launched", status_code=303)

    return app


LIVE_CONFIRM_PHRASE = "RUN LIVE"


def _trace_rows(run_dir: Path, events: list[dict], view: str) -> list[dict]:
    """The explorer's row list — same semantics as the derived transcripts:
    ``clean`` = audience:agent events with each model utterance folded verbatim
    from raw/ (render_clean); anything else = every event with its one-line
    summary (render_full). Row text comes from the same functions the
    transcripts use, so the two readings can never drift apart."""
    if view != "clean":
        return [{"e": e, "kind": "event", "text": ev.summary(e)} for e in events]
    rows: list[dict] = []
    for e in events:
        if e.get("event_class") == "model.responded":
            prose = ev.prose_for(run_dir, e)
            if prose:
                rows.append({"e": e, "kind": "prose", "text": prose})
            continue  # the telemetry line itself stays out of clean
        if e.get("audience") == "agent":
            rows.append({"e": e, "kind": "event", "text": ev.summary(e)})
    return rows


_CC_W, _CC_H, _CC_PAD = 1000, 150, 8


def _cost_chart(cost_rows, cap, events) -> dict | None:
    """Geometry for the cumulative-spend curve: x = sequence, y = running dollars,
    with the cap as a reference line and any cap-blocked dispatches marked. Shows
    WHEN budget pressure built — a flat line that suddenly steepens is a burn."""
    if not cost_rows:
        return None
    max_seq = max((e.get("sequence_number") or 0) for e in events) or 1
    total = cost_rows[-1][2]
    y_max = max(total, cap or 0) * 1.06 or 1.0

    def _pt(seq, usd):
        x = _CC_PAD + (seq / max_seq) * (_CC_W - 2 * _CC_PAD)
        y = _CC_H - _CC_PAD - (usd / y_max) * (_CC_H - 2 * _CC_PAD)
        return f"{x:.1f},{y:.1f}"

    points = [_pt(0, 0.0)] + [_pt(e.get("sequence_number") or 0, c) for e, _, c in cost_rows]
    blocked = [{"x": _pt(e.get("sequence_number") or 0, cap or total).split(",")[0],
                "event_id": e.get("event_id"), "seq": e.get("sequence_number")}
               for e in events if e.get("event_class") == "cost.cap_blocked_dispatch"]
    cap_y = None
    if cap:
        cap_y = round(_CC_H - _CC_PAD - (cap / y_max) * (_CC_H - 2 * _CC_PAD), 1)
    return {"w": _CC_W, "h": _CC_H, "polyline": " ".join(points),
            "end": points[-1], "total": total, "cap": cap, "cap_y": cap_y,
            "blocked": blocked, "pct_of_cap": (total / cap * 100) if cap else None}


_MINIMAP_MAX = 1500


def _flow_minimap(pages: list[list[dict]]) -> dict:
    """The whole flow as one clickable strip: every item a tick positioned by its
    sequence number, carrying the PAGE it lives on so a click can jump across
    pagination. Down-sampled evenly past the cap (problems/commits always kept)."""
    items = [(pi + 1, item) for pi, groups in enumerate(pages) for g in groups for item in g["items"]]
    if not items:
        return {"ticks": [], "window": None}
    max_seq = max((it["e"].get("sequence_number") or 0) for _, it in items) or 1
    keep_always = {"problem", "commit", "outcome", "arrival", "filing"}
    if len(items) > _MINIMAP_MAX:
        step = len(items) / _MINIMAP_MAX
        sampled, next_i = [], 0.0
        for i, (pg, it) in enumerate(items):
            if i >= next_i or it["kind"] in keep_always:
                sampled.append((pg, it))
                if i >= next_i:
                    next_i += step
        items = sampled
    ticks = [{"pct": round((it["e"].get("sequence_number") or 0) / max_seq * 100, 2),
              "kind": it["kind"], "event_id": it["e"].get("event_id"), "page": pg,
              "seq": it["e"].get("sequence_number")}
             for pg, it in items]
    return {"ticks": ticks, "max_seq": max_seq}


REGISTERED_MODES = ("confirmatory",)
EXPLORATORY_MODES = ("calibration", "pilot")


def _design_for(experiment_ids: list[str], designs: list[dict]) -> dict | None:
    """The library design a lineage's experiment ids name: an exact name, or the
    design name as a prefix (runners suffix the case set, e.g. ``_delfield_...``)."""
    for d in designs:
        name = d.get("name") or ""
        if name and any(e == name or e.startswith(name + "_") for e in experiment_ids):
            return d
    return None


def _prereg_link(design: dict | None, documents: dict[str, Path]) -> tuple[str | None, str | None]:
    ref = ((design or {}).get("resolved") or {}).get("preregistration_ref")
    if not ref:
        return None, None
    name = Path(ref).name
    return ref, (f"/study-records/{name}" if name in documents else None)


def _lineage_groups(rows: list[dict], designs: list[dict], documents: dict[str, Path]) -> list[dict]:
    by: dict[str, list[dict]] = {}
    for r in rows:
        by.setdefault(r.get("lineage") or "—", []).append(r)
    out = []
    for lineage, members in sorted(by.items()):
        exp_ids = sorted({m.get("experiment_id") for m in members if m.get("experiment_id")})
        design = _design_for(exp_ids, designs)
        prereg_ref, prereg_href = _prereg_link(design, documents)
        out.append({
            "lineage": lineage, "rows": members, "n": len(members),
            "experiments": exp_ids, "modes": sorted({m.get("mode") or "none" for m in members}),
            "design": (design or {}).get("name"), "prereg_ref": prereg_ref, "prereg_href": prereg_href,
            "passed": sum(1 for m in members if m.get("status") == "passed"),
            "failed_score": sum(1 for m in members if m.get("status") == "failed_score"),
            "incomplete": sum(1 for m in members if m.get("status") == "incomplete"),
            "irregular": sum(1 for m in members if m.get("irregular")),
        })
    return out


def _mode_sections(rows: list[dict], designs: list[dict], documents: dict[str, Path]) -> dict:
    """Runs by the mode their manifest declares (DASHBOARD.md §4.1): registered
    experiments (confirmatory), exploratory work (calibration and pilots), and runs
    with no declared mode. Read from the saved manifest, never inferred from names."""
    registered = [r for r in rows if r.get("mode") in REGISTERED_MODES]
    exploratory = [r for r in rows if r.get("mode") in EXPLORATORY_MODES]
    undeclared = [r for r in rows if r.get("mode") not in REGISTERED_MODES + EXPLORATORY_MODES]
    return {"registered": _lineage_groups(registered, designs, documents),
            "exploratory": _lineage_groups(exploratory, designs, documents),
            "undeclared": _lineage_groups(undeclared, designs, documents),
            "n_registered": len(registered), "n_exploratory": len(exploratory),
            "n_undeclared": len(undeclared)}


INDEX_THRESHOLD = 60  # below this many runs the page lists every run; above, lineages first
SCOPES = {"registered": REGISTERED_MODES, "exploratory": EXPLORATORY_MODES}
_ULID_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def _run_time(row: dict) -> float | None:
    """When the run started, in epoch seconds: the ULID the runner appends to a run id,
    else the manifest file's modification time. A display aid, never an analysis input."""
    tail = str(row.get("run_id") or "").rsplit("__", 1)[-1].upper()
    if len(tail) == 26 and all(ch in _ULID_ALPHABET for ch in tail):
        ms = 0
        for ch in tail[:10]:
            ms = ms * 32 + _ULID_ALPHABET.index(ch)
        return ms / 1000.0
    try:
        return (Path(row["run_dir"]) / "manifest.json").stat().st_mtime
    except (KeyError, OSError):
        return None


def _when(t: float | None) -> str | None:
    """A start time as local wall-clock text for display (this is a local dashboard)."""
    import datetime
    return datetime.datetime.fromtimestamp(t).strftime("%Y-%m-%d %H:%M") if t else None


SORTS = {"newest": (lambda r: r.get("started") or 0.0, True),
         "oldest": (lambda r: r.get("started") or 0.0, False),
         "cost": (lambda r: r.get("cost_usd") or 0.0, True)}

# A batch launcher names one experiment per seed, ``<stem>_s<seed>``, and a rerun ``<stem>_s<seed>_b``
# (PC1's run_pc1_batch, October 2026), so the runs of one design land in as many experiments as seeds.
_SEEDED_EXPERIMENT = re.compile(r"^(?P<stem>.+)_s(?P<seed>\d+)(?P<rerun>_b)?$")


def _experiment_stem(experiment_id: str | None) -> tuple[str | None, str | None]:
    """An experiment name without its seed suffix, and the suffix as a label ("s109", "s158 rerun");
    a name without one is its own stem and has no label. A reading aid for the run list, read from the
    name the launcher gave; never an analysis input."""
    m = _SEEDED_EXPERIMENT.match(experiment_id or "")
    if not m:
        return experiment_id, None
    return m["stem"], f"s{m['seed']}" + (" rerun" if m["rerun"] else "")


def _experiment_groups(rows: list[dict]) -> list[dict]:
    """Rows grouped by experiment stem, in the order the list already has (DASHBOARD.md §4.1): each group is
    one entry whose run is chosen from a menu. Not by lineage, since a launch without a series folder gives each
    seed its own top-level folder. Runs without an experiment name stay alone."""
    groups: dict[str, dict] = {}
    for i, r in enumerate(rows):
        stem, label = _experiment_stem(r.get("experiment_id"))
        key = stem if stem else f"#{i}"
        g = groups.setdefault(key, {"stem": stem, "runs": []})
        g["runs"].append({"row": r, "label": " · ".join(x for x in (label, r.get("started_label")) if x)
                          or r.get("run_id", "")[-6:]})
    return list(groups.values())


def _lineage_index(rows: list[dict], designs: list[dict], documents: dict[str, Path]) -> list[dict]:
    """One row per lineage, newest first (DASHBOARD.md §4.1): what it is, how much of it
    there is, and how many of its runs carry a recorded condition worth reading first."""
    import datetime
    out = []
    for g in _lineage_groups(rows, designs, documents):
        times = [t for t in (_run_time(m) for m in g["rows"]) if t is not None]
        costs = [m["cost_usd"] for m in g["rows"] if m.get("cost_usd") is not None]
        attention_n = sum(1 for m in g["rows"] if attention.row_attention(m))
        day = lambda t: datetime.datetime.fromtimestamp(t, datetime.timezone.utc).strftime("%Y-%m-%d")  # noqa: E731
        out.append({**{k: v for k, v in g.items() if k != "rows"},
                    "packs": sorted({m.get("task_pack_id") for m in g["rows"] if m.get("task_pack_id")}),
                    "scopes": sorted({"registered" if m.get("mode") in REGISTERED_MODES else
                                      "exploratory" if m.get("mode") in EXPLORATORY_MODES else "undeclared"
                                      for m in g["rows"]}),
                    "first_day": day(min(times)) if times else None,
                    "last_day": day(max(times)) if times else None,
                    "latest": max(times) if times else 0.0,
                    "latest_run": max(g["rows"], key=lambda m: _run_time(m) or 0.0),
                    "attention": attention_n,
                    "posts": sum((m.get("n_board_posts") or 0) + (m.get("n_notes") or 0) for m in g["rows"]),
                    "cost_usd": sum(costs) if costs else None,
                    "n_unknown_usage": sum(m.get("n_unknown_usage") or 0 for m in g["rows"]),
                    "n_eligible": store.n_eligible(g["rows"]),
                    "outcome_digest": store.outcome_digest(g["rows"]),
                    "_rows": g["rows"]})
    return sorted(out, key=lambda g: (-g["latest"], g["lineage"]))


def _study_index(lineages: list[dict], declared: list[dict], documents: dict[str, Path]) -> list[dict]:
    """Fold the lineages of a declared study into one index row (library/studies.yaml);
    a lineage no study claims keeps its own row. Newest first either way."""
    out, folded = [], {}
    for g in lineages:
        st = studylib.study_of(g["lineage"], declared)
        if st is None:
            out.append({**g, "kind": "lineage"})
            continue
        row = folded.get(st["id"])
        if row is None:
            record = st.get("record")
            row = folded[st["id"]] = {
                "kind": "study", "study": st["id"], "title": st["title"], "members": [],
                "record": record, "record_href": f"/study-records/{record}" if record in documents else None,
                "n": 0, "attention": 0, "posts": 0, "passed": 0, "failed_score": 0, "cost_usd": None,
                "n_unknown_usage": 0, "n_eligible": 0, "rows_for_digest": [],
                "modes": set(), "packs": set(), "scopes": set(), "first_day": None, "last_day": None, "latest": 0.0}
            out.append(row)
        row["members"].append(g)
        for key in ("n", "attention", "posts", "passed", "failed_score", "n_unknown_usage", "n_eligible"):
            row[key] += g.get(key) or 0
        if g["cost_usd"] is not None:
            row["cost_usd"] = (row["cost_usd"] or 0.0) + g["cost_usd"]
        for key in ("modes", "packs", "scopes"):
            row[key] |= set(g[key])
        row["rows_for_digest"] += g.get("_rows") or []
        days = [d for d in (row["first_day"], g["first_day"]) if d]
        row["first_day"] = min(days) if days else None
        days = [d for d in (row["last_day"], g["last_day"]) if d]
        row["last_day"] = max(days) if days else None
        if g["latest"] >= row["latest"]:
            row["latest_run"] = g.get("latest_run")
        row["latest"] = max(row["latest"], g["latest"])
    for row in out:
        if row["kind"] == "study":
            for key in ("modes", "packs", "scopes"):
                row[key] = sorted(row[key])
            # outcomes of different tasks do not add up: one digest only for one task
            row["outcome_digest"] = (store.outcome_digest(row.pop("rows_for_digest"))
                                     if len(row["packs"]) == 1 else None)
    return sorted(out, key=lambda g: (-g["latest"], g.get("lineage") or g.get("study")))


def _experiment_pivot(rows: list[dict]) -> dict:
    """arm × condition cells for one experiment. The condition axis is whichever
    factor actually varies in these runs (difficulty, else context budget, else a
    single '—' column)."""
    conditions = sorted({r.get("difficulty") for r in rows if r.get("difficulty")})
    axis = "difficulty"
    if len(conditions) <= 1:
        clocks = sorted({r.get("clock_label") for r in rows if r.get("clock_label")})
        if clocks:
            conditions, axis = clocks, "clock"
    if len(conditions) <= 1 and axis != "clock":
        cbs = sorted({str(r.get("context_budget")) for r in rows
                      if r.get("context_budget") is not None})
        if len(cbs) > 1:
            conditions, axis = cbs, "context_budget"
    if not conditions:
        conditions = ["—"]
    arms = sorted({r.get("organization_id") or "—" for r in rows})
    cells: dict[tuple, dict] = {}
    for r in rows:
        col = "clock_label" if axis == "clock" else axis
        cond = (r.get(col) if axis != "context_budget" else str(r.get("context_budget"))) or "—"
        key = (r.get("organization_id") or "—", cond)
        cell = cells.setdefault(key, {"n": 0, "passed": 0, "scored": 0, "censored": 0,
                                      "floor": 0, "scores": [], "retained": [], "cost": 0.0,
                                      "prov": set()})
        cell["n"] += 1
        cell["passed"] += 1 if r.get("status") == "passed" else 0
        cell["scored"] += 1 if r.get("scored") else 0
        cell["censored"] += 1 if r.get("censored") else 0
        cell["floor"] += 1 if r.get("floor_regime") else 0
        if r.get("partial_score") is not None:
            cell["scores"].append(r["partial_score"])
        if r.get("retained_fraction") is not None:
            cell["retained"].append(r["retained_fraction"])
        cell["cost"] += r.get("cost_usd") or 0.0
        cell.setdefault("members", []).append(r)
        cell["unknown_usage"] = cell.get("unknown_usage", 0) + (r.get("n_unknown_usage") or 0)
        cell["prov"].add(r.get("provenance") or "unknown")
    for cell in cells.values():
        members = cell.pop("members", [])
        cell["eligible"] = store.n_eligible(members)
        cell["outcome_digest"] = store.outcome_digest(members)
        cell["mean"] = sum(cell["scores"]) / len(cell["scores"]) if cell["scores"] else None
        cell["mean_retained"] = (sum(cell["retained"]) / len(cell["retained"])
                                 if cell["retained"] else None)
        cell["prov"] = sorted(cell["prov"])
    return {"axis": axis, "conditions": conditions, "arms": arms, "cells": cells}


_SW_W, _SW_LANE_H, _SW_LEFT = 1000, 26, 130

# agent-identity color slots (fixed order, never cycled; red is reserved for
# trouble so it is not in this list; a 9th+ agent falls to gray)
AGENT_SLOTS = 8


def agent_slot(agents: list[str]) -> dict[str, int]:
    """agent → identity color slot (0-7 by first appearance, -1 = gray overflow)."""
    return {a: (i if i < AGENT_SLOTS else -1) for i, a in enumerate(agents)}


def _swimlane_svg(model: dict, *, compact: bool = False) -> dict:
    """Pixel geometry for the swimlane template (all layout here, none in Jinja)."""
    lane_h = 20 if compact else _SW_LANE_H
    lane_y = {a: 16 + i * lane_h for i, a in enumerate(model["agents"])}
    scale = (_SW_W - _SW_LEFT - 10) / model["max_seq"]
    slots = agent_slot(model["agents"])

    def _x(seq):
        return round(_SW_LEFT + seq * scale, 1)

    marks = [{"x": _x(m["seq"]), "y": lane_y[m["agent"]], "kind": m["kind"],
              "cls": m["cls"], "seq": m["seq"], "event_id": m["event_id"]}
             for m in model["marks"]]
    arrows = [{"x": _x(a["seq"]), "y1": lane_y[a["from"]], "y2": lane_y[a["to"]],
               "cls": a["cls"], "seq": a["seq"], "event_id": a["event_id"]}
              for a in model["arrows"]]
    # Merge each agent's turn spans that touch in PIXEL space: a scheduler that
    # admits thousands of micro-turns (the organic arm does) reads as continuous
    # activity, which is the honest rendering — and keeps the SVG small.
    spans: list[dict] = []
    by_agent: dict[str, list] = {}
    for s in sorted(model["spans"], key=lambda s: s["s0"]):
        if s["agent"] not in lane_y:
            continue
        x0, x1 = _x(s["s0"]), max(_x(s["s1"]), _x(s["s0"]) + 2)
        merged = by_agent.setdefault(s["agent"], [])
        if merged and x0 <= merged[-1]["x1"] + 1.5:
            merged[-1]["x1"] = max(merged[-1]["x1"], x1)
            merged[-1]["n"] += 1
        else:
            merged.append({"x0": x0, "x1": x1, "y": lane_y[s["agent"]],
                           "turn": s["turn"], "n": 1})
    for agent_spans in by_agent.values():
        for s in agent_spans:
            s["turn"] = s["turn"] if s["n"] == 1 else f"{s['n']} turns"
            spans.append(s)
    counts: dict[str, int] = {}
    for m in model["marks"]:
        counts[m["kind"]] = counts.get(m["kind"], 0) + 1
    for a in model["arrows"]:
        counts[a["cls"]] = counts.get(a["cls"], 0) + 1
    return {"width": _SW_W, "height": len(model["agents"]) * lane_h + 10,
            "lanes": [{"agent": a, "y": y, "slot": slots[a]} for a, y in lane_y.items()],
            "marks": marks, "arrows": arrows, "spans": spans, "counts": counts,
            "truncated": model["truncated"], "left": _SW_LEFT, "compact": compact}


def _tiles(rows: list[dict]) -> dict:
    costs = [r["cost_usd"] for r in rows if r.get("cost_usd") is not None]
    return {
        "runs": len(rows),
        "passed": sum(1 for r in rows if r.get("status") == "passed"),
        "eligible": sum(1 for r in rows if (r.get("eligibility") or {}).get("label") in ("eligible", "in analysis dataset")),
        "failed_score": sum(1 for r in rows if r.get("status") == "failed_score"),
        "unscored": sum(1 for r in rows if r.get("status") == "unscored"),
        "incomplete": sum(1 for r in rows if r.get("status") == "incomplete"),
        "censored": sum(1 for r in rows if r.get("censored")),
        "clocked": sum(1 for r in rows if r.get("clock_label") or r.get("rounds_total")),
        "irregular": sum(1 for r in rows if r.get("irregular")),
        "cost_usd": sum(costs) if costs else None,
        "n_unknown_usage": sum(r.get("n_unknown_usage") or 0 for r in rows),
    }


def _with_dataset(elig: dict | None, frozen_row: dict | None, left_out: dict | None) -> dict | None:
    """A saved analysis dataset's own membership replaces the platform reading: a run in
    its rows is in the dataset; a run its audit left out is out, for its stated reason."""
    notes = {"notes": elig["notes"]} if elig and elig.get("notes") else {}
    if frozen_row is not None:
        return {"label": "in analysis dataset", "reasons": [],
                "source": frozen_row.get("_evidence_file"), **notes}
    if left_out is not None:
        return {"label": "left out of analysis dataset",
                "reasons": [str(left_out.get("reason") or left_out.get("kind")).replace("_", " ")],
                "source": left_out.get("_evidence_file"), **notes}
    return elig


def _row_recency(row: dict) -> int:
    """UI-only recency for the live landing page; never an analysis construct."""
    try:
        return (Path(row["run_dir"]) / "trace" / "events.jsonl").stat().st_mtime_ns
    except (KeyError, OSError):
        return 0
