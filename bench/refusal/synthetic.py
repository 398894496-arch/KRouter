#!/usr/bin/env python3
"""Set 37's synthetic set: a mostly-Chinese memory with long English reference articles mixed in.

Written before any refusal rule was chosen (HELDOUT.md, set 37). The memory: 16 Chinese rule pages and 4 English ones.
Reference material: three English articles under `参考资料/` (with web-clipper style frontmatter: they count as the
knowledge base even when no folder is declared), and three under `01 项目/支付重构/调研/` written the way a saved article
usually is (a `Source:` line in the text, no frontmatter), which nothing recognises until the folder is declared.

Three configurations of the same files: `none` (no `krouter-kb.txt`), `ref` (`参考资料` declared), `all` (both folders
declared, as after following `krouter kb suggest`). Four kinds of question, Chinese and English: `memory` (a memory page
answers it), `kb` (only an article answers it), `near` (the memory holds something close, nothing answers it), `absent`
(nothing in the folder is about it). The scenario from the maintainer's vault is `near-en-01`.

    python3 bench/refusal/synthetic.py DIR      # lay the vaults out under DIR and print the item count
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

RULES_ZH = {
    "发版流程": "**发版前先跑全量测试，测试全绿后打 tag，由 CI 发布；不直接推 main。**",
    "数据库备份": "**数据库每天凌晨 3 点全量备份到对象存储，备份保留 30 天。** 每周日做一次恢复演练。",
    "代码评审": "**每个 PR 至少一人批准才能合并；改动超过 400 行要拆成几个 PR。**",
    "值班交接": "**值班每周一上午 10 点交接，交接单写在值班频道里。** 交接时说明未关闭的告警。",
    "日志保留": "**应用日志保留 14 天，审计日志保留 1 年。** 超期由定时任务清理。",
    "前端包管理": "**前端仓库统一用 pnpm，锁文件必须提交。** 不混用 npm 和 yarn。",
    "接口超时": "**支付接口超时设为 8 秒，失败重试 2 次，重试间隔 1 秒。**",
    "周报": "**每周五下午 5 点前在飞书发周报：本周完成、下周计划、风险。**",
    "报销审批": "**报销单 5000 元以下组长审批，5000 元以上要财务总监审批。**",
    "服务器配置": "**测试环境用 2 核 4G 的云主机；生产环境每台至少 8 核 16G。**",
    "错误上报": "**线上错误统一上报 Sentry，告警发到 alerts 频道。**",
    "分支命名": "**分支名用 feat/、fix/、chore/ 前缀，后面跟工单号。**",
    "依赖升级": "**每月第一个周二统一升级依赖；安全补丁随时升，不等月度窗口。**",
    "新人入职": "**新人第一周跟一位导师，一周内照文档配好开发环境。**",
    "口播导出": "**口播视频导出 1080p，码率 12Mbps，编码 H.264。**",
    "会议纪要": "**每次评审会后 24 小时内发会议纪要，写清结论和负责人。**",
}
RULES_EN = {
    "Billing service deploys": "**The billing service deploys only on Tuesdays and Thursdays, after the finance check "
                               "has passed.** Hotfixes need the on-call lead's approval.",
    "Database connection pool": "**Each service instance opens at most 50 database connections; PgBouncer runs in "
                                "transaction mode in front of Postgres.**",
    "Incident reviews": "**Every P1 incident gets a written, blameless review within 3 working days.**",
    "Public API rate limit": "**The public API allows 600 requests per minute per key, with bursts of up to 100.**",
}

ARTICLES_REF = {
    "Idempotency keys in payment APIs": (
        "https://example.org/blog/idempotency-keys",
        "Payment APIs are called over unreliable networks, so a client that times out cannot tell whether the charge "
        "went through. Idempotency keys solve this. The client generates a unique key for each logical operation and "
        "sends it with every retry of that operation. The server stores the key together with the response of the "
        "first request, and when the same key arrives again it returns the stored response instead of charging twice.\n\n"
        "How long should a server keep idempotency keys? Most providers keep them for 24 hours. That is long enough to "
        "cover automatic retries and a human retrying the next morning, and short enough that the table does not grow "
        "without bound. Keys should be scoped to the account that sent them, so two customers cannot collide.\n\n"
        "A key must be bound to the request body. If a client reuses a key with different parameters, the server "
        "should reject the request with a conflict error rather than silently returning the old response. Storing a "
        "hash of the request body next to the key makes that check cheap.\n\n"
        "Finally, idempotency is not only a server concern. Clients should generate keys before the first attempt, "
        "persist them across process restarts, and never derive them from timestamps alone."),
    "Postgres connection pooling explained": (
        "https://example.org/articles/postgres-pooling",
        "Every Postgres connection is a separate operating-system process with its own memory, which is why opening "
        "thousands of connections hurts. The default max_connections in Postgres is 100, and raising it far beyond "
        "a few hundred usually costs more in memory and contention than it gains.\n\n"
        "A connection pooler such as PgBouncer sits between the application and the database. In session pooling a "
        "client keeps one server connection for as long as it is connected; this is the most compatible mode and the "
        "least efficient. In transaction pooling a server connection is lent to a client only for the duration of one "
        "transaction, so a few dozen server connections can serve hundreds of clients. Statement pooling goes further "
        "and breaks multi-statement transactions, so it is rarely used.\n\n"
        "Transaction pooling has caveats: session-level features such as advisory locks held across transactions, "
        "SET commands and some prepared-statement setups do not behave as they would on a direct connection. Test "
        "them before switching modes."),
    "A short history of the Kubernetes scheduler": (
        "https://example.org/history/kube-scheduler",
        "The Kubernetes scheduler decides which node each new pod runs on. It watches for pods that have no node "
        "assigned, filters the nodes that cannot run the pod (not enough CPU or memory, taints the pod does not "
        "tolerate, affinity rules), scores the remaining nodes, and binds the pod to the best one.\n\n"
        "Pods that no node can take stay pending. The scheduler keeps them in a queue and retries when the cluster "
        "changes, for example when a node is added or another pod finishes. Preemption lets a high-priority pending "
        "pod evict lower-priority pods to make room.\n\n"
        "Early versions had a single hard-coded scoring function. The scheduling framework introduced plugin points "
        "(filter, score, reserve, bind) so that teams can add their own logic without forking the scheduler."),
}
ARTICLES_RESEARCH = {
    "What went wrong in a fintech billing outage": (
        "https://example.org/news/fintech-billing-outage",
        "A mid-sized fintech company lost its billing service for six hours last spring. According to the "
        "postmortem, the billing service database ran out of connections during a schema migration: the migration "
        "held long transactions open while the application kept opening new connections on every retry.\n\n"
        "Engineers first restarted the application servers, which made things worse, because every restart opened a "
        "fresh burst of connections. The service recovered only after the team paused the migration, rotated the "
        "production database credentials that had been copied into a debugging script, and brought the servers back "
        "one at a time.\n\n"
        "The postmortem lists three lessons: put a pooler in front of the database, cap retries with backoff, and "
        "keep credentials in a secrets manager instead of configuration files, where the review found the database "
        "password stored in plain text."),
    "Why teams move from npm to pnpm": (
        "https://example.org/blog/npm-to-pnpm",
        "pnpm stores every version of every package once, in a content-addressable store on the machine, and links "
        "it into each project's node_modules. Ten projects that use the same version of a library share one copy on "
        "disk, which is where most of the disk savings come from.\n\n"
        "pnpm's node_modules is also strict: a package can only import what it declares as a dependency. Projects "
        "that accidentally relied on a hoisted transitive dependency break when they switch, which is usually a bug "
        "worth finding.\n\n"
        "Installs are faster on a warm store because nothing has to be downloaded or copied again."),
    "Designing rate limits for public APIs": (
        "https://example.org/guides/api-rate-limits",
        "A token bucket rate limiter gives each client a bucket that refills at a fixed rate; each request takes a "
        "token, and requests that find the bucket empty are rejected. The bucket's size sets how large a burst can "
        "be, its refill rate sets the sustained rate.\n\n"
        "A leaky bucket smooths traffic instead: requests queue and leave at a constant rate. Fixed windows are the "
        "simplest to build but let a client send twice the limit across a window boundary; sliding windows fix that "
        "at the cost of more bookkeeping.\n\n"
        "Rejected requests should get HTTP 429 with a Retry-After header, so well-behaved clients know when to come "
        "back."),
}

QUESTIONS = [
    # memory: a page of the memory answers it
    ("memory-zh-01", "memory", "发版之前要做什么？", "02 经验与方法/发版流程.md"),
    ("memory-zh-02", "memory", "数据库多久备份一次，备份保留几天？", "02 经验与方法/数据库备份.md"),
    ("memory-zh-03", "memory", "一个 PR 至少要几个人批准才能合并？", "02 经验与方法/代码评审.md"),
    ("memory-zh-04", "memory", "值班什么时候交接？", "02 经验与方法/值班交接.md"),
    ("memory-zh-05", "memory", "审计日志保留多久？", "02 经验与方法/日志保留.md"),
    ("memory-zh-06", "memory", "前端仓库用什么包管理器？", "02 经验与方法/前端包管理.md"),
    ("memory-zh-07", "memory", "支付接口超时设多少秒？", "02 经验与方法/接口超时.md"),
    ("memory-zh-08", "memory", "报销超过 5000 元要谁审批？", "02 经验与方法/报销审批.md"),
    ("memory-zh-09", "memory", "生产环境的服务器至少要什么配置？", "02 经验与方法/服务器配置.md"),
    ("memory-zh-10", "memory", "分支名怎么起？", "02 经验与方法/分支命名.md"),
    ("memory-zh-11", "memory", "口播视频导出用多少码率？", "02 经验与方法/口播导出.md"),
    ("memory-en-01", "memory", "Which days can the billing service deploy?", "02 经验与方法/Billing service deploys.md"),
    ("memory-en-02", "memory", "How many database connections may each service instance open?",
     "02 经验与方法/Database connection pool.md"),
    ("memory-en-03", "memory", "How soon is a P1 incident review due?", "02 经验与方法/Incident reviews.md"),
    ("memory-en-04", "memory", "What is the rate limit on the public API?", "02 经验与方法/Public API rate limit.md"),
    # kb: only an article answers it
    ("kb-en-01", "kb", "How long should a server keep idempotency keys?", "参考资料/Idempotency keys in payment APIs.md"),
    ("kb-en-02", "kb", "What is the default max_connections in Postgres?",
     "参考资料/Postgres connection pooling explained.md"),
    ("kb-en-03", "kb", "What does the Kubernetes scheduler do with pending pods?",
     "参考资料/A short history of the Kubernetes scheduler.md"),
    ("kb-en-04", "kb", "How does a token bucket rate limiter work?",
     "01 项目/支付重构/调研/Designing rate limits for public APIs.md"),
    ("kb-en-05", "kb", "Why does pnpm save disk space?", "01 项目/支付重构/调研/Why teams move from npm to pnpm.md"),
    ("kb-en-06", "kb", "What went wrong in the fintech billing outage?",
     "01 项目/支付重构/调研/What went wrong in a fintech billing outage.md"),
    # near: the memory holds something close, nothing answers it
    ("near-en-01", "near", "What is the production database password of the billing service?", None),
    ("near-en-02", "near", "Which days can the search service deploy?", None),
    ("near-en-03", "near", "What is the rate limit on the internal admin API?", None),
    ("near-en-04", "near", "Who approves the review of a P2 incident?", None),
    ("near-en-05", "near", "How many connections does the billing database allow at peak traffic?", None),
    ("near-en-06", "near", "How often do we rotate the billing database credentials?", None),
    ("near-zh-01", "near", "数据库备份用的是哪家云厂商的对象存储？", None),
    ("near-zh-02", "near", "代码评审的评审人由谁指定？", None),
    ("near-zh-03", "near", "值班的加班费怎么算？", None),
    ("near-zh-04", "near", "搜索接口超时设多少秒？", None),
    ("near-zh-05", "near", "报销要不要附发票原件？", None),
    ("near-zh-06", "near", "后端仓库用什么包管理器？", None),
    # absent: nothing in the folder is about it
    ("absent-en-01", "absent", "What is the Wi-Fi password in the Berlin office?", None),
    ("absent-en-02", "absent", "How do we renew the TLS certificate of the marketing site?", None),
    ("absent-en-03", "absent", "Which GPU do we use for model training?", None),
    ("absent-en-04", "absent", "How much of a gym membership does the company reimburse?", None),
    ("absent-zh-01", "absent", "公司年会在哪里办？", None),
    ("absent-zh-02", "absent", "咖啡机怎么除垢？", None),
    ("absent-zh-03", "absent", "停车位怎么申请？", None),
    ("absent-zh-04", "absent", "团建的预算是多少？", None),
]
CONFIGS = {"none": [], "ref": ["参考资料"], "all": ["参考资料", "01 项目/支付重构/调研"]}
RESEARCH = "01 项目/支付重构/调研"


def lay_out(root: Path) -> None:
    """The files, once; `krouter-kb.txt` is written per configuration by `vault_for`."""
    if root.exists():
        shutil.rmtree(root)
    rules = root / "02 经验与方法"
    rules.mkdir(parents=True)
    for name, text in {**RULES_ZH, **RULES_EN}.items():
        (rules / f"{name}.md").write_text(f"---\nstatus: active\n---\n# {name}\n\n{text}\n", encoding="utf-8")
    ref = root / "参考资料"
    ref.mkdir()
    for title, (url, body) in ARTICLES_REF.items():
        (ref / f"{title}.md").write_text(f"---\ntitle: \"{title}\"\nsource: {url}\ntags: [clippings]\n---\n# {title}\n\n"
                                         f"{body}\n", encoding="utf-8")
    res = root / RESEARCH
    res.mkdir(parents=True)
    for title, (url, body) in ARTICLES_RESEARCH.items():
        (res / f"{title}.md").write_text(f"# {title}\n\nSource: {url}\n\n{body}\n", encoding="utf-8")
    (root / "01 项目/支付重构/项目说明.md").write_text(
        "# 支付重构\n\n**目标：把支付和账单拆成两个服务，账单服务单独发版。** 调研资料放在 调研/ 下。\n", encoding="utf-8")


def vault_for(base: Path, config: str) -> Path:
    v = base / config
    if not v.exists():
        shutil.copytree(base / "files", v)
    kb = v / "krouter-kb.txt"
    if CONFIGS[config]:
        kb.write_text("# set 37 synthetic\n" + "".join(f + "\n" for f in CONFIGS[config]), encoding="utf-8")
    elif kb.exists():
        kb.unlink()
    return v


def in_kb(rel: str, config: str) -> bool:
    """Where a gold page sits in a configuration: `参考资料` is a clipping folder by its frontmatter in every one."""
    return rel.startswith("参考资料/") or (config == "all" and rel.startswith(RESEARCH + "/"))


def items(base: Path) -> list[dict]:
    """Every question in every configuration: {id, q, vault, answerable, gold, kb_gold, kind, config}. `answerable`
    is from the memory's side: a `kb` question whose article is in the knowledge base must be refused by the memory
    (and its article listed under knowledge_base); with the article not in the knowledge base it is part of the memory,
    so the memory should answer with it."""
    base = Path(base)
    if not (base / "files").exists():
        lay_out(base / "files")
    out = []
    for config in CONFIGS:
        v = vault_for(base, config)
        for qid, kind, q, gold in QUESTIONS:
            kb_side = kind == "kb" and in_kb(gold, config)
            out.append({"id": f"{config}:{qid}", "q": q, "vault": str(v), "kind": kind, "config": config,
                        "answerable": kind == "memory" or (kind == "kb" and not kb_side),
                        "gold": [gold] if gold and not kb_side else [], "kb_gold": [gold] if kb_side else []})
    return out


if __name__ == "__main__":
    rows = items(Path(sys.argv[1]))
    print(json.dumps({"items": len(rows), "configs": list(CONFIGS)}))
