#!/usr/bin/env python3
"""Set 40's labelled vaults: your own pages and outside reference material mixed in the same folders.

Two vaults, written by this script from fixed text banks and a fixed seed: `zh` (a Chinese memory folder) and `en` (an
English one, `@lang|en`). Every page carries a label (`own` / `ext`), a kind, and a split (`dev` / `heldout`, by a
hash of its path), all in `labels.jsonl` next to the vaults; nothing about the label is written into the page.

Own pages: rules and decisions in project folders, meeting notes with decisions and to-dos, short personal notes,
English notes in the Chinese vault (and Chinese in the English one), and the hard cases — long essays you wrote
yourself, and excerpts you copied and annotated. Outside pages: plain-text articles with no frontmatter (some with a
source line, some with nothing), clippings with a source in the frontmatter, research excerpts, translations, minutes of
someone else's meeting or talk, a library's README copied in. KRouter's own folders (`05 时间日志`, `02 经验与方法`)
hold some own pages too; they are recognised by where they are, and counted.

    python3 bench/kb_auto/make.py DIR        # writes DIR/zh, DIR/en, DIR/labels.jsonl
"""

from __future__ import annotations

import hashlib
import json
import random
import shutil
import sys
from pathlib import Path

SEED = 20261111

ZH_TOPICS = ["支付重构", "数据平台", "视频生产", "客服机器人", "移动端", "搜索服务"]
EN_TOPICS = ["Billing", "Data platform", "Video pipeline", "Support bot", "Mobile app", "Search"]

ZH_RULE = [
    "以后发版前先跑全量测试，测试全绿再打 tag。", "数据库迁移统一用 alembic，不手写 SQL 改表。",
    "接口超时设为 8 秒，失败重试两次。", "日志保留 14 天，审计日志保留一年。", "前端统一用 pnpm，锁文件必须提交。",
    "评审会后 24 小时内发纪要，写清负责人。", "生产环境每台至少 8 核 16G。", "分支名用 feat/、fix/ 前缀加工单号。",
    "报销 5000 元以下组长审批。", "线上告警统一发到 alerts 频道。", "测试数据不能用真实用户手机号。",
    "周五下午不发版，紧急修复除外。",
]
EN_RULE = [
    "From now on we deploy only after the full test suite passes.", "Database migrations go through alembic; no hand-written ALTERs.",
    "API timeouts are 8 seconds with two retries.", "Application logs are kept 14 days, audit logs one year.",
    "The frontend uses pnpm and the lockfile must be committed.", "Minutes go out within 24 hours of every review.",
    "Production hosts get at least 8 cores and 16 GB.", "Branch names start with feat/ or fix/ and the ticket number.",
    "Never use real customer phone numbers in test data.", "No deploys on Friday afternoons except hotfixes.",
]
ZH_DIARY = [
    "今天把{t}的接口文档补完了，下午和小王对了一下字段。", "{t}这周进度慢，主要卡在权限审批上。",
    "想到一个点子：{t}的重试可以放到队列里做。", "跟老板聊了{t}的排期，他希望月底前能上线第一版。",
    "{t}的压测结果还行，峰值 1200 QPS，CPU 到 70%。", "记一下：{t}的测试账号密码在 1Password 里，不要写进文档。",
    "明天要找运维确认{t}的域名证书什么时候到期。", "{t}上线后第一周没有大问题，只有两个小 bug。",
]
EN_DIARY = [
    "Finished the {t} API docs today and went over the fields with Sam.", "{t} is slow this week, mostly stuck on access approvals.",
    "Idea: the {t} retries could go through the queue.", "Talked to my manager about the {t} schedule; first version by month end.",
    "{t} load test looks fine: 1200 QPS peak, CPU at 70%.", "Note to self: the {t} test account lives in 1Password, never in docs.",
    "Need to ask ops tomorrow when the {t} certificate expires.", "First week after the {t} launch: no big problems, two small bugs.",
]
ZH_ESSAY = [
    "我做{t}这两年，最大的体会是先把边界想清楚。很多时候我们急着写代码，结果写到一半才发现需求本身是含糊的，"
    "回头再改的代价比一开始多花一天想清楚大得多。我现在的习惯是先写一页纸，把输入、输出、出错时怎么办写下来，再动手。",
    "回想{t}第一次上线那周，我几乎每天都在半夜被告警叫醒。那时候我以为是监控太敏感，后来才明白是我们的重试策略有问题："
    "一个下游抖一下，上游就成倍地重试，把下游彻底压垮。这件事让我对“稳”这个字有了新的理解。",
    "我一直觉得{t}团队最宝贵的不是技术，而是大家愿意把问题说出来。复盘的时候没有人互相指责，"
    "每个人都只说自己那一环当时看到了什么、做了什么判断。这种氛围是我花了很久才慢慢建立起来的。",
    "写这篇是想给自己留个记录。{t}从立项到现在，我换了三次方案，每一次推翻都很痛苦，但事后看每一次都是对的。"
    "我学到的是：方案不怕推翻，怕的是明知道不对还硬撑着。",
]
EN_ESSAY = [
    "Two years into {t}, the biggest lesson I keep coming back to is to get the boundaries straight first. Too often I "
    "rushed into code and found halfway through that the requirement itself was vague, and going back cost far more than "
    "a day of thinking would have. These days I write one page first: inputs, outputs, what happens on failure.",
    "Looking back at the week {t} first went live, I was woken by alerts almost every night. I thought the monitoring was "
    "too sensitive; it took me a while to see that our retry policy was the problem. One wobble downstream and upstream "
    "retried many times over, flattening the service it depended on.",
    "I have always felt that what the {t} team has that matters most is not technology but that people say what is "
    "wrong. In our reviews nobody blames anybody; everyone says what they saw at their step and what they decided.",
    "I am writing this to keep a record for myself. Since {t} started I changed the design three times. Every reversal "
    "hurt, and every one was right in hindsight. What I learned: a design can be thrown away; holding on to one you "
    "know is wrong is the real mistake.",
]
EN_ARTICLE = [
    "Payment systems are called over unreliable networks, so a client that times out cannot tell whether a charge went "
    "through. Idempotency keys address this: the client generates a key per logical operation and sends it with every "
    "retry, and the server returns the stored response when the same key arrives again.",
    "Feature flags let teams ship code that is switched off, then turn it on for a small share of users. The practice "
    "has costs: every flag is a branch in the code, and flags that are never removed accumulate into a maze that nobody "
    "fully understands. Mature teams give each flag an owner and an expiry date.",
    "Observability is often described with three pillars: logs, metrics and traces. The framing is useful but "
    "incomplete. What matters is whether an engineer who was not involved can answer a new question about the system "
    "without shipping new code. That is a property of the whole toolchain, not of any single signal.",
    "The history of the relational database is a history of arguments about where complexity should live. Codd's model "
    "moved it out of application code and into a declarative language; decades later, document stores moved some of it "
    "back. Neither side won, and most large systems today use both.",
    "Large language models are trained on text and predict the next token. Retrieval augmented generation adds a search "
    "step: the system finds passages relevant to the question and puts them in the prompt. The quality of the answer "
    "then depends heavily on the quality of the retrieval, which is often the weakest link.",
    "Rate limiting protects a service from being overwhelmed. The token bucket algorithm is the most common choice: "
    "tokens are added at a fixed rate up to a maximum, and each request consumes one. Bursts are allowed up to the "
    "bucket size, while the long-run rate stays bounded.",
]
ZH_ARTICLE = [
    "在分布式系统中，幂等性是保证数据一致的重要手段。客户端为每一次逻辑操作生成唯一的请求号，服务端在收到重复请求时直接返回"
    "第一次的结果，而不是再执行一遍。这种做法在支付、下单等场景中被广泛采用，业内通常把请求号保留 24 小时。",
    "近年来，越来越多的企业开始关注可观测性建设。日志、指标和链路追踪常被称为可观测性的三大支柱，但业内专家指出，"
    "真正重要的是工程师能否在不改代码的前提下回答关于系统的新问题，这取决于整套工具链，而不是某一种数据。",
    "据业内人士介绍，短视频平台的推荐算法主要依据完播率、互动率和账号权重三类指标。新账号在冷启动阶段会被分配少量流量，"
    "表现好的内容再逐级放大。多位从业者表示，前三秒的留存决定了一条视频能否进入下一个流量池。",
    "大模型的训练成本在过去两年持续下降。研究机构的报告显示，同等能力的模型，训练所需的算力每年约降低一半。"
    "与此同时，推理成本成为企业部署时最关心的问题，量化、蒸馏和缓存等技术被广泛使用。",
    "限流是保护服务不被压垮的常见做法。令牌桶算法按固定速率往桶里放令牌，每个请求消耗一个令牌，桶满时多余的令牌被丢弃。"
    "这种算法允许一定程度的突发流量，同时保证长期速率不超过上限。",
]
ZH_TITLES = ["深度｜分布式系统中的幂等性设计与实践", "可观测性建设：从三大支柱到工具链", "揭秘短视频推荐算法：完播率为何如此重要？",
             "大模型训练成本持续下降，推理成为新战场", "一文读懂限流算法：令牌桶与漏桶的区别", "行业观察：企业数字化转型的五个误区",
             "专访｜一位架构师眼中的十年技术变迁", "为什么越来越多的团队放弃微服务？"]
EN_TITLES = ["Why Idempotency Keys Matter in Payment APIs", "Feature Flags: The Hidden Cost of Shipping Dark",
             "Observability Is Not Three Pillars", "A Short History of Arguing About Databases",
             "How Retrieval Augmented Generation Actually Works", "Rate Limiting with Token Buckets: A Practical Guide",
             "What Ten Years of Microservices Taught the Industry", "The Case Against Premature Abstraction"]


def split_of(rel: str) -> str:
    return "dev" if int(hashlib.sha1(f"{SEED}:{rel}".encode()).hexdigest(), 16) % 2 == 0 else "heldout"


def fm(**kv) -> str:
    return "---\n" + "".join(f"{k}: {v}\n" for k, v in kv.items()) + "---\n\n"


def pages_zh(rng: random.Random) -> list[tuple[str, str, str, str]]:
    out = []
    for i, t in enumerate(ZH_TOPICS):
        proj = f"01 项目/{t}"
        rules = rng.sample(ZH_RULE, 4)
        out.append((f"{proj}/{t}决定记录.md", f"# {t}决定记录\n\n" + "".join(f"- {r}\n" for r in rules), "own", "decision"))
        out.append((f"{proj}/{t}周会纪要.md", f"# {t}周会 第{i + 3}周\n\n参会：我、小王、阿杰\n\n结论：{rules[0]}\n\n"
                    f"待办：\n- [ ] 小王补{t}的接口文档\n- [ ] 我找运维确认证书\n", "own", "meeting"))
        notes = rng.sample(ZH_DIARY, 3)
        out.append((f"{proj}/随手记.md", "\n\n".join(n.format(t=t) for n in notes) + "\n", "own", "note"))
        if i % 2 == 0:
            out.append((f"{proj}/{t}复盘：我这两年学到的.md", f"# {t}复盘：我这两年学到的\n\n" +
                        "\n\n".join(e.format(t=t) for e in rng.sample(ZH_ESSAY, 4)) * 2 + "\n", "own", "essay"))
        else:
            out.append((f"03 笔记/{t}的一点感想.md", "\n\n".join(e.format(t=t) for e in rng.sample(ZH_ESSAY, 3)) * 2 + "\n",
                        "own", "essay"))
        art = rng.sample(ZH_ARTICLE, 3)
        title = ZH_TITLES[i % len(ZH_TITLES)]
        out.append((f"{proj}/调研/{title}.md", f"# {title}\n\n" + "\n\n".join(art * 2) + "\n", "ext", "article-bare"))
        out.append((f"{proj}/调研/{EN_TITLES[i]}.md", "\n\n".join(rng.sample(EN_ARTICLE, 4)) * 2 + "\n", "ext",
                    "article-foreign"))
        out.append((f"{proj}/参考-{i}.md", f"来源：https://news.example.com/{i}\n\n" + "\n\n".join(rng.sample(ZH_ARTICLE, 2)) + "\n",
                    "ext", "article-source"))
        excerpt = rng.choice(ZH_ARTICLE)
        out.append((f"{proj}/摘抄与批注-{i}.md", f"> {excerpt}\n\n我的批注：这段对{t}有用，我们的重试也该带请求号，"
                    f"下周跟小王说一下。\n", "own", "annotated"))
        out.append((f"03 笔记/translation-{i}.md", f"# {EN_TITLES[(i + 3) % 8]}（译文）\n\n原文：https://blog.example.org/p/{i}\n"
                    f"译者：某某\n\n" + "\n\n".join(rng.sample(ZH_ARTICLE, 3)) + "\n", "ext", "translation"))
        out.append((f"04 资料/{t}-行业会议纪要.md", f"# 2026 {t}技术大会分论坛纪要\n\n整理：大会组委会\n\n" +
                    "\n\n".join(rng.sample(ZH_ARTICLE, 3)) + "\n\n本文版权归大会主办方所有。\n", "ext", "minutes-other"))
        out.append((f"04 资料/clip-{i}.md", fm(title=f'"{EN_TITLES[(i + 1) % 8]}"', source=f"https://example.net/a/{i}",
                                               tags="[clippings]") + "\n\n".join(rng.sample(EN_ARTICLE, 2)) + "\n",
                    "ext", "clipping"))
        out.append((f"03 笔记/english note {i}.md", rng.choice(EN_DIARY).format(t=EN_TOPICS[i]) + "\n" +
                    rng.choice(EN_DIARY).format(t=EN_TOPICS[i]) + "\n", "own", "note-foreign"))
        out.append((f"05 时间日志/会话摘录/2026-11-0{i + 1} 会话.md", fm(type="session-excerpt", date=f"2026-11-0{i + 1}") +
                    f"- **问**：{t}的超时怎么定？\n  **答**：{rng.choice(ZH_RULE)}\n", "own", "session"))
        out.append((f"02 经验与方法/{t}规范.md", fm(status="active", how=rules[1]) + f"# {t}规范\n\n{rules[1]}\n", "own", "rule"))
    out.append(("04 资料/README-ratelimit.md", "# ratelimit\n\nA small library for token bucket rate limiting.\n\n## Install\n\n"
                "    pip install ratelimit\n\n## Usage\n\n" + EN_ARTICLE[5] + "\n\nLicensed under the MIT License.\n",
                "ext", "readme"))
    return out


def pages_en(rng: random.Random) -> list[tuple[str, str, str, str]]:
    out = []
    for i, t in enumerate(EN_TOPICS):
        proj = f"Projects/{t}"
        rules = rng.sample(EN_RULE, 4)
        out.append((f"{proj}/{t} decisions.md", f"# {t} decisions\n\n" + "".join(f"- {r}\n" for r in rules), "own", "decision"))
        out.append((f"{proj}/{t} weekly sync.md", f"# {t} weekly sync, week {i + 3}\n\nAttendees: me, Sam, Priya\n\n"
                    f"Decision: {rules[0]}\n\nAction items:\n- [ ] Sam writes the {t} API docs\n- [ ] I check the certificate\n",
                    "own", "meeting"))
        out.append((f"{proj}/scratch.md", "\n\n".join(d.format(t=t) for d in rng.sample(EN_DIARY, 3)) + "\n", "own", "note"))
        out.append((f"{proj}/What two years of {t} taught me.md", f"# What two years of {t} taught me\n\n" +
                    "\n\n".join(e.format(t=t) for e in rng.sample(EN_ESSAY, 4)) * 2 + "\n", "own", "essay"))
        title = EN_TITLES[i]
        out.append((f"{proj}/research/{title}.md", f"# {title}\n\n" + "\n\n".join(rng.sample(EN_ARTICLE, 3)) * 2 + "\n",
                    "ext", "article-bare"))
        out.append((f"{proj}/research/{ZH_TITLES[i]}.md", "\n\n".join(rng.sample(ZH_ARTICLE, 3)) * 2 + "\n", "ext",
                    "article-foreign"))
        out.append((f"{proj}/ref-{i}.md", f"Source: https://news.example.com/{i}\n\n" + "\n\n".join(rng.sample(EN_ARTICLE, 2))
                    + "\n", "ext", "article-source"))
        out.append((f"{proj}/excerpt with notes {i}.md", f"> {rng.choice(EN_ARTICLE)}\n\nMy take: this applies to {t}; our "
                    f"retries should carry a request key too. Raise it with Sam next week.\n", "own", "annotated"))
        out.append((f"Reading/{title} (summary of a talk).md", f"# Talk notes: {title}\n\nPosted by the conference team\n\n" +
                    "\n\n".join(rng.sample(EN_ARTICLE, 3)) + "\n\nAll rights reserved.\n", "ext", "minutes-other"))
        out.append((f"Reading/clip-{i}.md", fm(title=f'"{title}"', source=f"https://example.net/a/{i}") +
                    "\n\n".join(rng.sample(EN_ARTICLE, 2)) + "\n", "ext", "clipping"))
        out.append((f"Notes/{ZH_TOPICS[i]}笔记.md", rng.choice(ZH_DIARY).format(t=ZH_TOPICS[i]) + "\n" +
                    rng.choice(ZH_DIARY).format(t=ZH_TOPICS[i]) + "\n", "own", "note-foreign"))
    return out


def build(base: Path) -> list[dict]:
    base = Path(base)
    rng = random.Random(SEED)
    labels = []
    for name, pages in (("zh", pages_zh(rng)), ("en", pages_en(rng))):
        root = base / name
        if root.exists():
            shutil.rmtree(root)
        root.mkdir(parents=True)
        if name == "en":
            (root / "krouter-zones.psv").write_text("@lang|en\n", encoding="utf-8")
        for rel, text, label, kind in pages:
            p = root / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text, encoding="utf-8")
            labels.append({"vault": name, "rel": rel, "label": label, "kind": kind, "split": split_of(f"{name}/{rel}")})
    (base / "labels.jsonl").write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in labels), encoding="utf-8")
    return labels


if __name__ == "__main__":
    rows = build(Path(sys.argv[1]))
    from collections import Counter

    print(json.dumps({"pages": len(rows), "by": Counter(f"{r['split']}:{r['label']}" for r in rows)}, ensure_ascii=False))
