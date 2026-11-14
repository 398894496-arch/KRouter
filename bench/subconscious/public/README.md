# A public benchmark for "mention it and it comes to mind"

[中文](README.zh.md) · registration and log: [`HELDOUT.md`, set 45](../../memory_honesty/HELDOUT.md) · the one-command table of every
registered number that needs no model: [`bench/reproduce.py`](../../reproduce.py)

You give a system a message and a small knowledge base; it says which pages it hands over for that message, or that it stays
quiet. That is all this benchmark asks. It needs no model, no key and no network, and the scorer is plain Python.

| | |
|---|---|
| The knowledge base | 110 pages: 60 live handbook pages (30 in English, 30 in Chinese, largely parallel topics), 30 replaced pages (15 in each language) each beside its newer page, 20 daily logs as distractors. It is [`bench/memory_honesty/vault3`](../../memory_honesty/vault3). |
| The messages | 120 **invented** spoken-style messages (development half of [set 45](../../memory_honesty/HELDOUT.md)), written by two fresh Claude Sonnet 5.5 subagents from the page list alone: 48 that mention a page (42 of them name nothing the page is called), 24 about a rule that changed (the replaced page must not come), 48 that should change nothing (six kinds: unrelated, a name in another sense, a common word, pasted text, the same field but a thing the base does not hold, a bare "ok"). Sets 32 and 35 (60 messages each) fit the same interface: `--cases set32dev` / `set35dev`. |
| The score | **recall** (the expected page is among those handed over), **changed** (the new page is, and the replaced one is not counted right), **quiet loud** (a quiet message got any page), **wrong pages** (any other page on a recall or changed message), **old pages** (the replaced page handed over). Counting is the registered one, unchanged, and is the same code path as `bench/subconscious/run.py`. |

```bash
python3 bench/subconscious/public/score.py --adapter krouter-hook              # KRouter's prompt hook by itself
python3 bench/subconscious/public/score.py --adapter bm25-naive --opt live_only=1 --opt floor=22
python3 bench/subconscious/public/score.py --adapter my_adapter.py --cases set35dev --show
python3 bench/subconscious/public/score.py --adapter bm25-naive --sweep floor=0,10,20,30   # one line per value
```

## Writing an adapter (about a dozen lines)

An adapter is one Python file with two functions. `setup` is called once with the pages; `handle` is called once per message and
returns the paths of the pages the system hands over (an empty list = it stays quiet):

```python
# my_adapter.py: hand over the page whose title the message contains (a deliberately dumb system)
PAGES = []

def setup(pages, **options):                # pages: [{"path", "title", "text", "status", "names"}, ...]
    PAGES[:] = [p for p in pages if p["status"] != "superseded"]

def handle(message):                        # -> ["Handbook/Status page.md"] or []
    return [p["path"] for p in PAGES if p["title"].lower() in message.lower()][:1]
```

`status` is `superseded` for a page that a newer one replaced (the front matter says so too); `names` are the names the team listed
for the page (KRouter's alias table; an adapter may use them or ignore them); `--opt key=value` arrives as keyword arguments to
`setup`; an optional `close()` is called at the end. The scorer checks that `handle` returns a list of strings and counts any
path that is not the expected page as a wrong page.

**Not in Python?** `score.py --export DIR` writes `DIR/pages.jsonl` and `DIR/messages.jsonl` (the message text and id only; the
expected answers are not in what is handed out). Write one line per message, `{"id": "...", "pages": ["Handbook/X.md"]}` (an empty
list for quiet), and run `score.py --answers answers.jsonl`.

The two adapters that come with it do not install or call anyone else's system, and nobody else's numbers are reported here.
If you run another memory system through an adapter, say how it was configured and what was given to it; the table below is only
a reference for the two bundled ones.

## What the two bundled adapters score (development halves, recomputed by the commands above)

| Set 45 development, 120 messages | recall (of 48) | changed (of 24) | quiet loud (of 48) | wrong pages | old pages |
|---|---|---|---|---|---|
| **`krouter-hook`**: the lookup the prompt hook runs on every message (alias table and trigger words written before any case, full-text recall; no model) | **7** (1 of the 42 that name nothing) | **7** | **2** | **0** | **0** |
| `bm25-naive`, always answers (all pages, top page for every message) | 16 | 11 | 42 | 41 | 3 |
| `bm25-naive`, live pages only, always answers | 17 | 13 | 42 | 38 | 0 |
| `bm25-naive`, live pages only, floor 22 (best choice score on set 35's development half) | 4 | 4 | 2 | 2 | 0 |
| `bm25-naive`, live pages only, page names added, floor 24 (same rule) | 5 | 5 | 1 | 1 | 0 |

Set 35 development (24 recall, 12 changed, 24 quiet): `krouter-hook` 6 / 2 / 2 / 0 / 0; the four BM25 rows 10 / 1 / 23 / 24 / 8,
10 / 8 / 23 / 17 / 0, 2 / 1 / 0 / 0 / 0, 3 / 1 / 0 / 0 / 0. Set 32 development: `krouter-hook` 5 / 5 / 0 / 0 / 0; BM25 9 / 1 / 23 / 26 / 7,
8 / 5 / 23 / 23 / 0, 0 / 1 / 0 / 3 / 0, 0 / 1 / 0 / 2 / 0.

**How to read it.** A keyword matcher that answers every message finds more of the mentions than the hook (16–17 of 48 against 7) and
also names a page for 42 of the 48 messages that should change nothing: this benchmark is about not doing that as much as about
finding the page. Tuned to be as quiet as the hook (floors picked on set 35, not on set 45), plain BM25 lands in the same low range
(4–5 of 48 against 7; 1–2 loud against 2): the hook is ahead by a couple of cases, on 48 and 24 cases, with no interval (the hook's
thresholds were set on set 32's development half, never on set 45's). That is what we said elsewhere: **the hook by itself is quiet and finds little**; what lifts
the whole chain (Sonnet 5.5 44 of 48, Haiku 5.5 42 of 48 on this half) is the standing index at session start with the host model
fetching for itself, which needs a model and is not in this benchmark. A different floor, tokenizer or case set moves the BM25 rows.

## Not here, and why

- **The host layer** (the session-start index plus a model that goes and looks: the 44 / 48, 42 / 48 and 38 / 48 of
  [set 45's addendum](../../memory_honesty/HELDOUT.md)) needs a model. To run it with your own: `python3
  bench/subconscious/both.py prepare set45dev --work DIR` writes prompt batches; answer each item with the host model you want into
  `DIR/replies_<host>.jsonl`; `both.py score --work DIR --host <host>` scores them. The registered runs used Claude Code subagents on
  named models; the four runs together read and wrote 478,381 tokens. Another host model gives other numbers.
- **The held-out half of set 45** (120 messages) stays sealed. It is not reachable from `score.py` (`--cases set45held` is refused),
  is not run in `reproduce.py`, and is opened by the maintainer once, to confirm a result that was reached on the development half.
  A system adjusted against the development half has shown nothing about it.
- **Real messages.** Every message here is invented, by one model family, for one small base. It says how a system behaves on
  spoken-style messages of that kind; it is not an estimate of anyone's real use. The base holds each handbook page in Chinese and
  English, so a system that fetches the other language's twin of the right page is scored wrong (pessimistic for English).
- **Speed.** `python3 bench/reproduce.py --timing` prints this machine's hook latency, apart from everything else.
