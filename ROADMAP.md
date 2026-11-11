# Roadmap

中文：[`ROADMAP.zh.md`](ROADMAP.zh.md) · back to the [README](README.md)

What is planned next, in no particular order and with no dates: nothing here is a promise, and an item is crossed out
only when it ships and its [`CHANGELOG.md`](CHANGELOG.md) entry says so. What does not work yet is listed in the README
under [What it does not do](README.md#what-it-does-not-do).

- **The knowledge base as a named layer.** Today any Markdown folder you point KRouter at is searched, and a folder can
  be treated as reference material only by its name or a tag. Planned: declare a folder as reference explicitly.
- **A better refusal rule.** A question about something near what the memory holds still gets an answer. The gate was
  analysed and no simple rule beat it ([`NUMBERS.md`](docs/NUMBERS.md), set 14); a different kind of signal is needed.
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
