# Roadmap

中文：[`ROADMAP.zh.md`](ROADMAP.zh.md) · back to the [README](README.md)

What is planned next, in no particular order and with no dates: nothing here is a promise, and an item is crossed out
only when it ships and its [`CHANGELOG.md`](CHANGELOG.md) entry says so. What does not work yet is listed in the README
under [What it does not do](README.md#what-it-does-not-do).

- **A better refusal rule.** A question about something near what the memory holds still gets an answer. The gate was
  analysed twice and no rule beat it: set 14 on LongMemEval, and set 37, which tried 216 coverage rules on LongMemEval,
  LoCoMo and our own sets and found the best refusing only 3 more within a 1-point loss of answers
  ([`NUMBERS.md`](docs/NUMBERS.md)); a different kind of signal is needed.
- **A public side-by-side evaluation.** Take part in a comparison someone else runs, with questions we did not write.
- **Backfill everything after the install.** One command that brings in the whole history and distills it in batches,
  instead of the newest 40 by default.
- **Learning at the end of a session.** Have the session-end hook start the learning step, so it does not depend on the
  agent calling a tool (in real sessions it almost never does).
- **Lookup across languages.** A question in one language finding pages written in another.
- **An optional local semantic layer.** Local embeddings were measured and not shipped
  ([`DENSE-OPTIN.md`](docs/DENSE-OPTIN.md)); the question is whether one can be added without losing the refusals.
- **PyPI and npm.** Publish the Python package (with the LangGraph store) and the JavaScript client.
- **Windows, by hand.** Run the install and the apps on a real Windows machine; so far the tests run there in CI only.

## Done

- **The knowledge base as a named layer** (2.1.0, unreleased): `krouter kb add` declares a folder of reference
  material; the receipt lists it apart under `knowledge_base:`, it sets no confidence, and when only it matches the
  first line is `memory: none`; `krouter kb suggest` proposes folders, `krouter kb import` brings in PDF, Word and HTML
  ([`CHANGELOG.md`](CHANGELOG.md)).
