"""Plain BM25 over the pages, nothing else: the naive baseline.

No stemming, no stop words, no alias table, no trigger words, no model. Latin text is split into lowercase words; Chinese
(any CJK run) into overlapping character pairs (a lone character on its own). It hands over the single best page when
that page's score is at least `floor`, otherwise it stays quiet.

Options (`--opt key=value`):
  floor=0            0 means "always speak": the top page for every message (the naive reading of "search the memory")
  live_only=0        1 leaves pages whose status is `superseded` out of the index (what a careful baseline adds)
  use_names=0        1 adds the names listed for each page (pages[].names, KRouter's alias table) to the page's text
  k1=1.5, b=0.75     the usual BM25 constants

The floor of the "careful" row in README.md was picked on set 35's development half, never on set 45's.
"""
import math
import re
from collections import Counter

_LATIN = re.compile(r"[a-z0-9]+")
_CJK = re.compile(r"[㐀-鿿豈-﫿]+")
_docs = []
_df = Counter()
_avg = 0.0
_opt = {}


def tokens(text):
    text = text.lower()
    out = _LATIN.findall(text)
    for run in _CJK.findall(text):
        out += [run] if len(run) == 1 else [run[i:i + 2] for i in range(len(run) - 1)]
    return out


def setup(pages, floor=0, live_only=0, use_names=0, k1=1.5, b=0.75, **_ignored):
    global _docs, _df, _avg, _opt
    _opt = {"floor": float(floor), "k1": float(k1), "b": float(b)}
    _docs, _df = [], Counter()
    for p in pages:
        if int(live_only) and p["status"] == "superseded":
            continue
        extra = "\n" + "\n".join(p.get("names", [])) if int(use_names) else ""
        tf = Counter(tokens(p["title"] + "\n" + p["text"] + extra))
        _docs.append((p["path"], tf, sum(tf.values())))
        _df.update(tf.keys())
    _avg = sum(n for _, _, n in _docs) / max(1, len(_docs))


def handle(message):
    q = Counter(tokens(message))
    if not q or not _docs:
        return []
    n = len(_docs)
    best, best_s = None, 0.0
    for path, tf, length in _docs:
        s = 0.0
        for t in q:
            f = tf.get(t, 0)
            if f:
                idf = math.log(1 + (n - _df[t] + 0.5) / (_df[t] + 0.5))
                s += idf * f * (_opt["k1"] + 1) / (f + _opt["k1"] * (1 - _opt["b"] + _opt["b"] * length / _avg))
        if s > best_s:
            best, best_s = path, s
    return [best] if best and best_s >= _opt["floor"] and best_s > 0 else []
