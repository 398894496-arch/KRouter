"""Set 53 (bench/memory_honesty/HELDOUT.md): a question to the vault, the closest pages as candidates, and a reader that
says which one answers it, or none. A bench-side prototype: `krouter_ask` does not do this yet.

Two candidate sources, everything else the same:

- `krouter`: KRouter's recall with its refusal gate off (`gate=False`), the first K pages in force.
- `bm25`: plain BM25 over the same pages, superseded pages left out (the "BM25 with KRouter's rules" baseline of the
  third bench, without its floor: the reader decides instead).

Each candidate is shown the same way whatever its source: its title and the start of its text (EXCERPT characters, the
front matter left out). One call a question; the reply is a number, 0 for none. Replies are cached by prompt in
`results/<model>/cache.jsonl`, so a rerun spends nothing on a question already asked.

The answers come out in `bench/memory_honesty/run.py`'s format (`refused`, `cited`), graded with its own `score`.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "bench/memory_honesty"))
sys.path.insert(0, str(REPO / "skill/krouter/scripts"))

import run as mh  # noqa: E402

K = 5
EXCERPT = 240
URL = "https://api.deepseek.com/chat/completions"
MODEL = "deepseek-flash"
MAX_TOKENS = 1500
ASK = ("Below is a question someone asked their own memory vault, and the vault pages closest to it (number, title, "
       "the start of the page). Decide which page answers the question. A page about a neighbouring matter, or one that "
       "only shares words with the question, does not answer it.\n"
       "Answer with one number only: the page's number, or 0 if none of them answers the question. No explanation.\n\n"
       "The question: {q}\n\n{pages}\n")


def key() -> str:
    if os.environ.get("DEEPSEEK_API_KEY"):
        return os.environ["DEEPSEEK_API_KEY"]
    f = Path.home() / ".config/krouter-bench/deepseek.env"
    for line in f.read_text(encoding="utf-8").splitlines():
        if line.startswith("DEEPSEEK_API_KEY="):
            return line.split("=", 1)[1].strip().strip("'\"")
    raise SystemExit("no DEEPSEEK_API_KEY")


def excerpt(vault: Path, rel: str) -> tuple[str, str]:
    """(title, the start of the text) of a page, front matter and the H1 left out."""
    text = (vault / rel).read_text(encoding="utf-8", errors="replace")
    title = Path(rel).stem
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            m = re.search(r"^title:\s*(.+)$", text[:end], re.M)
            title = m.group(1).strip().strip("'\"") if m else title
            text = text[end + 4:]
    lines = [ln for ln in text.splitlines() if ln.strip() and not ln.startswith("# ")]
    return title, re.sub(r"\s+", " ", " ".join(lines))[:EXCERPT]


def prompt(q: str, vault: Path, cands: list[str]) -> str:
    pages = []
    for i, rel in enumerate(cands, 1):
        title, start = excerpt(vault, rel)
        pages.append(f"{i}. {title}: {start}")
    return ASK.format(q=q.strip(), pages="\n".join(pages))


def pick(reply: str, n: int) -> int:
    m = re.search(r"\d+", reply or "")
    v = int(m.group()) if m else 0
    return v if 1 <= v <= n else 0


class Reader:
    def __init__(self, model: str, url: str):
        self.model, self.url, self.k = model, url, key()
        self.dir = HERE / "results" / model
        self.dir.mkdir(parents=True, exist_ok=True)
        self.path = self.dir / "cache.jsonl"
        self.cache = {}
        if self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                row = json.loads(line)
                self.cache[row["h"]] = row
        self.lock = threading.Lock()
        self.spent = 0

    def __call__(self, text: str) -> dict:
        h = hashlib.sha256(f"{self.model}\n{text}".encode()).hexdigest()[:24]
        if h in self.cache:
            return self.cache[h]
        body = json.dumps({"model": self.model, "messages": [{"role": "user", "content": text}], "temperature": 0,
                           "max_tokens": MAX_TOKENS}).encode()
        req = urllib.request.Request(self.url, data=body, headers={"Content-Type": "application/json",
                                                                   "Authorization": f"Bearer {self.k}"})
        t0, reply, err = time.time(), "", ""
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    data = json.loads(r.read())
                reply = (data["choices"][0]["message"].get("content") or "").strip()
                err = "" if reply else "empty"
                break
            except Exception as e:  # noqa: BLE001
                err = type(e).__name__
                time.sleep(2 * (attempt + 1))
        row = {"h": h, "reply": reply, "error": err, "seconds": round(time.time() - t0, 2)}
        with self.lock:
            self.cache[h] = row
            self.spent += 1
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        return row


def candidates(source: str, rows: list[dict], vault: Path, qset: str) -> dict[str, list[str]]:
    if source == "krouter":
        import recall_index as ri

        out = {}
        for it in rows:
            res = ri.recall(vault, it["q"], gate=False)
            out[it["id"]] = [h["rel"] for h in res["hits"]][:K]
        return out
    scored = mh.bm25_scored(rows, skip_superseded=True, vault_src=vault, cjk=qset in mh.CJK_SETS)
    return {qid: [p for p, _ in hits][:K] for qid, hits in scored}


def answers(source: str, qset: str, reader: Reader, workers: int = 8) -> tuple[list[dict], list[dict]]:
    rows = mh.questions(qset)
    with tempfile.TemporaryDirectory(prefix="krouter-askjudge-", ignore_cleanup_errors=True) as tmp:
        os.environ["KROUTER_NO_QUERY_LOG"] = "1"
        os.environ["KROUTER_CACHE_DIR"] = str(Path(tmp) / "cache")
        os.environ.pop("KROUTER_MAP", None)
        vault = Path(tmp) / "vault"
        shutil.copytree(mh.vault_of(qset), vault)
        cands = candidates(source, rows, vault, qset)
        prompts = {it["id"]: prompt(it["q"], vault, cands[it["id"]]) for it in rows if cands[it["id"]]}
        with ThreadPoolExecutor(workers) as ex:
            replies = dict(zip(prompts, ex.map(reader, prompts.values())))
    out, log = [], []
    for it in rows:
        c = cands[it["id"]]
        r = replies.get(it["id"], {"reply": "", "error": "no candidates", "seconds": 0})
        n = pick(r["reply"], len(c))
        out.append({"id": it["id"], "refused": n == 0, "cited": [c[n - 1]] if n else [], "score": None})
        log.append({"id": it["id"], "n_cands": len(c), "pick": n, "error": r["error"], "seconds": r["seconds"],
                    "gold_in_cands": bool(it["gold"]) and it["gold"] in c})
    return out, log


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", dest="qset", choices=sorted(mh.SETS), required=True)
    ap.add_argument("--source", choices=["krouter", "bm25"], required=True)
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--url", default=URL)
    ap.add_argument("--reveal", action="store_true", help="per-question misses (never on a held-out set)")
    args = ap.parse_args()
    reader = Reader(args.model, args.url)
    ans, log = answers(args.source, args.qset, reader)
    tag = f"{args.qset}-{args.source}"
    (reader.dir / f"{tag}.answers.jsonl").write_text("".join(json.dumps(a, ensure_ascii=False) + "\n" for a in ans),
                                                     encoding="utf-8")
    res = mh.score(mh.questions(args.qset), ans)
    secs = sorted(x["seconds"] for x in log if x["seconds"])
    summary = {"set": args.qset, "source": args.source, "model": args.model, **mh.aggregate(res),
               "gold_in_candidates": sum(x["gold_in_cands"] for x in log),
               "errors": sum(1 for x in log if x["error"] and x["error"] != "no candidates"),
               "median_seconds": secs[len(secs) // 2] if secs else None, "calls_made": reader.spent}
    if args.reveal and args.qset not in mh.HELDOUT_SETS:
        summary["misses"] = res["misses"]
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
