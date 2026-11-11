"""A sample memory with a bit of everything, for `krouter view --demo`, the screenshot in the README and the tests.

`build()` copies the bundled template into a throwaway folder (English layout for `en`) and adds what the viewer shows:
a page that replaced another, two pages that say different things about one subject, pages that link each other and
share a session, an alias lock, three experience cards with their use records, a correction made the way the agent
makes one (`corrections.apply_now`), the change ledger of two nightly runs, the learned triggers, the nightly report
(written three times and committed, so there is a history). Everything is made up. `build_big()` writes a memory of
any size from a small vocabulary, to see how the viewer behaves on tens of thousands of pages.

Needs `KROUTER_STATE_DIR` set (the co-citation weights go there) when it should not touch the real one; `view --demo`
and the tests set it.
"""

from __future__ import annotations

import json
import random
import shutil
import subprocess
import sys
from pathlib import Path

from . import router_dir

ZH = {
    "deploy": "部署清单", "rollback": "回滚方案", "qa": "测试周一跑", "db1": "数据库选型", "db2": "数据库选型（复议）",
    "retry": "计费服务重试", "standup": "站会时间", "topic": "主题｜发版",
    "sess1": "2026-11-03｜计费重试会话", "sess2": "2026-11-03｜回滚演练会话",
}


def _put(vault: Path, rel: str, fm: dict, body: str) -> Path:
    import zones

    path = zones.path(vault, rel)
    path.parent.mkdir(parents=True, exist_ok=True)
    head = "".join(f"{k}: {v}\n" for k, v in fm.items())
    path.write_text(f"---\n{head}---\n\n{body.strip()}\n", encoding="utf-8")
    return path


def build(root: Path, lang: str = "en", git: bool = True) -> Path:
    """The sample memory under `root/vault`; returns its path."""
    from . import demo

    sys.path.insert(0, str(router_dir()))
    import capture_ledger
    import corrections
    import experience
    import nightly
    import zones
    import associate

    lang = "zh" if lang == "zh" else "en"
    vault = demo.build(root, lang)  # the template, plus Monday's decision and Wednesday's change of mind
    en = lang == "en"
    names = ({"deploy": "Deploy checklist", "rollback": "Rollback plan", "qa": "QA runs on Mondays",
              "db1": "Database choice", "db2": "Database choice, revisited", "retry": "Billing service retries",
              "standup": "Standup time", "topic": "Topic releases",
              "sess1": "2026-11-03｜Billing retries session", "sess2": "2026-11-03｜Rollback drill session"}
             if en else ZH)
    release_old, release_new = ("Release day", "Release day, changed") if en else ("发版日", "发版日（改）")
    M = "02 经验与方法/"
    J = "05 时间日志/会话摘录/"
    if en:
        _put(vault, M + names["deploy"] + ".md",
             {"title": names["deploy"], "status": "active", "date": "2026-10-20"},
             f"# {names['deploy']}\n\nBefore a deploy to production: run the test suite, check the migration plan, tell the "
             f"channel. Releases follow [[{release_new}]]. If anything looks wrong, use the [[{names['rollback']}]].")
        _put(vault, M + names["rollback"] + ".md",
             {"title": names["rollback"], "status": "active", "date": "2026-10-22"},
             f"# {names['rollback']}\n\nTo roll back, redeploy the previous tag and restore the last database snapshot. "
             "Whoever deployed does the rollback.")
        _put(vault, M + names["qa"] + ".md", {"title": names["qa"], "status": "active", "date": "2026-11-01"},
             f"# {names['qa']}\n\nQA finishes its full pass on Monday, which is why releases wait for Tuesday. See "
             f"[[{release_new}]].")
        _put(vault, M + names["db1"] + ".md", {"title": names["db1"], "status": "active", "date": "2026-03-01"},
             f"# {names['db1']}\n\nThe billing service keeps its data in PostgreSQL. One managed instance, nightly backups.")
        _put(vault, M + names["db2"] + ".md", {"title": names["db2"], "status": "active", "date": "2026-10-05"},
             f"# {names['db2']}\n\nWe switched from PostgreSQL to SQLite for the billing service database: one file, no "
             "server to run, the volume is small.")
        _put(vault, "01 项目/示例项目/" + names["retry"] + ".md",
             {"title": names["retry"], "status": "active", "date": "2026-11-03"},
             f"# {names['retry']}\n\nRetry a failed charge three times with a growing delay, then give up and mark the invoice "
             f"overdue. Discussed in [[{names['sess1']}]].")
        _put(vault, J + names["sess1"] + ".md",
             {"title": names["sess1"], "date": "2026-11-03", "session": "sess-billing-01", "status": "generated"},
             "# Billing retries session\n\nQuestion: how many times should a failed charge be retried?\n\nAnswer: three "
             "times, with a growing delay, then mark the invoice overdue.")
        _put(vault, J + names["sess2"] + ".md",
             {"title": names["sess2"], "date": "2026-11-03", "session": "sess-billing-01", "status": "generated"},
             "# Rollback drill session\n\nWe practised restoring the database snapshot after a bad billing migration.")
        _put(vault, "02 经验与方法/主题档案/" + names["topic"] + ".md",
             {"title": names["topic"], "status": "provisional", "date": "2026-11-06"},
             f"# {names['topic']}\n\nEverything about shipping: [[{release_new}]], the [[{names['deploy']}]], "
             f"[[{names['qa']}]].")
        _put(vault, M + names["standup"] + ".md", {"title": names["standup"], "status": "active", "date": "2026-09-01"},
             "# Standup time\n\nStandups are at 10:00 every day.")
        cards = [
            ("C01", "When a fix works on one machine but not another, compare the environments before the code.",
             "works on my machine; differs between machines"),
            ("C02", "When a test fails only on CI, rerun it locally with the CI's exact settings before guessing.",
             "fails on CI; passes locally"),
            ("C03", "When a dish tastes flat as a whole, add a little of the opposite.", "flat; no depth"),
        ]
        uses = [("C01", "offered", "2026-11-04T10:02:11", "reply carried the id"),
                ("C01", "adopted", "2026-11-04T10:02:11", "the next line said it worked"),
                ("C01", "again", "2026-11-07T09:30:00", "same lesson, another session"),
                ("C02", "offered", "2026-11-05T15:40:00", "reply carried the id"),
                ("C02", "offered", "2026-11-06T11:00:00", "reply carried the id")]
    else:
        _put(vault, M + names["deploy"] + ".md", {"title": names["deploy"], "status": "active", "date": "2026-10-20"},
             f"# {names['deploy']}\n\n发布到生产之前：先跑测试，核对迁移方案，再在群里说一声。发版时间见 [[{release_new}]]。"
             f"出了问题就按 [[{names['rollback']}]] 来。")
        _put(vault, M + names["rollback"] + ".md", {"title": names["rollback"], "status": "active", "date": "2026-10-22"},
             f"# {names['rollback']}\n\n回滚就是重新部署上一个标签，并恢复最近一次数据库快照。谁发的版谁回滚。")
        _put(vault, M + names["qa"] + ".md", {"title": names["qa"], "status": "active", "date": "2026-11-01"},
             f"# {names['qa']}\n\n测试周一才能跑完一整轮，所以发版要等到周二。见 [[{release_new}]]。")
        _put(vault, M + names["db1"] + ".md", {"title": names["db1"], "status": "active", "date": "2026-03-01"},
             f"# {names['db1']}\n\n计费服务的数据放在 PostgreSQL，一个托管实例，每晚备份。")
        _put(vault, M + names["db2"] + ".md", {"title": names["db2"], "status": "active", "date": "2026-10-05"},
             f"# {names['db2']}\n\n计费服务的数据库从 PostgreSQL 改成了 SQLite：一个文件，不用跑服务，数据量小。")
        _put(vault, "01 项目/示例项目/" + names["retry"] + ".md",
             {"title": names["retry"], "status": "active", "date": "2026-11-03"},
             f"# {names['retry']}\n\n扣款失败重试三次，间隔越来越长，之后放弃并把发票标为逾期。讨论见 [[{names['sess1']}]]。")
        _put(vault, J + names["sess1"] + ".md",
             {"title": names["sess1"], "date": "2026-11-03", "session": "sess-billing-01", "status": "generated"},
             "# 计费重试会话\n\n问：扣款失败该重试几次？\n\n答：三次，间隔越来越长，之后把发票标为逾期。")
        _put(vault, J + names["sess2"] + ".md",
             {"title": names["sess2"], "date": "2026-11-03", "session": "sess-billing-01", "status": "generated"},
             "# 回滚演练会话\n\n演练了计费迁移出错之后恢复数据库快照。")
        _put(vault, "02 经验与方法/主题档案/" + names["topic"] + ".md",
             {"title": names["topic"], "status": "provisional", "date": "2026-11-06"},
             f"# {names['topic']}\n\n发版相关的一切：[[{release_new}]]、[[{names['deploy']}]]、[[{names['qa']}]]。")
        _put(vault, M + names["standup"] + ".md", {"title": names["standup"], "status": "active", "date": "2026-09-01"},
             "# 站会时间\n\n每天上午 10:00 开站会。")
        cards = [
            ("C01", "两台机器上结果不一样时，先比环境，再看代码。", "我这儿没问题; 机器之间不一致"),
            ("C02", "测试只在 CI 上失败时，先用 CI 的原样设置在本地重跑，再猜原因。", "CI上失败; 本地通过"),
            ("C03", "整体发平、没有层次时，加一点点反差的东西。", "发平; 没有层次"),
        ]
        uses = [("C01", "offered", "2026-11-04T10:02:11", "回复里带了编号"),
                ("C01", "adopted", "2026-11-04T10:02:11", "下一句说「管用」"),
                ("C01", "again", "2026-11-07T09:30:00", "别的会话里又遇到"),
                ("C02", "offered", "2026-11-05T15:40:00", "回复里带了编号"),
                ("C02", "offered", "2026-11-06T11:00:00", "回复里带了编号")]
    # the alias lock: one alias for the deploy checklist
    table = zones.path(vault, "90 系统文件/canonical_sources.psv")
    alias = "deploy checklist;pre-deploy steps" if en else "部署清单;发布前检查"
    rel = zones.real(vault, M + names["deploy"] + ".md")
    row = f"Q90|{alias}|{rel}|{'Before a deploy: tests, migration plan, tell the channel' if en else '发布前：测试、迁移方案、通知'}\n"
    with table.open("a", encoding="utf-8") as fh:
        fh.write(row)
    # experience cards and their use records
    folder = zones.path(vault, experience.FOLDER)
    folder.mkdir(parents=True, exist_ok=True)
    for cid, lesson, when in cards:
        title = ("Lesson: " if en else "经验｜") + lesson.split(",")[0].split("，")[0][:50]
        text = (f"---\ntitle: \"{title}\"\ntype: experience-card\nstatus: provisional\ncard_id: {cid}\nwhen: {when}\n"
                f"source_ref: \"[[{zones.real(vault, J + names['sess1'])}]]\"\ndate: 2026-11-03\n---\n\n# {title}\n\n"
                + (f"- Situation: {when}\n- Action: see the lesson\n- Result: it worked\n- Lesson: {lesson}\n" if en else
                   f"- 处境：{when}\n- 做法：见通用说法\n- 结果：管用\n- 通用说法：{lesson}\n"))
        (folder / (cid + ".md")).write_text(text, encoding="utf-8")
    log = zones.path(vault, experience.USES)
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("w", encoding="utf-8") as fh:
        for card, kind, at, why in uses:
            fh.write(json.dumps({"at": at, "card": card, "kind": kind, "session": "sess-billing-01", "turn": at, "why": why},
                                ensure_ascii=False) + "\n")
    # a correction made the way the agent makes one, the old page replaced
    old = "Standups are at 10:00 every day." if en else "每天上午 10:00 开站会。"
    new = "Standups are at 9:30 every day." if en else "每天上午 9:30 开站会。"
    corrections.apply_now(vault, new, old, zones.real(vault, M + names["standup"] + ".md"), "sample")
    # co-citation: the checklist and the rollback plan are cited together
    associate.reinforce(vault, [zones.real(vault, M + names["deploy"] + ".md"),
                                zones.real(vault, M + names["rollback"] + ".md")], 3.0)
    # learned triggers
    learned = zones.path(vault, "90 系统文件/自动化/下意识触发词-自学习.psv")
    learned.parent.mkdir(parents=True, exist_ok=True)
    rr = lambda rel: zones.real(vault, rel)  # noqa: E731
    qs = ([rr("01 项目/示例项目/" + names["retry"] + ".md") + "|how many retries does billing get",
           rr(M + names["rollback"] + ".md") + "|how do we undo a bad migration"] if en else
          [rr("01 项目/示例项目/" + names["retry"] + ".md") + "|计费失败重试几次",
           rr(M + names["rollback"] + ".md") + "|迁移出错了怎么撤回"])
    learned.write_text("\n".join(qs) + "\n", encoding="utf-8")
    # the change ledger: two runs
    for rid, at, line in (("20261104T030000", "2026-11-04 03:00", "retries"), ("20261105T030000", "2026-11-05 03:00", "rollback")):
        page = zones.path(vault, J + names["sess1" if line == "retries" else "sess2"] + ".md")
        text = capture_ledger.section(
            vault, rid, [{"path": page, "agent": "claude", "session": "sess-billing-01-" + line,
                          "added": ["- decided: failed charges are retried three times"] if en else ["- 决定：失败的扣款重试三次"]}],
            [], [], f"import_sessions.py --undo {rid}", "", [(zones.path(vault, M + names["db1"] + ".md"), names["db2"])]
            if line == "rollback" else [])
        capture_ledger.append(vault, text.replace(text.split("\n", 1)[0], f"## {at} · run {rid}", 1))
    # the nightly report, three nights, each committed (a history to look at)
    if git and shutil.which("git"):
        _git(vault, "init", "-q")
        _git(vault, "add", "-A")
        _git(vault, "commit", "-qm", "sample memory")
    for day, state, results in (
            ("2026-11-06", "ok", [("import_sessions", "off", "会话导入没开（import_sessions.py --consent 开启）"),
                                   ("cocite", "ok", ""), ("checkup", "ok", "")]),
            ("2026-11-07", "skipped", [("import_sessions", "off", "会话导入没开（import_sessions.py --consent 开启）"),
                                        ("reconsolidate", "skipped", "no model lane: skipped"), ("cocite", "ok", "")]),
            ("2026-11-08", "ok", [("import_sessions", "off", "会话导入没开（import_sessions.py --consent 开启）"),
                                   ("reconsolidate", "ok", ""), ("answer_cards", "ok", ""), ("cocite", "ok", ""),
                                   ("backup", "off", "备份没开（backup.py init --dir <会同步到别处的文件夹> 开启）")])):
        rows = [{"step": s, "state": st, "reason": why, "seconds": 2, "model_calls": 0, "chars_sent": 0}
                for s, st, why in results]
        # the real writer, with the two lines that probe this machine's model lane / key file replaced by fixed text
        saved = (nightly.channel_lines, nightly.duplicate_lines)
        nightly.channel_lines = lambda _v: (["没有可用的模型通道（没有 API key，也没找到已登录的 agent 命令行），这些功能没开：问答卡、主题档案、夜间学习。"
                                             "召回、纠错捕获、经验摘要、agent 自己写卡和笔记照常。", ""]
                                            if state == "skipped" else [])
        nightly.duplicate_lines = lambda _v: []
        try:
            nightly.write_report(vault, rows, state, "none" if state == "skipped" else "cli claude", f"{day}T03:00:12")
        finally:
            nightly.channel_lines, nightly.duplicate_lines = saved
        if git and shutil.which("git"):
            _git(vault, "add", "-A")
            _git(vault, "commit", "-qm", f"KRouter nightly {day}")
    return vault


def _git(vault: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(vault), "-c", "user.name=sample", "-c", "user.email=sample@local", *args],
                   capture_output=True, stdin=subprocess.DEVNULL, timeout=60)


WORDS = ("billing invoice retry deploy release rollback database migration cache queue worker backup restore alert "
         "dashboard latency timeout schema index budget vendor contract meeting planning review hiring onboarding "
         "security audit token session cookie webhook payment refund ledger report export import sync mobile desktop "
         "search ranking recall memory page topic customer support ticket sprint roadmap metric funnel pricing quota").split()


def build_big(root: Path, pages: int = 10000, lang: str = "en", seed: int = 7) -> Path:
    """A memory of `pages` made-up pages (a few links, a few replaced pages, a few sessions), for timing."""
    rnd = random.Random(seed)
    vault = Path(root) / "vault-big"
    folders = ["02 Methods", "01 Projects", "05 Journal/Sessions", "03 Sources", "04 Done"]
    (vault).mkdir(parents=True, exist_ok=True)
    (vault / "krouter-zones.psv").write_text("@lang|en\n", encoding="utf-8")
    names = [f"{rnd.choice(WORDS)} {rnd.choice(WORDS)} {i}" for i in range(pages)]
    for i, name in enumerate(names):
        folder = vault / folders[i % len(folders)] / f"g{i // 500}"
        folder.mkdir(parents=True, exist_ok=True)
        body_words = " ".join(rnd.choice(WORDS) for _ in range(rnd.randint(40, 120)))
        links = " ".join(f"[[{names[rnd.randrange(pages)]}]]" for _ in range(rnd.randint(0, 3)))
        status = "superseded" if i % 97 == 0 else "active"
        fm = f"---\ntitle: {name}\nstatus: {status}\ndate: 2026-{1 + i % 12:02d}-{1 + i % 28:02d}\n"
        if i % 11 == 0:
            fm += f"session: s{i // 40}\n"
        (folder / f"{name}.md").write_text(f"{fm}---\n\n# {name}\n\n{body_words}\n\n{links}\n", encoding="utf-8")
    return vault


