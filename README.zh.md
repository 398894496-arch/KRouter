# KRouter

**让你的 AI 记住你定过什么，也记住后来改成了什么。**

你现在用的 AI 就能接，有一个就够。记忆是一个纯 Markdown 文件夹，你能在 [Obsidian](https://obsidian.md) 或任何编辑器里打开、阅读、修改。问一句「封面标题我们是怎么定的」，答案会注明出自哪一页。纠错之后，新结论直接取代旧结论，不会两个一起冒出来。记忆里没有的，AI 会被明确告知「没有」，而不是拿一条差不多的凑数。写代码、写稿、做视频、学习、工作，凡是定过又会改的事都适用。

[![ci](https://github.com/398894496-arch/KRouter/actions/workflows/ci.yml/badge.svg)](https://github.com/398894496-arch/KRouter/actions/workflows/ci.yml) [![release](https://img.shields.io/github/v/release/398894496-arch/KRouter)](https://github.com/398894496-arch/KRouter/releases/latest) [![license](https://img.shields.io/badge/license-MIT-blue)](LICENSE) · English: [`README.md`](README.md)

每次提交都在 Linux、macOS、Windows 上跑测试。一行安装下载的是最新发布版（只用 tag，从不拉 `main`），运行任何东西之前先核对 SHA-256；每个发布版还带 GitHub 构建来源证明（`gh attestation verify <安装包> --repo 398894496-arch/KRouter`）。你问的问题从不离开本机。

![周一定了 A，周三改成 B，周四 agent 答 B 并引用那条纠错；库里没有的问题直接拒答](docs/img/demo.gif)

**不用安装、不用 key，几秒钟亲眼看一遍**：同样的过程，在一个用完即删的临时记忆库上跑。

```bash
uvx --from git+https://github.com/398894496-arch/KRouter krouter demo --lang zh      # 或者在 clone 里：PYTHONPATH=sdk python3 -m krouter.cli demo --lang zh
```

| 我想…… | 从这里开始 |
|---|---|
| 装之前先看它怎么答、怎么被纠正、怎么拒答 | `krouter demo`（上面这行） |
| 给我已经在用的 AI 应用接上记忆 | [安装](#安装)：一行，什么都不问，本机装了哪个应用就接哪个 |
| 看能接哪些应用 | [能接哪些应用](#能接哪些应用) |
| 从自己的代码里调用 | [从你自己的代码里用](#从你自己的代码里用) |
| 团队共用一份记忆，或者跑好几份 | [`docs/TEAM.md`](docs/TEAM.md) |
| 自己复现这些数字 | [自己复现](#自己复现) |
| 弄清楚什么会离开本机 | [什么会离开本机](#什么会离开本机) |

## 用数字说话

**别人出的基准**，按出题方自己的标注机械评分，不用模型当裁判：
- **LongMemEval**（ICLR 2025；500 道题，每道题配约 50 段聊天）：470 道能答的题里，439 道 KRouter 引用的页面里有答案所在的那段；72 道「事实后来变了」的题里，70 道引到了最新那次。
- **LoCoMo**（ACL 2024；10 段长对话，1 986 道题）：1 540 道能答的题里，991 道第一条引用就是证据所在的那段，1 204 道在前三条里。

这两项测的是「找没找对页」，不是「模型最后答没答对」，所以和别家公布的答案准确率不是一回事，不能直接比。纯 BM25 找到的页数也差不多（447/470、968/1 540）。

**弱点**：如果问的是记忆里某件事的「近邻」，它还是会作答。LongMemEval 里 30 道没有答案的题只拒了 3 道，LoCoMo 446 道陷阱题只拒了 37 道。

**我们自己的 200 道留出题**（中英文，从没拿来调过分，由 Claude Opus 在单独会话里出题）：KRouter 引错 26%，claude-mem 64%，basic-memory 78%。80 道记忆里答不了的题，KRouter 拒答 47 道，另外两个一道都不拒。60 道「决定后来改过」的题，KRouter 答对 50 道，它们是 34 和 16 道。这个差距有一部分是结构决定的：给纯全文检索加上 KRouter 那两条规则，它就和 KRouter 打平。KRouter 多出来的，是这两条规则默认就开着，外加出处回执和一个你能直接编辑的记忆库。[每个数字和测法](#老实的数字) · [自己复现](#自己复现)

## 安装

```bash
curl -fsSL https://github.com/398894496-arch/KRouter/releases/latest/download/bootstrap.sh | sh
```

这一行下载的小脚本，和它接着安装的包，都来自最新发布版（只用 tag，从不拉 `main`）；包在运行前先核对发布版里的 SHA-256，两者都带构建来源证明。

Windows（PowerShell）：`irm https://github.com/398894496-arch/KRouter/releases/latest/download/bootstrap.ps1 | iex` · Claude Code 插件：`/plugin install krouter --marketplace 398894496-arch/KRouter`（需要 Claude Code 2.1.275 或更高；在 shell 里用 `claude plugin install krouter --marketplace 398894496-arch/KRouter` 需要 2.1.292）。第三方插件市场不会自动更新：运行 `claude plugin update krouter@krouter`，或在 `/plugin` → Marketplaces → krouter 里选 Enable auto-update。

想先看看再装？下面只有最后一行会改动你的机器：

```bash
git clone https://github.com/398894496-arch/KRouter.git && cd KRouter
./scripts/first_run.sh                      # 在自带的示例库上出一张回执
python3 scripts/bootstrap.py --dry-run      # 列出安装会做的每一处改动，一处都不做
python3 scripts/bootstrap.py --vault ~/notes --no-timer   # 装到你自己的库，先不开夜间任务
```

唯一的前提是 Python 3，安装脚本什么都不问。它会建一个记忆文件夹（已有的用 `--vault` 指定，一个文件都不覆盖），把本机装了的、[下面这张表](#能接哪些应用)里的应用都接上，从同一个校验过的发布包装上 Claude Code 插件，再把近 7 天的 agent 会话导成页面：只在本机做、先脱敏、不调模型，每一页都记在变更记录里，可以撤回。从这以后它自己记：Claude Code、Codex、Cursor 每一轮结束就记下（安装时给它们接上会话钩子），没有任何内容离开本机。`--no-import` 只装查询；`--ask` 会先问你，要开「用你的模型提炼」和夜间任务也走它，这两步会把文字发出去。

## 能接哪些应用

一次安装，本机装了哪个就接哪个。每个应用都按它自己文档里的格式写进它的 MCP 设置，文件里原有的内容全部保留、另存一份备份；读不懂的文件、不是我们写的 `krouter` 条目一律不动；`uninstall.sh` 只删自己加的那一项。

| 应用 | 怎么接 | 状态 |
|---|---|---|
| Claude Code | 插件（会话钩子）和 MCP，安装脚本都会装上 | 已实测 |
| Codex | MCP，加上会话钩子（`~/.codex/hooks.json`；在 Codex 里输入 `/hooks` 信任一次，Codex 不跑没信任过的钩子） | MCP 已实测；钩子在 codex-cli 0.155 实测 |
| Cursor | 规则和 skill、MCP（`~/.cursor/mcp.json`），加上会话钩子（`~/.cursor/hooks.json`） | 规则和 skill 已实测；MCP 设置和钩子由测试照 Cursor 文档的格式检查，还没在 Cursor 里实测 |
| DeepSeek Harness | 插件（`dsh plugin --profile web add github:398894496-arch/KRouter`） | 已实测 |
| Claude Desktop · VS Code（Copilot）· GitHub Copilot CLI · Gemini CLI · Kiro · Zed | MCP：装了这个应用，安装脚本就写它的设置文件；重启一次应用 | 设置按各家文档的格式由测试检查过；还没在应用里实测 |
| 其他能跑本地 MCP 服务的应用：Windsurf、opencode、Cline、Continue…… | 把下面这段加进应用的 MCP 设置 | 应该能用，我们还没逐个实测：[告诉我们](https://github.com/398894496-arch/KRouter/issues) |
| 团队：好几个人共用记忆 | 自己部署的 HTTP 服务（`mcp_server.py --http`、Docker 镜像 `ghcr.io/398894496-arch/krouter`，或 [Compose](deploy/docker-compose.yml)）；一个服务可以挂好几个互不相通的库，各有各的 token；有 Prometheus `/metrics`：[`docs/TEAM.md`](docs/TEAM.md) | 已用 Claude Code 通过 HTTP 实测 |
| 只接受远程 MCP 服务的应用 | 同一个 HTTP 服务，前面加 HTTPS | 应该能用，我们还没实测 |
| 你自己的代码 | Python 包和 `krouter` 命令（见下） | 已实测 |

```json
{ "mcpServers": { "krouter": { "command": "python3",
    "args": ["/Users/you/.agents/skills/krouter-obsidian/scripts/mcp_server.py"] } } }
```

路径要写到你自己的用户目录（Windows 上是 `C:\\Users\\you\\.agents\\…`，命令常常是 `python` 而不是 `python3`）。一行安装之后，这个服务自己就能找到你的记忆库。它只用 Python 标准库，走 stdio，提供三个工具：`krouter_ask` 和 `krouter_status` 只读；`krouter_note` 让你的 AI 记下一行（一个决定、一处纠正、一个事实），写进当天的笔记页当线索，不会写进规则页，并在变更记录里记成一个可以撤销的 git 提交。HTTP 团队服务默认不开 `krouter_note`，启动时加 `--allow-write` 才开。用一个普通的 MCP 客户端连它，`initialize`、`tools/list`、带出处的回答、`recall: none` 都走得通。

### 从你自己的代码里用

Python 3.9+，同样的查询、收据和笔记：

```bash
pipx install "git+https://github.com/398894496-arch/KRouter"      # 或者：uvx --from git+https://github.com/398894496-arch/KRouter krouter ask "…"
krouter ask "我们怎么发版？"
```

```python
import krouter
a = krouter.ask("我们怎么发版？")
print(a.page, a.how, a.refused)          # 出处页、一句话答案、记忆里没有时为 True
krouter.note("只从 main 打发版标签。", kind="decision")
```

## 装完五分钟

1. 问你的 AI：*「上周我们关于 X 是怎么定的？」* 它会从记忆里查，给出答案和出处页；记忆里没有，就直说没有。
2. 打开记忆文件夹：近 7 天的 Claude Code、Codex、Cursor 会话已经在里面了，每个会话一页，内容是你的提问和每轮最后的回答，像 key 的文字已经脱敏，全程没出本机。（加 `--ask` 会先问你再导。）
3. **「要让模型提炼一下定了什么吗？」** 答应后，你已经在用的模型（登录好的 CLI 或 API key）会在最近几个会话的页面顶上写出「定了什么、改了什么」。发之前它会先告诉你要发多少字。

## 之后它自己跟上

什么都不用你维护，也不用你批；只有会把文字发给模型的那两步要先问你：
- **每天夜里**（这个任务会先问你）导入前一天的会话、做提炼、整理记忆库。
- **每一轮结束时**（Claude Code、Codex、Cursor 都是）：agent 一答完，这个会话到目前为止的内容就写进它那一页。只在本机做、不调模型，在后台不到一秒，别的窗口的 agent 马上就查得到。会话结束时再提炼一次（你同意过提炼的话）。
- **你纠正 AI 的时候**（同样是这三个）：读起来像纠正的话（「以后都……」「改成……」「from now on…」）在你发出的那一刻就记下来，只在本机做、不调模型，下一次提炼时自动判定成不成立。开新会话时，先带上这个仓库记下的决定，纠正排在前面，每条都带来源页。
- **白天**，可以再开一个定时任务，每天两个固定时间把当天的会话补进来（`extras/host-daily-evolution/intraday_capture.py`，附 macOS launchd 示例）。
- **不用你批，但每一步都看得见。** 每一轮加了什么、取代了什么，都写进 `90 系统文件/自动化/记忆变更记录.md`。记忆文件夹是 git 仓库时（运行一次 `git init` 就行），每一轮还是一个单独的提交，`import_sessions.py --undo <轮次>` 一条命令就能撤回。
- **某个会话不想被记**，在它的任何一个提问里写上 `#不记`（或 `#nocapture`）。

## 适不适合你

**适合**：你在用 AI 助手，哪一个都行，却总要把同一个决定反复交代，或者它总拿几周前已经改掉的说法来回答你。还没有笔记？安装脚本会帮你建好文件夹。同时用好几个 AI 是加分项，不是前提：它们会共用同一份记忆。**不适合**：你要基于向量的语义搜索、要把上一轮聊天自动塞进下一轮、要一个别人替你运营的托管记忆服务（自己部署团队服务器可以，见 [`docs/TEAM.md`](docs/TEAM.md)），或者希望装好就是一个装满的大脑。

**不只用于写代码**：同样的事放到短视频工作里，录法一样（Claude Code 加插件、演示库、真实输出）：

![周一定了封面标题规则 A，周三改成 B，周四 agent 答 B 并给出处页；库里没有的问题直接说没有](docs/img/demo-content.gif)

**不需要**：装 Obsidian（它只是可选的查看器）、维护别名表、
自己设环境变量。已经有库？`--vault` 一个文件都不改。默认什么都不往外发：只在本机导入会话，不装夜间任务，不调模型（`--no-import` 只装查询）。

## 和常见 agent 记忆的区别

| | KRouter | 常见的 agent 记忆 |
|---|---|---|
| 记忆放在哪 | 你能打开、编辑、比对、同步的 Markdown 页 | 数据库或向量库 |
| 纠错之后 | 新页取代旧页，旧页标成「已取代」 | 新旧两条都能匹配上，只能指望对的那条排前面 |
| 什么都对不上时 | 返回 `recall: none`，AI 会说记忆里没有 | 拿最接近的一条，说得很肯定 |
| 每条答案 | 带出处页和回执 | 通常没有出处 |
| 谁在用 | 本机每个 AI 应用都读同一个文件夹（MCP、skill、规则） | 通常只服务一个工具 |

**在用 [claude-mem](https://github.com/thedotmack/claude-mem)？** 不用卸掉。导入器已经在真实安装的 claude-mem 13.35.0 上完整跑通过。安装时会发现它的记忆库并问你要不要导入：会话总结变成页面，每个项目的决定汇成一页，等你确认。你的模型还能把这些决定理一遍，分出哪些还有效、哪些被后来的决定取代了，这一步是 claude-mem 自己不做的。Claude Code 插件也能做到 claude-mem 让人觉得「有记忆」的那两件事，只是存成纯 Markdown：会话结束时自动记下；开新会话时，自动带上这个仓库最近的决定，纠错排在前面，每条都注明出处页。仓库按路径区分，不按文件夹名。这两件事都要你先同意导入才会做。

## 什么会离开本机

查询从不外发：查找走本地的 SQLite 全文索引，每次约 110 ms。导入会话也只在本机做。只有你点过头的步骤才会把文字发给模型，就是提炼会话和夜间整理两步，发给你本来就在用的 CLI 或 API key，用 `--dry-run` 可以先看会发多少。key 和标成机密的页从不外发，也从不引用。夜间写入用 API key 通道时，本机不跑任何写入进程；用 CLI 通道时，
各家 CLI 能读到的范围不同，安装时会告诉你选的是哪一条。细节见 [`SECURITY.md`](SECURITY.md)。

**备份。** 运行 `backup.py init --dir <一个会同步到别处的文件夹>`，就会每晚给整个库（连同历史）做一个加密备份包，并且当晚重新打开验证过才算数。可以指向 iCloud 云盘、OneDrive、Dropbox、网盘同步文件夹或移动硬盘，也可以同时指两个；KRouter 不连任何云。为什么这样做，而不是直接同步或推送整个库：[`DETAILS.zh.md` → 备份你的库](docs/DETAILS.zh.md#备份你的库)。

## 老实的数字

| 测了什么 | 结果 |
|---|---|
| LongMemEval S，别人出的题和标注（[第 7 套](bench/memory_honesty/HELDOUT.md#set-7-longmemeval-someone-elses-questions-and-labels-registered-2026-10-18-before-any-download-or-run)；KRouter 1.1.1；按出题方标注机械评分，跑之前先登记方案） | 470 道可答题里 439 道引到答案所在的会话；72 道「知识更新」题里 70 道引到最新那次（只引到旧的：1 道）；470 道可答题拒了 12 道；**30 道无答案的题只拒了 3 道**。纯 BM25 不设下限、取前三页：447/470 和 69/72，持平 |
| LoCoMo，别人的对话和标注（[第 10 套](docs/DENSE-OPTIN.md#locomo-set-10-someone-elses-conversations-and-labels)；KRouter `main`，2026-10-30；只有英文） | 1 540 道可答题里 991 道第一条就引到证据会话，1 204 道在前三条里；**446 道陷阱题只拒了 37 道**。纯 BM25：第一条命中 968 道，前三条 1 257 道 |
| 该拒答时拒答（公开测试集，CI 跑） | 离题问题英文 12/12、中文 6/6 拒答 |
| 在一个没人调过分的库上的错误引用率（[第三套测试集](docs/BENCHMARK.md#third-bench-200-held-out-questions-on-a-vault-nobody-tunes-on-2026-10-13)，200 道留出题，中英各半，带日志干扰页；方括号是 95% 区间） | 默认设置下：KRouter 引错 26% [19, 33]，80 道近邻题拒答 47 道，120 道可答题答对 102 道；纯全文检索引错 58% [52, 65]。**和认真做的基线比是持平，不是领先**：给纯全文检索加上同样的两条规则（跳过已被取代的旧页、低于分数下限就拒答），答题数相同时它引错 42 页、KRouter 36 页，答对 96 道对 102 道，但两项差距都不显著（配对区间：引错率 [-10.2, +1.3] 个百分点，答对 [-2, +14]）。同样这 200 道题、都用默认设置：claude-mem 13.39 引错 64% [58, 71]，basic-memory 0.23 引错 78% [72, 84]；80 道近邻题两者一道都没拒；60 道「决定改过」的题，它们分别答对 34 和 16 道，KRouter 50 道 |
| 规模（[`BENCHMARK.md` → Scale](docs/BENCHMARK.md#scale-how-big-a-vault-can-get-2026-11-09)；合成库，Apple M2 笔记本，每次查询一个进程） | 1 千页：每次查询 0.08 秒（中位数），第一次查询含建索引 0.4 秒。1 万页：0.12 秒、4.8 秒。5 万页：0.53 秒（p95 1.1 秒）、24 秒，内存峰值 76 MB。HTTP 上 16 个人同时问 1 万页的库：没有出错，中位数 0.96 秒 |
| 精确命中和向量检索比（「已取代」和「近邻」题，CI 跑） | 精确命中会拒答；TF-IDF、MiniLM、BGE-M3 会引一个近邻。本地向量做成可选档：测过了，没有上线（[`DENSE-OPTIN.md`](docs/DENSE-OPTIN.md)） |
| 作者自己的真实提问 | 208 道历史提问由 Grok 盲评（2026-10-16）：KRouter 0.36，加了两条规则的 BM25 0.25（满分 2），配对区间 [−0.02, +0.24]：**没有显示出差距**。裁判只在约 5% 的题里找到「提问之前就已经存在的答案页」，这种评分方式会奖励拒答，所以这次结果只报告、不当证据（[第 5 套](bench/memory_honesty/HELDOUT.md)）。新提问上的盲测要等攒够 50 条，到 2026-11-09 记下了 30 条。更早的 0.62 → 1.47 是开发集（[VERIFY.md](docs/VERIFY.md)） |

### 自己复现

不用安装、不用模型，只要 Python 3；题目就在仓库里，留出题的数字大约一秒就能跑出来：

```bash
python3 bench/memory_honesty/run.py --set heldout3 --ci                        # KRouter，带 95% 区间
python3 bench/memory_honesty/run.py --set heldout3 --vs-matched bm25-floor    # 和加了同样两条规则的 BM25 比
```

别人出的基准要先下载它们的数据：数据不在仓库里，脚本也不会自己下载（每个脚本开头写了文件名、下载地址和许可）：

```bash
python3 bench/longmemeval/lme.py convert --data longmemeval_s_cleaned.json
python3 bench/longmemeval/lme.py run --system krouter && python3 bench/longmemeval/lme.py score
python3 bench/locomo/locomo.py convert --data locomo10.json
python3 bench/locomo/locomo.py run --system krouter && python3 bench/locomo/locomo.py score
```

方法和还没做好的地方：[`docs/VERIFY.md`](docs/VERIFY.md)。

## 更多

- [工作原理和全部选项](docs/DETAILS.zh.md)：安装参数、夜间写手、精确命中和排序召回、问答卡、四种 agent 接入
- [`docs/TEAM.md`](docs/TEAM.md)：团队共用一份记忆、自己部署的 HTTP 服务和它的 Docker 镜像
- [`SECURITY.md`](SECURITY.md)：每条模型通道能看到什么、能做什么
- [`docs/FOR-AGENTS.md`](docs/FOR-AGENTS.md)：给 agent 判断 KRouter 适不适合它的用户时参考的事实
- [`CHANGELOG.md`](CHANGELOG.md) · [`CONTRIBUTING.md`](CONTRIBUTING.md)：适合新人的 issue 都打了标签

**维护。** 目前只有一个维护者，这是采用它最大的风险，欢迎外部贡献。项目停了你还剩什么、没有作者时怎么继续：[`MAINTAINERS.md`](MAINTAINERS.md)。小版本每周最多一个，补丁随时发；`KROUTER_TAG=v1.3.0`（换成任何 tag）可以固定版本。哪些算稳定接口：[`DETAILS.md` → Stability and versions](docs/DETAILS.md#stability-and-versions)。问题和 bug 提 [issue](https://github.com/398894496-arch/KRouter/issues)；安全问题见 [`SECURITY.md`](SECURITY.md)。

*原名 DSH-KRouter，旧链接、旧 clone 地址和旧安装命令都会自动跳转。* MIT 协议。
