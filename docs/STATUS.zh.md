> **`main` 的当前状态（最新发布版 v1.3.0，2026-11-09）：测过什么，没测过什么。** 一行安装拿到的是最新发布版；
> CHANGELOG.md 里「Unreleased」下的改动只在 `main` 上。给评估 agent 的全部事实和出处：
> [`docs/FOR-AGENTS.md`](https://github.com/398894496-arch/KRouter/blob/main/docs/FOR-AGENTS.md)。
> - **留出测评**（合成的 110 页库上 200 道从没调过分的题，*不是*真实流量）：KRouter 引错 26%，80 道库里答不了的题
>   拒答 47 道，120 道可答题答对 102 道。默认设置下 claude-mem 引错 64%、basic-memory 78%，分别答对 72 和 45 道；
>   两者都没有拒答机制。给 BM25 加上 KRouter 那两条规则（跳过已被取代的页、匹配太弱就拒答），它就和 KRouter 打平：
>   领先来自这两条规则默认开着，不是排序算法。
> - **答案准确率**（LongMemEval S，也就是别家公布的那个数）：500 道答对 400 道，80.0% [76.4, 83.4]；只给 KRouter
>   引用的前三页，作答和评判都是 Claude Sonnet 5.5、用基准自带的提示词，不是多数项目用的 GPT-4o。最弱的是要把好几段
>   聊天加起来的题（121 道答对 69 道）。
> - **别人出的基准**（按出题方标注评分，不用模型当裁判）：LongMemEval S 470 道可答题里 439 道引到答案会话，30 道
>   无答案题拒了 3 道；LoCoMo 1 540 道里 991 道第一条就是证据，446 道陷阱题拒了 37 道。测的是找没找对页，不是答案
>   准确率；纯 BM25 找到的也差不多。
> - **新查询上的真实流量盲测**（[VERIFY.md](https://github.com/398894496-arch/KRouter/blob/main/docs/VERIFY.md) 第 4 层）：
>   还没跑，要等攒够 50 条新查询（到 2026-11-09 记下了 30 条）。
> - **留出题是谁写的：** claude.ai 里单独会话中的 Claude Opus，不是真人。真人写的一套在计划中。
> - **发版节奏：** 1.3.0（2026-11-09）：同意导入之后，记忆自己保持更新，不再逐条等你确认；每一轮都有记录、能撤回。
>   小版本每周最多一个，补丁随时发；`KROUTER_TAG` 可以固定版本。
> - **安装和自动记：** 一行安装什么都不问，把本机装了的应用都接上（Claude Code 连同插件、Codex、Cursor、Claude Desktop、
>   VS Code、Copilot CLI、Gemini CLI、Kiro、Zed），并在本机导入近 7 天的会话，不调模型；`--no-import` 只装查询。之后
>   Claude Code、Codex、Cursor 都通过会话钩子在每一轮结束时记下（只在本机、不调模型；Codex 要先在 `/hooks` 里信任；Cursor
>   的照它的文档检查过，还没在 Cursor 里实测）。用模型提炼和夜间任务会先问（`--ask`）。从 clone 手动跑 `install.sh` 会直接装夜间任务（`KROUTER_NO_TIMER=1` 跳过）。查询从不出本机。
> - **夜间写入通道：** API key 通道本机不跑任何进程；grok（内核沙箱）和 claude（工具白名单）只能动库；Codex 能读整个账号、
>   只写库，所以只有你点名或设 `KROUTER_ALLOW_CODEX=1` 才用；其他 CLI 没有约束，不设 `KROUTER_ALLOW_UNCONFINED=1` 就不会被选用。对照表见 [SECURITY.md](https://github.com/398894496-arch/KRouter/blob/main/SECURITY.md)。
