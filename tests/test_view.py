"""`krouter view`: the read-only page. No browser: the server is started in a thread on a free port and its endpoints are
requested directly. What is checked: it listens on loopback only, has no endpoint that writes, refers to nothing outside
(no external address in any response, a Content-Security-Policy that allows none), pages through a large memory instead of
sending it, and shows the same explanation as `krouter why`."""

from __future__ import annotations

import http.client
import inspect
import json
import re
import shutil
import sys
import threading
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "sdk"))
from krouter import sample, view, viewdata, why  # noqa: E402
from krouter.viewdata import Store  # noqa: E402


@pytest.fixture(scope="module")
def env(tmp_path_factory):
    mp = pytest.MonkeyPatch()
    root = tmp_path_factory.mktemp("view")
    mp.setenv("KROUTER_NO_QUERY_LOG", "1")
    mp.setenv("KROUTER_CACHE_DIR", str(root / "cache"))
    mp.setenv("KROUTER_STATE_DIR", str(root / "state"))
    mp.delenv("OBSIDIAN_VAULT", raising=False)
    mp.delenv("KROUTER_VAULT", raising=False)
    en = sample.build(root / "en", "en")
    zh = sample.build(root / "zh", "zh")
    yield {"en": en, "zh": zh, "root": root}
    mp.undo()


class Client:
    def __init__(self, server):
        self.port = server.server_address[1]

    def req(self, method: str, path: str, headers: dict | None = None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=30)
        c.request(method, path, headers=headers or {})
        r = c.getresponse()
        body = r.read()
        out = (r.status, dict(r.getheaders()), body)
        c.close()
        return out

    def get(self, path: str):
        status, headers, body = self.req("GET", path)
        return status, headers, body

    def json(self, path: str):
        status, _h, body = self.get(path)
        assert status == 200, (path, status, body[:200])
        return json.loads(body)


@pytest.fixture(scope="module")
def srv(env):
    store = Store(env["en"])
    store.refresh(force=True)
    server = view.Server(store, 0)
    th = threading.Thread(target=server.serve_forever, daemon=True)
    th.start()
    yield Client(server), server
    server.shutdown()
    server.server_close()


def test_it_listens_on_loopback_only_and_there_is_no_way_to_ask_otherwise(srv):
    _c, server = srv
    assert server.server_address[0] == "127.0.0.1" and view.BIND == "127.0.0.1"
    assert server.url.startswith("http://127.0.0.1:")
    from krouter import cli

    src = inspect.getsource(cli)
    assert "--host" not in src and "0.0.0.0" not in inspect.getsource(view)


def test_nothing_can_be_written_through_it(srv):
    c, _server = srv
    for method in ("POST", "PUT", "DELETE", "PATCH", "OPTIONS"):
        for path in ("/", "/api/pages", "/api/page?rel=Home.md", "/api/why?q=x"):
            status, headers, _b = c.req(method, path)
            assert status == 405 and headers.get("Allow") == "GET, HEAD", (method, path, status)
    # the handler class has no method for any verb but GET/HEAD (and the ones that refuse)
    verbs = {n[3:] for n, _f in inspect.getmembers(view.Handler, inspect.isfunction) if n.startswith("do_")}
    assert verbs == {"GET", "HEAD", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"}
    for v in verbs - {"GET", "HEAD"}:
        assert getattr(view.Handler, "do_" + v) is view.Handler._refuse
    # the api routes: every one is a read; the module imports no way to write a page
    src = inspect.getsource(view)
    assert not re.search(r"\.write_text|\.write_bytes|open\([^)]*['\"]w", src)
    # and a request really leaves the memory as it was
    vault = srv[1].store.vault
    before = {p: p.read_bytes() for p in vault.rglob("*") if p.is_file() and ".git" not in p.parts}
    c.json("/api/why?q=how%20do%20we%20deploy%20to%20production")
    c.req("POST", "/api/pages")
    assert {p: p.read_bytes() for p in vault.rglob("*") if p.is_file() and ".git" not in p.parts} == before


def test_other_hosts_are_refused(srv):
    c, _s = srv
    status, _h, _b = c.req("GET", "/api/stats", {"Host": "evil.example"})
    assert status == 403
    status, _h, _b = c.req("GET", "/api/stats", {"Host": f"localhost:{c.port}"})
    assert status == 200


def test_the_static_page_and_every_response_refer_to_nothing_outside(srv):
    c, _s = srv
    paths = ["/", "/app.js", "/app.css", "/api/config", "/api/stats", "/api/pages", "/api/experience", "/api/nightly",
             "/api/why?q=when%20do%20we%20ship%20releases", "/api/page?rel=02%20Methods%2FDeploy%20checklist.md",
             "/api/graph?rel=02%20Methods%2FDeploy%20checklist.md"]
    external = re.compile(r"(?i)(https?:)?//[a-z0-9][a-z0-9.-]*\.[a-z]{2,}|\bsrc\s*=\s*[\"']?//|@import|url\(\s*[\"']?https?:")
    for p in paths:
        status, headers, body = c.get(p)
        assert status == 200, p
        text = body.decode("utf-8")
        assert not external.search(text), (p, external.search(text).group(0))
        csp = headers["Content-Security-Policy"]
        assert "default-src 'none'" in csp and "script-src 'self'" in csp and "http" not in csp
        assert "unsafe-inline" not in csp and "unsafe-eval" not in csp
        assert headers["Cache-Control"] == "no-store" and "Access-Control-Allow-Origin" not in headers
    html = c.get("/")[2].decode()
    urls = re.findall(r"""(?:src|href)=["']([^"']+)""", html)
    assert "/app.css" in urls and "/app.js" in urls
    assert all(u.startswith(("/", "#")) and not u.startswith("//") for u in urls)  # same origin, or an in-page route
    js = c.get("/app.js")[2].decode()
    assert "fetch(" in js and "XMLHttpRequest" not in js and "WebSocket" not in js and "innerHTML" in js
    assert not re.search(r"""fetch\(\s*["']https?""", js) and "style=" not in js  # no inline style: the CSP forbids it


def test_pages_come_one_screen_at_a_time_with_a_total(srv):
    c, _s = srv
    allp = c.json("/api/pages?limit=200")
    n = allp["total"]
    assert n == len(allp["items"]) and n >= 30 and allp["offset"] == 0
    a = c.json("/api/pages?limit=10&offset=0")
    b = c.json("/api/pages?limit=10&offset=10")
    assert len(a["items"]) == len(b["items"]) == 10 and a["total"] == b["total"] == n
    assert {i["rel"] for i in a["items"]}.isdisjoint({i["rel"] for i in b["items"]})
    assert [i["rel"] for i in a["items"] + b["items"]] == [i["rel"] for i in allp["items"][:20]]
    assert len(c.json("/api/pages?limit=100000")["items"]) <= viewdata.MAX_LIST
    assert c.json("/api/pages?limit=5&offset=100000")["items"] == []
    assert all(i["status"] == "superseded" for i in c.json("/api/pages?status=superseded")["items"])
    assert {i["tier"] for i in c.json("/api/pages?tier=dead&limit=200")["items"]} == {"dead"}
    recent = c.json("/api/pages?sort=recent&limit=3")["items"]
    assert recent and recent[0]["modified"] >= recent[-1]["modified"]


def test_search_finds_by_path_title_and_words(srv):
    c, _s = srv
    by_path = c.json("/api/pages?q=Rollback")
    assert by_path["items"][0]["rel"].endswith("Rollback plan.md")
    by_word = c.json("/api/pages?q=migration")
    assert any(i["rel"].endswith("Deploy checklist.md") for i in by_word["items"])
    assert c.json("/api/pages?q=zzzzqqqq")["items"] == []
    assert c.json("/api/pages?q=%22%20OR%20%28")["total"] >= 0  # an odd query does not break it


def test_one_page_shows_its_text_what_replaced_it_and_where_it_links(srv):
    c, _s = srv
    old = c.json("/api/page?rel=02%20Methods%2FRelease%20day.md")
    assert old["status"] == "superseded" and old["replaced_by"][0]["rel"].endswith("Release day, changed.md")
    new = c.json("/api/page?rel=02%20Methods%2FRelease%20day%2C%20changed.md")
    assert new["replaces"][0]["rel"].endswith("Release day.md") and "Tuesday" in new["body"]
    dep = c.json("/api/page?rel=02%20Methods%2FDeploy%20checklist.md")
    assert dep["links"] and all(v.endswith(".md") for v in dep["links"].values())
    assert c.get("/api/page?rel=nope.md")[0] == 404
    assert c.get("/api/page?rel=../../etc/passwd")[0] == 404
    assert c.get("/api/page?rel=%2Fetc%2Fpasswd")[0] == 404
    assert c.get("/api/graph?rel=nope.md")[0] == 404


def test_a_secret_page_shows_its_path_only_and_keys_are_masked(env, tmp_path):
    v = tmp_path / "v"
    shutil.copytree(env["en"], v, ignore=shutil.ignore_patterns(".git"))
    (v / "02 Methods" / "API credentials.md").write_text("# creds\n\nthe key is sk-abcdefghijklmnopqrstuvwxyz123456\n", encoding="utf-8")
    (v / "02 Methods" / "Notes.md").write_text("# Notes\n\nTOKEN=abcdef1234567890abcdef12 and sk-abcdefghijklmnopqrstuvwxyz123456\n",
                                              encoding="utf-8")
    s = Store(v)
    s.refresh(force=True)
    secret = s.page("02 Methods/API credentials.md")
    assert secret["secret"] and secret["body"] == "" and secret["meta"] == {}
    notes = s.page("02 Methods/Notes.md")
    assert "abcdefghijklmnopqrstuvwxyz123456" not in notes["body"] and "abcdef1234567890abcdef12" not in notes["body"]


def test_connections_say_why_each_edge_exists_and_how_strong(srv):
    c, _s = srv
    g = c.json("/api/graph?rel=02%20Methods%2FDeploy%20checklist.md")
    by = {n["rel"].rsplit("/", 1)[-1]: n for n in g["neighbors"]}
    kinds = {e["kind"] for e in by["Rollback plan.md"]["edges"]}
    assert {"link", "cocite", "words"} <= kinds
    link = next(e for e in by["Rollback plan.md"]["edges"] if e["kind"] == "link")
    assert link["direction"] == "out" and link["strength"] == 0.6
    assert next(e for e in by["Topic releases.md"]["edges"] if e["kind"] == "link")["direction"] == "in"
    assert all(0 < n["strength"] for n in g["neighbors"]) and g["neighbors"] == sorted(
        g["neighbors"], key=lambda n: (-n["strength"], -len(n["edges"]), n["rel"]))
    # supersession keeps its direction
    r = c.json("/api/graph?rel=02%20Methods%2FRelease%20day%2C%20changed.md")
    sup = next(e for n in r["neighbors"] for e in n["edges"] if e["kind"] == "supersedes")
    assert sup["direction"] == "replaces"
    d = c.json("/api/graph?rel=02%20Methods%2FRelease%20day.md")
    assert next(e for n in d["neighbors"] for e in n["edges"] if e["kind"] == "supersedes")["direction"] == "replaced_by"
    # same session pages are listed, with the count
    s = c.json("/api/graph?rel=05%20Journal%2FSessions%2F2026-11-03%EF%BD%9CBilling%20retries%20session.md")
    assert any(e["kind"] == "session" for n in s["neighbors"] for e in n["edges"])


def test_experience_cards_with_how_often_they_were_offered_and_adopted(srv):
    c, _s = srv
    x = c.json("/api/experience")
    cards = {k["id"]: k for k in x["cards"]}
    assert set(cards) == {"C01", "C02", "C03"} and x["on"]
    assert (cards["C01"]["offered"], cards["C01"]["adopted"], cards["C01"]["again"]) == (1, 1, 1)
    assert (cards["C02"]["offered"], cards["C02"]["adopted"]) == (2, 0) and cards["C03"]["offered"] == 0
    assert x["cards"][0]["id"] == "C01"  # adopted first, as the session-start digest lists them
    assert x["drafts"] == [] and x["skills"] == [] and x["events"]


def test_skills_are_listed_when_they_exist_and_their_absence_is_not_an_error(env, tmp_path):
    v = tmp_path / "v"
    shutil.copytree(env["en"], v, ignore=shutil.ignore_patterns(".git"))
    (v / "02 Methods" / "Skill draft: triage.md").write_text("---\ntitle: Triage\ntype: skill-draft\nstatus: draft\n---\n\n# Triage\n",
                                                             encoding="utf-8")
    (v / "02 Methods" / "Skill: review.md").write_text("---\ntitle: Review\ntype: skill\nstatus: active\n---\n\n# Review\n",
                                                       encoding="utf-8")
    s = Store(v)
    s.refresh(force=True)
    x = s.experience()
    assert [d["title"] for d in x["drafts"]] == ["Triage"] and [d["title"] for d in x["skills"]] == ["Review"]
    empty = tmp_path / "empty"
    shutil.copytree(REPO / "template", empty)
    e = Store(empty)
    e.refresh(force=True)
    out = e.experience()
    assert out["cards"] == [] and out["drafts"] == [] and out["skills"] == [] and out["events"] == []
    n = e.nightly()
    assert n["report"] is None and n["runs"] == [] and n["history"] == [] and n["learned"]["count"] == 0
    assert e.stats()["pages"] > 0


def test_last_night_from_the_report_the_ledger_and_the_git_history(srv):
    c, _s = srv
    n = c.json("/api/nightly")
    assert n["report"]["state"] == "ok" and n["report"]["at"].startswith("2026-11-08")
    assert [s["step"] for s in n["report"]["steps"]][:2] == ["import_sessions", "reconsolidate"]
    assert {o["step"] for o in n["off"]} == {"import_sessions", "backup"} and all(o["reason"] for o in n["off"])
    assert [h["at"][:10] for h in n["history"]] == ["2026-11-07", "2026-11-06"] and n["history"][0]["state"] == "skipped"
    assert len(n["runs"]) == 2 and n["runs"][0]["superseded"] == 1 and n["runs"][1]["added"] == 1
    assert any("Database choice" in ln for ln in n["runs"][0]["lines"])
    assert n["corrections"] and "9:30" in n["corrections"][0]
    assert n["learned"]["count"] == 2 and n["learned"]["recent"][0]["page"].endswith(".md")
    en = c.json("/api/nightly?lang=en")
    assert all(not re.search(r"[一-鿿]", o["reason"]) for o in en["off"])
    assert any(ln.startswith("- Added") for r in en["runs"] for ln in r["lines"])
    cjk = re.compile(r"[一-鿿]")
    assert not any(cjk.search(x["reason"] + x["calls"]) for x in en["report"]["steps"])
    assert not any(cjk.search(x) for x in en["report"]["notes"])
    assert en["report"]["steps"][0]["calls"] == "0 calls / 0 chars"
    zh = c.json("/api/nightly")  # without lang the job's own (Chinese) words are left as written
    assert zh["report"]["steps"][0]["calls"] == "0 次 / 0 字"


def test_the_constants_the_viewer_reads_by_still_match_the_writers():
    sys.path.insert(0, str(viewdata.mods().ri.__file__ and Path(viewdata.mods().ri.__file__).parent))
    import corrections
    import nightly
    import reconsolidate

    assert viewdata.REPORT == nightly.REPORT and viewdata.CORRECTIONS == corrections.LOG_PAGE
    assert viewdata.LEARNED == reconsolidate.DEFAULT_OUT


def test_try_a_sentence_shows_what_why_shows(srv, env):
    c, _s = srv
    for q in ("how do we deploy to production", "which database does the billing service use", "what is our on-call rotation",
              "deploy checklist"):
        r = c.json("/api/why?q=" + q.replace(" ", "%20"))
        e = why.explain(env["en"], q, refresh=False)
        assert r["text"] == why.render(e)
        assert r["blocks"] == why.blocks(e) and set(r["pages"]) == set(why.pages_in(e))
    zh = c.json("/api/why?lang=zh&q=when%20do%20we%20ship%20releases")
    assert "一、别名锁" in zh["text"]
    assert c.json("/api/why?q=")["explanation"]["verdict"] == "none"  # an empty box is not an error


def test_a_large_memory_is_paged_and_a_page_costs_a_screen_not_the_memory(tmp_path, monkeypatch):
    monkeypatch.setenv("KROUTER_CACHE_DIR", str(tmp_path / "cache"))
    big = sample.build_big(tmp_path, 3000)
    s = Store(big)
    s.refresh(force=True)
    server = view.Server(s, 0)
    th = threading.Thread(target=server.serve_forever, daemon=True)
    th.start()
    try:
        c = Client(server)
        status, _h, body = c.get("/api/pages?limit=50")
        assert status == 200 and len(body) < 60_000
        r = json.loads(body)
        assert r["total"] == 3000 and len(r["items"]) == 50
        assert json.loads(c.get("/api/pages?limit=50&offset=2950")[2])["items"][-1]["rel"] > r["items"][0]["rel"]
        found = c.json("/api/pages?q=billing%20invoice&limit=20")
        assert len(found["items"]) == 20 and found["total"] <= viewdata.SEARCH_CAP
        assert len(c.get("/api/stats")[2]) < 5_000
    finally:
        server.shutdown()
        server.server_close()


def test_view_command_wiring(env, monkeypatch):
    from krouter import cli

    seen = {}
    monkeypatch.setattr(view, "run", lambda *a, **k: seen.update(args=a) or 0)
    assert cli.main(["--vault", str(env["en"]), "view"]) == 0
    assert seen["args"][1:4] == (0, False, False)  # random port, no browser, not the demo
    assert cli.main(["--vault", str(env["en"]), "view", "--port", "8765", "--open"]) == 0
    assert seen["args"][1:3] == (8765, True)
