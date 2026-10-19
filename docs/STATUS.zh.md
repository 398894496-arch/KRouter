> **`main` 的当前状态（最新发布版 v1.1.1，2026-10-15）：测过什么，没测过什么。** 一行安装拿到的是最新发布版；
> CHANGELOG.md 里「Unreleased」下的改动只在 `main` 上。给评估 agent 的全部事实和出处：
> [`docs/FOR-AGENTS.md`](https://github.com/398894496-arch/KRouter/blob/main/docs/FOR-AGENTS.md)。
> - **留出测评**（合成的 110 页库上 200 道从没调过分的题，*不是*真实流量）：KRouter 引错 27%，80 道库里答不了的题
>   拒答 46 道，120 道可答题答对 102 道。默认设置下 claude-mem 引错 64%、basic-memory 78%，分别答对 72 和 45 道；
>   两者都没有拒答机制。给 BM25 加上 KRouter 那两条规则（跳过已被取代的页、匹配太弱就拒答），它就和 KRouter 打平：
>   领先来自这两条规则默认开着，不是排序算法。
> - **新查询上的真实流量盲测**（[VERIFY.md](https://github.com/398894496-arch/KRouter/blob/main/docs/VERIFY.md) 第 4 层）：
>   还没跑，要等攒够 50 条新查询。
> - **留出题是谁写的：** claude.ai 里单独会话中的 Claude Opus，不是真人。真人写的一套在计划中。
> - **稳定线：** 1.1.x 到 2026-11-12 只修问题、不加功能，补丁每周最多一个。最小安装、零后台进程：
>   `bootstrap.py --vault <库> --no-timer --no-import`。
> - **夜间任务：** 一行安装只装查询，什么都不问；加 `--ask` 才问要不要导入会话、开夜间任务。从 clone 手动跑 `install.sh`
>   会直接装（`KROUTER_NO_TIMER=1` 跳过）。查询从不出本机。
> - **夜间写入通道：** API key 通道本机不跑任何进程；grok（内核沙箱）和 claude（工具白名单）只能动库；Codex 能读整个账号、
>   只写库，所以只有你点名或设 `KROUTER_ALLOW_CODEX=1` 才用；其他 CLI 没有约束，不设 `KROUTER_ALLOW_UNCONFINED=1` 就不会被选用。对照表见 [SECURITY.md](https://github.com/398894496-arch/KRouter/blob/main/SECURITY.md)。
