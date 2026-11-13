#!/usr/bin/env python3
"""Hot and cold: experience cards and the prompt hook's trigger phrases that have not been used for `hot_days` days
(60 by default) move behind the ones in use. Nothing is deleted, no page is changed, nothing waits for anyone's
approval, and a cold item still comes back when it is looked up by name.

What it applies to, and what counts as being used:

- **Experience cards** (`02 经验与方法/经验卡`): adopted, or seen again in another session (`experience.usage`:
  `last_adopted`, `last_again`, or `adopted_at` on the card). Being offered does not count. A card never used counts
  from its own `date`.
- **Trigger phrases of the prompt hook** (`90 系统文件/**/下意识触发词*.psv`: the generated ones and the ones the
  nightly step learned): the hook brought a page for that phrase (`recalled.jsonl` in the state folder). The lines
  carry no date, so a phrase counts from the first night the nightly step saw it (`first_seen` in the state folder);
  a phrase not seen by any night yet is never cold.

What it never applies to: your rule pages, correction pages, the alias table and its pages, and any page the lookup
finds. Knowledge is not weighed down for being old.

Cold cards sort after the others in the session-start digest (which has a line budget) and among suggestions; cold
trigger phrases sort after the others among the prompt hook's candidates (at most two pages a message), so they give
up the place first. Using an item makes it hot again at once: a card's next `adopted` / `again` record counts on the
next lookup, and a cold trigger phrase the hook does bring is taken off the cold list there and then.

`hot_days|60` in the memory folder's `krouter-settings.psv` sets the window, `hot_days|off` turns it off;
`KROUTER_HOT_DAYS` (a number or `off`) wins. "Today" is `KROUTER_TODAY` (YYYY-MM-DD) when set, so tests and benches do
not depend on the clock.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
from pathlib import Path

DEFAULT_DAYS = 60
SETTINGS_FILE = "krouter-settings.psv"


def days(vault: Path | None) -> int | None:
    """The window in days, or None when it is off."""
    raw = os.environ.get("KROUTER_HOT_DAYS", "").strip().lower()
    if not raw and vault is not None:
        try:
            text = (Path(vault) / SETTINGS_FILE).read_text(encoding="utf-8", errors="replace")
        except OSError:
            text = ""
        for line in text.splitlines():
            key, _, val = line.partition("|")
            if key.strip().lower() == "hot_days":
                raw = val.strip().lower()
    if not raw:
        return DEFAULT_DAYS
    if raw in ("off", "0", "no", "false"):
        return None
    try:
        return max(1, int(raw))
    except ValueError:
        return DEFAULT_DAYS


def today() -> dt.date:
    raw = os.environ.get("KROUTER_TODAY", "")[:10]
    try:
        return dt.date.fromisoformat(raw)
    except ValueError:
        return dt.date.today()


def _date(value: str) -> dt.date | None:
    try:
        return dt.date.fromisoformat(str(value or "")[:10])
    except ValueError:
        return None


def idle_days(last_active: str, since: str, now: dt.date | None = None) -> int | None:
    """Days since the item was last used (or, never used, since `since`); None when neither date is known."""
    d = _date(last_active) or _date(since)
    if d is None:
        return None
    return ((now or today()) - d).days


def cold(last_active: str, since: str, window: int | None, now: dt.date | None = None) -> bool:
    if window is None:
        return False
    n = idle_days(last_active, since, now)
    return n is not None and n >= window


# ---------- experience cards ----------

def card_active(card: dict, used: dict) -> str:
    u = used.get(card.get("id", ""), {})
    return max(u.get("last_adopted", ""), u.get("last_again", ""), card.get("adopted_at", ""))


def card_cold(card: dict, used: dict, window: int | None, now: dt.date | None = None) -> bool:
    return cold(card_active(card, used), card.get("date", ""), window, now)


# ---------- trigger phrases ----------

def state_dir() -> Path:
    return Path(os.environ.get("KROUTER_STATE_DIR") or Path.home() / ".local/state/krouter")


def _vault_key(vault: Path) -> str:
    return hashlib.sha1(str(Path(vault).resolve()).encode("utf-8")).hexdigest()[:12]


def ledger_path(vault: Path) -> Path:
    """first_seen per trigger phrase, and the cold list the prompt hook reads (one small JSON file)."""
    return state_dir() / f"hot-{_vault_key(vault)}.json"


def key(phrase: str, rel: str) -> str:
    return f"{phrase}|{rel}"


def load(vault: Path) -> dict:
    try:
        d = json.loads(ledger_path(vault).read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


_COLD: dict[str, tuple[float, frozenset]] = {}


def cold_triggers(vault: Path) -> frozenset:
    """The trigger phrases the last night found cold (keys `phrase|page`), as the prompt hook reads them: cheap, the
    file is read again only when it changed. Empty when the window is off."""
    if days(vault) is None:
        return frozenset()
    p = ledger_path(vault)
    try:
        m = p.stat().st_mtime
    except OSError:
        return frozenset()
    got = _COLD.get(str(p))
    if got and got[0] == m:
        return got[1]
    keys = frozenset(load(vault).get("cold") or [])
    _COLD[str(p)] = (m, keys)
    return keys


def warm_again(vault: Path, keys: list[str]) -> None:
    """The prompt hook brought these cold phrases: off the cold list at once (they were used today)."""
    if not keys:
        return
    d = load(vault)
    cold_now = [k for k in d.get("cold") or [] if k not in set(keys)]
    if len(cold_now) == len(d.get("cold") or []):
        return
    d["cold"] = cold_now
    d.setdefault("used", {}).update({k: today().isoformat() for k in keys})
    _write(vault, d)


def _write(vault: Path, d: dict) -> None:
    p = ledger_path(vault)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(p.name + f".{os.getpid()}.tmp")
        tmp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, p)
    except OSError:
        pass


def trigger_use(vault: Path) -> dict[str, str]:
    """{`phrase|page`: newest day the prompt hook brought that page for that phrase} from recalled.jsonl."""
    import recollect
    import zones

    out: dict[str, str] = {}
    for row in recollect._tail_lines(state_dir() / "recalled.jsonl"):
        if row.get("route") != "trigger" or not row.get("page"):
            continue
        k = key(recollect.norm(str(row.get("word") or "")), zones.canon(vault, str(row["page"])))
        out[k] = max(out.get(k, ""), str(row.get("ts") or "")[:10])
    return out


def nightly(vault: Path) -> dict:
    """The nightly pass: note first_seen for new trigger phrases, recompute the cold list of trigger phrases and of
    experience cards, and say what went cold and what came back since the last night.
    Returns {cards_cold, cards_new_cold, cards_restored, triggers_cold, triggers_new_cold, triggers_restored, window}
    (lists of ids / keys)."""
    import experience
    import recollect
    import zones

    window = days(vault)
    now = today()
    d = load(vault)
    first = d.setdefault("first_seen", {})
    used = d.setdefault("used", {})
    for k, day in trigger_use(vault).items():
        used[k] = max(used.get(k, ""), day)
    live = set()
    for row in recollect.entries(vault):
        if row[0] != "trigger":
            continue
        k = key(row[1], zones.canon(vault, row[3]))
        live.add(k)
        first.setdefault(k, now.isoformat())
    for k in list(first):
        if k not in live:
            first.pop(k)  # 触发词被删掉了：不再记
    t_cold = sorted(k for k in live if cold(used.get(k, ""), first.get(k, ""), window, now))
    cards = experience.load_cards(vault)
    use = experience.usage(vault)
    c_cold = sorted(c["id"] for c in cards if card_cold(c, use, window, now))
    before_t, before_c = set(d.get("cold") or []), set(d.get("cards_cold") or [])
    out = {"window": window, "cards_total": len(cards), "triggers_total": len(live),
           "cards_cold": c_cold, "cards_new_cold": [c for c in c_cold if c not in before_c],
           "cards_restored": sorted(c for c in before_c if c not in set(c_cold)),
           "triggers_cold": t_cold, "triggers_new_cold": [k for k in t_cold if k not in before_t],
           "triggers_restored": sorted(k for k in before_t if k not in set(t_cold))}
    d["cold"], d["cards_cold"], d["at"] = t_cold, c_cold, now.isoformat()
    _write(vault, d)
    return out


def report_lines(rep: dict) -> list[str]:
    """For the nightly report (Chinese, like the rest of it)."""
    if rep.get("window") is None:
        return ["冷热：关着（`krouter-settings.psv` 里 `hot_days|off`）。", ""]
    w = rep["window"]
    out = [f"冷热（{w} 天没被用到就排到同类后面，不删、不改页面；用到一次当场恢复；规则页、纠错页、别名表不受影响）："
           f"经验卡 {len(rep['cards_cold'])}/{rep['cards_total']} 张是冷的（本次新降 {len(rep['cards_new_cold'])}、"
           f"恢复 {len(rep['cards_restored'])}），钩子触发词 {len(rep['triggers_cold'])}/{rep['triggers_total']} 条是冷的"
           f"（本次新降 {len(rep['triggers_new_cold'])}、恢复 {len(rep['triggers_restored'])}）。", ""]
    out += [f"- 新降权的经验卡〔{c}〕" for c in rep["cards_new_cold"][:10]]
    out += [f"- 恢复的经验卡〔{c}〕" for c in rep["cards_restored"][:10]]
    out += [f"- 新降权的触发词 `{k.split('|', 1)[0]}` → [[{k.split('|', 1)[1].removesuffix('.md')}]]"
            for k in rep["triggers_new_cold"][:10]]
    out += [f"- 恢复的触发词 `{k.split('|', 1)[0]}` → [[{k.split('|', 1)[1].removesuffix('.md')}]]"
            for k in rep["triggers_restored"][:10]]
    return out + ([""] if len(out) > 2 else [])
