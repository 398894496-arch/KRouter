#!/usr/bin/env python3
"""Prototype: dense retrieval on the memory honesty bench, alone and combined with KRouter. Not part of the product.

Embeddings run locally (fastembed, ONNX; the model is downloaded once), so questions never leave the machine. Model:
`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` (English and Chinese), or any fastembed model through
`KROUTER_DENSE_MODEL`; `BAAI/bge-m3` is registered here from the ONNX export in its own repository (CLS pooling). Pages are embedded as title +
body without frontmatter; vectors are cached under `KROUTER_CACHE_DIR` (or a temp dir) by model and page hash.

Variants, each with superseded pages handled like KRouter does:
- `dense`:  cosine top hit, superseded pages left out, refuse below a floor picked on the dev set (`run.pick_floor`).
- `rescue`: KRouter first; when KRouter refuses, answer with its own best page if the dense top hit is that same page
            and the dense score clears a floor picked on the dev set. KRouter's off-vault checks still apply first.
- `gate`:   dense ranking, KRouter's refusal decision (refuse when KRouter refuses), superseded links followed.

Floors are always picked on a dev set of another vault when the run's vault has none: dev3 (vault2) for vault3, as
`run.py`'s `bm25-floor` does. `--ci` adds 95% bootstrap intervals and paired ones against KRouter's default (same
resamples and seed as `run.py`); on held-out sets only aggregates are printed.

    python3 bench/memory_honesty/dense.py --set dev3
    KROUTER_DENSE_MODEL=BAAI/bge-m3 python3 bench/memory_honesty/dense.py --set heldout3 --variant agree --ci
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
spec = importlib.util.spec_from_file_location("mh_bench_dense", HERE / "run.py")
bench = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bench)
MODEL = os.environ.get("KROUTER_DENSE_MODEL", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
_EMB = None


def embedder():
    global _EMB
    if _EMB is None:
        from fastembed import TextEmbedding

        if MODEL == "BAAI/bge-m3" and MODEL not in {m["model"] for m in TextEmbedding.list_supported_models()}:
            from fastembed.common.model_description import ModelSource, PoolingType

            TextEmbedding.add_custom_model(model=MODEL, pooling=PoolingType.CLS, normalization=True,
                                           sources=ModelSource(hf=MODEL), dim=1024, model_file="onnx/model.onnx",
                                           additional_files=["onnx/model.onnx_data"])
        _EMB = TextEmbedding(MODEL)
    return _EMB


def embed(texts: list[str], kind: str = "query") -> list[list[float]]:
    import numpy as np

    if "e5" in MODEL.lower():  # e5 models are trained with these prefixes; without them they score lower
        texts = [("query: " if kind == "query" else "passage: ") + t for t in texts]
    vecs = list(embedder().embed(texts))
    return [list(v / (np.linalg.norm(v) or 1.0)) for v in vecs]


def page_text(path: Path) -> tuple[str, dict]:
    raw = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    meta: dict[str, str] = {}
    body = raw
    if raw.startswith("---\n"):
        head, _, body = raw[4:].partition("\n---")
        for line in head.splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip()] = v.strip().strip('"')
    return (meta.get("title") or path.stem) + "\n" + body.strip("-\n "), meta


VAULT = bench.HERE / "vault"  # set by main() from the question set: vault/ or vault2/


def pages() -> list[tuple[str, str, dict]]:
    root = VAULT
    out = []
    for path in sorted(root.rglob("*.md")):
        text, meta = page_text(path)
        out.append((path.relative_to(root).as_posix(), text, meta))
    return out


def page_vectors() -> dict[str, list[float]]:
    cache = Path(os.environ.get("KROUTER_DENSE_CACHE") or os.environ.get("KROUTER_CACHE_DIR") or tempfile.gettempdir()) / "krouter-dense"
    cache.mkdir(parents=True, exist_ok=True)
    ps = pages()
    key = hashlib.sha1((MODEL + "".join(r + t for r, t, _ in ps)).encode("utf-8")).hexdigest()[:16]
    f = cache / f"{key}.json"
    if f.is_file():
        return json.loads(f.read_text())
    vecs = embed([t for _, t, _ in ps], kind="passage")
    data = {r: [float(x) for x in v] for (r, _, _), v in zip(ps, vecs)}
    f.write_text(json.dumps(data))
    return data


def superseded() -> set[str]:
    return {r for r, _, m in pages() if m.get("status", "").lower() == "superseded"}


def on_vault(path: Path):
    """Temporarily point the prototype at another vault (to pick floors on dev3 / vault2 for a vault3 run)."""
    import contextlib

    @contextlib.contextmanager
    def _cm():
        global VAULT
        old = VAULT
        VAULT = path
        try:
            yield
        finally:
            VAULT = old
    return _cm()


def dense_scored(rows: list[dict], skip: bool = True) -> list[tuple[str, list[tuple[str, float]]]]:
    import numpy as np

    pv = page_vectors()
    dead = superseded() if skip else set()
    rels = [r for r in pv if r not in dead]
    mat = np.array([pv[r] for r in rels])
    qv = np.array(embed([it["q"] for it in rows]))
    out = []
    for it, v in zip(rows, qv):
        sims = mat @ v
        order = np.argsort(-sims)[:3]
        out.append((it["id"], [(rels[i], float(sims[i])) for i in order]))
    return out


def dev_name() -> str:
    """The dev set floors are picked on: dev3 for the bilingual vaults (vault2, vault3, which has no dev set)."""
    return "dev3" if VAULT.name in ("vault2", "vault3") else "dev"


def dense_answers(rows: list[dict]) -> list[dict]:
    floor = dense_floor()
    return bench.floor_answers(dense_scored(rows), floor)


def _krouter_raw(rows: list[dict], src: Path | None = None) -> list[dict]:
    """KRouter's recall with its decision and its best page even when it refuses."""
    sys.path.insert(0, str(REPO / "skill/krouter/scripts"))
    os.environ["KROUTER_NO_QUERY_LOG"] = "1"
    with tempfile.TemporaryDirectory(prefix="krouter-dense-", ignore_cleanup_errors=True) as tmp:
        os.environ["KROUTER_CACHE_DIR"] = str(Path(tmp) / "cache")
        vault = Path(tmp) / "vault"
        shutil.copytree(src or VAULT, vault)
        import recall_index as ri

        out = []
        for it in rows:
            res = ri.recall(vault, it["q"], limit=3)
            out.append({"id": it["id"], "refused": res["confidence"] == "none" or not res["hits"],
                        "top": res["hits"][0]["rel"] if res["hits"] else None,
                        "cited": [h["rel"] for h in res["hits"]]})
        return out


def rescue_floor(dn_name: str | None = None) -> float:
    dn_name = dn_name or dev_name()
    dev = bench.questions(dn_name)
    with on_vault(bench.vault_of(dn_name)):
        kd, dd = _krouter_raw(dev), dict(dense_scored(dev))
    cands = sorted({h[0][1] for h in dd.values() if h})
    best, floor = None, 1.0
    for f in cands:
        res = bench.score(dev, _rescue(kd, dd, f))
        util = int(res["correction_hit"].split("/")[0]) + int(res["current_hit"].split("/")[0]) - res["wrong_citations"]
        if best is None or util > best:
            best, floor = util, f
    return floor


def rescue_answers(rows: list[dict], floor: float | None = None) -> list[dict]:
    if floor is None:
        floor = rescue_floor()
    return _rescue(_krouter_raw(rows), dict(dense_scored(rows)), floor)


def _rescue(kr: list[dict], dd: dict, floor: float) -> list[dict]:
    out = []
    for a in kr:
        if not a["refused"]:
            out.append({"id": a["id"], "refused": False, "cited": a["cited"]})
            continue
        hits = dd.get(a["id"]) or []
        ok = bool(hits) and hits[0][1] >= floor and a["top"] is not None and hits[0][0] == a["top"]
        out.append({"id": a["id"], "refused": not ok, "cited": [hits[0][0]] if ok else []})
    return out


def agree_answers(rows: list[dict], lex_floor: float | None = None, dense_floor: float | None = None) -> list[dict]:
    """Two independent retrievers must agree: lexical (BM25 over character pairs and words, superseded pages left
    out) and dense. A neighbour question tends to look like one page to one of them and another page to the other;
    a real question about a page tends to land on it in both. Answer only when their top pages agree and each clears
    a floor picked on the dev set (one sweep over both floors, same utility as `run.pick_floor`)."""
    if lex_floor is None or dense_floor is None:
        lex_floor, dense_floor = agree_floors()
    return _agree(rows, dict(lex_scored(rows)), dict(dense_scored(rows)), lex_floor, dense_floor)


def agree_floors(dn_name: str | None = None) -> tuple[float, float]:
    """Both floors of `agree`, picked together on the dev set (one sweep, same utility as `run.pick_floor`)."""
    dn_name = dn_name or dev_name()
    dev = bench.questions(dn_name)
    with on_vault(bench.vault_of(dn_name)):
        lx, dn = dict(lex_scored(dev)), dict(dense_scored(dev))
    lcands = sorted({0.0} | {h[0][1] for h in lx.values() if h})
    dcands = sorted({-1.0} | {h[0][1] for h in dn.values() if h})
    best = None
    for lf in lcands[:: max(1, len(lcands) // 25)]:
        for df in dcands[:: max(1, len(dcands) // 25)]:
            res = bench.score(dev, _agree(dev, lx, dn, lf, df))
            util = int(res["correction_hit"].split("/")[0]) + int(res["current_hit"].split("/")[0]) - res["wrong_citations"]
            if best is None or util > best[0]:
                best = (util, lf, df)
    return best[1], best[2]


def dense_floor(dn_name: str | None = None) -> float:
    dn_name = dn_name or dev_name()
    dev = bench.questions(dn_name)
    with on_vault(bench.vault_of(dn_name)):
        return bench.pick_floor(dev, dense_scored(dev))


def chunks(text: str, size: int = 600) -> list[str]:
    """Pieces of at most `size` characters, cut at line ends where possible. Short pages (every bench vault page is
    under 600 characters) stay one piece, so on vault2 / vault3 this scores exactly like `dense_scored`."""
    out, cur = [], ""
    for line in text.splitlines(keepends=True):
        while len(line) > size:
            if cur:
                out.append(cur)
                cur = ""
            out.append(line[:size])
            line = line[size:]
        if len(cur) + len(line) > size and cur:
            out.append(cur)
            cur = ""
        cur += line
    if cur.strip():
        out.append(cur)
    return [c.strip() for c in out if c.strip()] or [text[:size]]


def chunk_scored(vault: Path, rows: list[dict], k: int = 3) -> list[tuple[str, list[tuple[str, float]]]]:
    """Dense ranking for long pages (imported chat sessions): each page is cut into `chunks`, a page scores its best
    piece. Superseded pages are left out. The first piece carries the title, as in `page_text`."""
    import numpy as np

    cache = Path(os.environ.get("KROUTER_DENSE_CACHE") or tempfile.gettempdir()) / "krouter-dense-chunks"
    cache.mkdir(parents=True, exist_ok=True)
    rels, pieces = [], []
    for path in sorted(vault.rglob("*.md")):
        text, meta = page_text(path)
        if meta.get("status", "").lower() == "superseded":
            continue
        rel = path.relative_to(vault).as_posix()
        for c in chunks(text):
            rels.append(rel)
            pieces.append(c)
    key = hashlib.sha1((MODEL + "\x00".join(pieces)).encode("utf-8")).hexdigest()[:16]
    f = cache / f"{key}.npy"
    if f.is_file():
        mat = np.load(f)
    else:
        mat = np.array(embed(pieces, kind="passage"), dtype=np.float32) if pieces else np.zeros((0, 1), np.float32)
        np.save(f, mat)
    qv = np.array(embed([it["q"] for it in rows]), dtype=np.float32)
    out = []
    for it, v in zip(rows, qv):
        best: dict[str, float] = {}
        for rel, sim in zip(rels, (mat @ v).tolist() if len(rels) else []):
            if sim > best.get(rel, -2.0):
                best[rel] = sim
        top = sorted(best.items(), key=lambda kv: -kv[1])[:k]
        out.append((it["id"], [(r, float(x)) for r, x in top]))
    return out


def session_answers(system: str, vault: Path, rows: list[dict], floors: dict) -> list[dict]:
    """The dense systems on a vault of long pages (LongMemEval, LoCoMo), floors picked on dev3 beforehand:
    `dense` (top 3, no floor: ranking only), `dense-floor`, `agree` (BM25 and dense top page agree, both above their
    dev3 floors), `rescue` (KRouter, plus its refusals answered when dense puts KRouter's best page first above the
    dev3 floor)."""
    dn = dict(chunk_scored(vault, rows))
    if system == "dense":
        return [{"id": it["id"], "refused": not dn[it["id"]], "cited": [h[0] for h in dn[it["id"]]]} for it in rows]
    if system == "dense-floor":
        return bench.floor_answers([(it["id"], dn[it["id"]]) for it in rows], floors["dense"])
    if system == "agree":
        lx = dict(bench.bm25_scored(rows, vault_src=vault, cjk=True))
        return _agree(rows, lx, dn, *floors["agree"])
    if system == "rescue":
        return _rescue(_krouter_raw(rows, vault), dn, floors["rescue"])
    raise ValueError(system)


def session_floors() -> dict:
    with on_vault(bench.vault_of("dev3")):
        return {"dense": dense_floor("dev3"), "agree": list(agree_floors("dev3")), "rescue": rescue_floor("dev3"),
                "model": MODEL}


def lex_scored(rows: list[dict]):
    return bench.bm25_scored(rows, vault_src=VAULT, cjk=True)


def _agree(rows, lx, dn, lf, df):
    out = []
    for it in rows:
        a, b = lx.get(it["id"]) or [], dn.get(it["id"]) or []
        ok = bool(a and b) and a[0][0] == b[0][0] and a[0][1] >= lf and b[0][1] >= df
        out.append({"id": it["id"], "refused": not ok, "cited": [a[0][0]] if ok else []})
    return out


def vote_answers(rows: list[dict]) -> list[dict]:
    """`agree`, plus KRouter's own answers that the dense retriever confirms (same top page). Two pairs of independent
    signals; an answer needs one pair to agree. Floors for the lexical/dense pair come from `agree` (picked on dev)."""
    base = {a["id"]: a for a in agree_answers(rows)}
    dn = dict(dense_scored(rows))
    out = []
    for k in _krouter_raw(rows):
        a = base[k["id"]]
        hits = dn.get(k["id"]) or []
        if a["refused"] and not k["refused"] and hits and k["top"] == hits[0][0]:
            a = {"id": k["id"], "refused": False, "cited": k["cited"]}
        out.append(a)
    return out


def gate_answers(rows: list[dict]) -> list[dict]:
    kr = {a["id"]: a for a in _krouter_raw(rows)}
    out = []
    for qid, hits in dense_scored(rows):
        refused = kr[qid]["refused"] or not hits
        out.append({"id": qid, "refused": refused, "cited": [] if refused else [h[0] for h in hits]})
    return out


def by_lang(rows: list[dict], ans: list[dict], base: list[dict] | None) -> dict:
    """Aggregates on the Chinese questions (any CJK character) and the English ones apart; nothing per question."""
    out = {}
    for lang in ("zh", "en"):
        sub = [r for r in rows if bool(re.search(r"[\u4e00-\u9fff]", r["q"])) == (lang == "zh")]
        res = bench.aggregate(bench.score(sub, ans))
        out[lang] = {"n": len(sub), "wrong": f"{res['wrong_citations']}/{res['answered']}", "refused": res["refused"],
                     "right": int(res["correction_hit"].split("/")[0]) + int(res["current_hit"].split("/")[0])}
        if base is not None:
            out[lang]["delta_ci95"] = {k: v for k, v in bench.bootstrap(sub, ans, base).items() if k.startswith("delta")}
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", default="dev")
    ap.add_argument("--variant", choices=["dense", "rescue", "gate", "agree", "vote", "all"], default="all")
    ap.add_argument("--ci", action="store_true", help="95%% bootstrap intervals, and paired ones against KRouter's default")
    ap.add_argument("--by-lang", action="store_true", help="also the aggregates on the Chinese and the English questions apart")
    args = ap.parse_args()
    global VAULT
    VAULT = bench.vault_of(args.set)
    rows = bench.questions(args.set)
    variants = ["dense", "rescue", "gate", "agree", "vote"] if args.variant == "all" else [args.variant]
    base = bench.krouter_answers(rows, VAULT) if args.ci else None
    for v in variants:
        ans = {"dense": dense_answers, "rescue": rescue_answers, "gate": gate_answers, "agree": agree_answers, "vote": vote_answers}[v](rows)
        res = bench.score(rows, ans)
        if args.set in bench.HELDOUT_SETS:
            res = bench.aggregate(res)
        right = int(res["correction_hit"].split("/")[0]) + int(res["current_hit"].split("/")[0])
        line = {"variant": v, "model": MODEL, "wrong": f"{res['wrong_citations']}/{res['answered']}",
                "wrong_rate": res["wrong_citation_rate"], "refused": res["refused"], "right": right,
                "corr": res["correction_hit"], "cur": res["current_hit"]}
        if base is not None:
            line["ci95"] = bench.bootstrap(rows, ans, base)  # delta_* = this variant minus KRouter's default
        if args.by_lang:
            line["by_lang"] = by_lang(rows, ans, base)
        print(json.dumps(line, ensure_ascii=False))
    if args.by_lang and base is not None:
        print(json.dumps({"variant": "krouter-default", "by_lang": by_lang(rows, base, None)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
