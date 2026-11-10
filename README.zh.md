# KRouter

**让你的 AI 记住你定过什么，也记住后来改成了什么。**

你现在用的 AI 就能接，有一个就够。记忆是一个纯 Markdown 文件夹，你能在 [Obsidian](https://obsidian.md) 或任何编辑器里打开、阅读、修改。问一句「封面标题我们是怎么定的」，答案会注明出自哪一页。纠错之后，新结论直接取代旧结论，不会两个一起冒出来。记忆里没有的，AI 会被明确告知「没有」，而不是拿一条差不多的凑数。写代码、写稿、做视频、学习、工作，凡是定过又会改的事都适用。

[![ci](https://github.com/398894496-arch/KRouter/actions/workflows/ci.yml/badge.svg)](https://github.com/398894496-arch/KRouter/actions/workflows/ci.yml) [![release](https://img.shields.io/github/v/release/398894496-arch/KRouter)](https://github.com/398894496-arch/KRouter/releases/latest) [![license](https://img.shields.io/badge/license-MIT-blue)](LICENSE) · English: [`README.md`](README.md)

每次提交都在 Linux、macOS、Windows 上跑测试。一行安装下载的是最新发布版（只用 tag，从不拉 `main`），运行任何东西之前先核对 SHA-256；每个发布版还带 GitHub 构建来源证明（`gh attestation verify <安装包> --repo 398894496-arch/KRouter`）。你问的问题从不离开本机。

![周一定了 A，周三改成 B，周四 agent 答 B 并引用那条纠错；库里没有的问题直接拒答](docs/img/demo.gif)

开始用不需要 key：查询、出处、拒答都不调模型。没有模型时改主意不会被提炼，旧答案不会被自动替换（[没有模型时哪些能用](#安装)）。

**不用安装、不用 key，几秒钟亲眼看一遍**：同样的过程，在一个用完即删的临时记忆库上跑。

```bash
uvx --from git+https://github.com/398894496-arch/KRouter krouter demo --lang zh      # 或者在 clone 里：PYTHONPATH=sdk python3 -m krouter.cli demo --lang zh
```

| 我想…… | 从这里开始 |
|---|---|
| 装之前先看它怎么答、怎么被纠正、怎么拒答 | `krouter demo`（上面这行） |
| 给我已经在用的 AI 应用接上记忆 | [安装](#安装)：一行，什么都不问，本机装了哪个应用就接哪个（`--minimal`：只装查询、只接你点名的） |
| 看能接哪些应用 | [能接哪些应用](#能接哪些应用) |
| 从自己的代码里调用 | [从你自己的代码里用](#从你自己的代码里用) |
| 团队共用一份记忆，或者跑好几份 | [`docs/TEAM.md`](docs/TEAM.md) |
| 自己复现这些数字 | [自己复现](#自己复现) |
| 弄清楚什么会离开本机 | [什么会离开本机](#什么会离开本机) |

## 用数字说话

**每道题交 5 页，能不能把答案要的会话交齐。** 现在一次查询交 5 页：3 页是直接对上问题的，后面最多 2 页是记忆库里和它们连着的（链接、取代关系、同一段会话、共有的少见词、以前一起被引用过）。在 LongMemEval（ICLR 2025；500 道题，每道题配约 50 段聊天）上，按出题方自己的标注机械评分、不用模型，看调这些连接时没碰过的那一半 235 道题：**KRouter 交的 5 页把答案要的会话全部交齐的有 210 道，同样交 5 段的纯关键词检索（BM25）是 198 道**（多 12 道，配对 95% 区间 +3 到 +21）。答案分散在好几段聊天里的题：**47 道里 40 对 31**。这些是检索层的数字：交出去的页里有没有答案，不是模型据此答对了多少（[第 18 套](bench/memory_honesty/HELDOUT.md#set-18-does-following-the-vaults-own-connections-bring-the-whole-answer-registered-2026-11-10-before-the-associative-path-was-written-or-any-held-out-question-was-run)）。

**5 页版本的答题正确率没有重跑。** 带作答和评判模型的那一轮已经登记（[第 22 套](bench/memory_honesty/HELDOUT.md#set-22-the-same-reader-five-pages-each--keyword-search-against-krouter-with-its-associative-path-registered-2026-11-10-before-any-reader-or-judge-call)），没有跑。测过的答题正确率是上一个版本的，那时只交 3 页（KRouter 1.3.0：作答和评判都用 Claude Sonnet 5.5，500 道答对 400 道，和 BM25 交 3 段持平）；那张表连同版本和页数放在 [`docs/NUMBERS.zh.md`](docs/NUMBERS.zh.md#同一个作答模型只交-3-页krouter-130)。

**找没找对页**（更早的 3 页版本），同样机械评分。LongMemEval（KRouter 1.1.1）：470 道能答的题里，439 道 KRouter 引用的页面里有答案所在的那段（BM25 是 447 道）；72 道「事实后来变了」的题里，70 道引到了最新那次。LoCoMo（ACL 2024；10 段长对话，1 986 道题）：1 540 道能答的题里，991 道第一条引用就是证据所在的那段（BM25 是 968 道）。

**弱点**：如果问的是记忆里某件事的「近邻」，它还是会作答。LongMemEval 里 30 道没有答案的题只拒了 3 道，LoCoMo 446 道陷阱题只拒了 37 道。在 LoCoMo 那种短对话上，连着的那 2 页得不偿失：5 页把证据会话交齐的是 1 536 道里 1 185 道，5 页全给直接命中是 1 204 道。

**我们自己的 200 道留出题**（中英文，从没拿来调过分，由 Claude Opus 在单独会话里出题）：KRouter 引错 26%，claude-mem 64%，basic-memory 78%。80 道记忆里答不了的题，KRouter 拒答 47 道，另外两个一道都不拒。60 道「决定后来改过」的题，KRouter 答对 50 道，它们是 34 和 16 道。这个差距有一部分是结构决定的：给纯全文检索加上 KRouter 那两条规则（跳过已被取代的旧页、匹配太弱就拒答），它就和 KRouter 打平。

**所以 KRouter 多出来的**，是顺着记忆库自己的连接去找（上面那个领先，交 5 页时；只看引用的第一页，它和加了两条规则的纯检索持平），这两条规则默认就开着，每条答案带一张回执（出自哪一页、为什么是这页、有多大把握），还有一个你能直接打开、编辑的记忆库。[每个数字和测法](#老实的数字) · [自己复现](#自己复现) · [这页用到的词](#这页用到的词)

## 安装

```bash
curl -fsSL https://github.com/398894496-arch/KRouter/releases/latest/download/bootstrap.sh -o /tmp/krouter-install.sh && sh /tmp/krouter-install.sh
```

先把脚本存成文件再运行：下载失败就停在这一步，退出码非零（`curl … | sh` 会拿空脚本跑一遍，还报成功）。Windows（PowerShell）：`irm https://github.com/398894496-arch/KRouter/releases/latest/download/bootstrap.ps1 | iex`
· 只装 Claude Code 插件：`/plugin install krouter --marketplace 398894496-arch/KRouter`（[版本要求和更新办法](docs/DETAILS.zh.md#claude-code-插件)）。

唯一的前提是 Python 3；装了 ripgrep 只是让大库的原文搜索快一点。两种装法都什么都不问，选一种（参数跟在脚本后面：`sh /tmp/krouter-install.sh --minimal --apps claude`）：

| | 默认 | `--minimal`（最小安装） |
|---|---|---|
| 查询带出处、库里没有就直说 | 有 | 有 |
| 接哪些应用 | [下面这张表](#能接哪些应用)里本机装了的全部 | 只接你用 `--apps claude,codex,cursor,…` 点名的（不点名就一个都不接） |
| Claude Code 插件（会话钩子） | 找到 `claude` 就装 | 不装 |
| Codex、Cursor 的会话钩子 | 找到应用就加 | 不加 |
| Cursor 规则（`~/.cursor/rules/`） | 写 | 只在 `--apps cursor` 时写 |
| 记会话 | 从现在起：每一轮结束就记下，只在本机、先脱敏、不调模型 | 不记 |
| 导入以前的会话（近 7 天） | 不导：安装最后一行给出一条命令，想导再跑；或一开始就加 `--all` | 不导 |
| 夜间任务、用你的模型提炼（会把文字发出去的两步） | 不开：`--ask` 先问你，`--timer` 直接开夜间任务 | 不开 |
| 在 Obsidian 里打开新库 | 只在你从终端运行时打开（`--open` 总是打开，`--no-open` 从不）；agent 代跑时不打开 | 同左 |

`--all` 做安装在不调模型时能做的全部事，也就是以前的默认：另外导入近 7 天的会话，有 claude-mem 的话把它的记忆也导进来。

默认安装会建或改的全部文件（`--dry-run` 先按你这台机器列一遍，一处都不改；安装时会逐条列出改过的设置文件，改之前都先留了备份）：

| 位置 | 是什么 |
|---|---|
| `~/Documents/第二大脑/`（或你用 `--vault` 指定的文件夹） | 记忆本身，纯 Markdown。已有的文件夹一个文件都不覆盖，只补缺的 |
| `~/.dsh-krouter/<版本>/`、`~/.dsh-krouter/current` | 下载下来的发布包（从 clone 里装就用 clone 本身） |
| `~/.agents/skills/krouter-obsidian/` | 路由器 |
| `~/.config/krouter/vault` | 记着记忆在哪，给钩子和 MCP 服务用 |
| `~/.claude.json`（`claude mcp add`）、`~/.claude/settings.json`（插件和它的市场） | Claude Code |
| `~/.codex/config.toml`（`codex mcp add`）、`~/.codex/hooks.json` | Codex |
| `~/.cursor/mcp.json`、`~/.cursor/hooks.json`、`~/.cursor/rules/` | Cursor |
| [下面表里](#能接哪些应用)其他应用各自的 MCP 设置文件 | 只动本机装了的；改过的文件旁边留一份 `*.krouter-bak` |
| Claude Desktop 的 `claude_desktop_config.json` | 只在应用关着时写（用扩展包的话：点安装后应用会先联网检查几秒，界面没有反应；只点一次、等它好，再点一次可能会把它卸掉）；开着时一个字不改：给你一个 `~/.config/krouter/KRouter.mcpb` 去双击，或者退出应用后跑安装最后打印的那条 `--connect claude-desktop` 命令 |
| `~/.cache/krouter/`、`~/.local/state/krouter/` | 搜索缓存（可重建）和导入进度 |

安装过程中除了下载本身，没有任何内容离开本机。装完：

```bash
~/.dsh-krouter/current/scripts/krouter doctor     # 一句结论：正常，或缺什么、用哪条命令补
~/.dsh-krouter/current/scripts/krouter search "上周 X 最后定了什么？"
```

（在 clone 里用 `./scripts/krouter`；装了 Python 包、`krouter` 在 PATH 上，直接 `krouter`。）记忆文件夹就是纯 Markdown，用任何编辑器打开都行，喜欢的话也可以用 Obsidian。各个工具按这个顺序找它：`KROUTER_VAULT`，其次 `OBSIDIAN_VAULT`（旧名字，照样认；两个都设了以 `KROUTER_VAULT` 为准），最后是安装时记在 `~/.config/krouter/vault` 里的路径。

**没有模型时**（没登录任何 AI 编程工具、也没有 API key）：查询、带出处的回答、库里没有就直说、本地导入会话、记下读起来像纠正的话，都照常；不工作的是提炼（每页开头的「定了什么、改了什么」）、夜间整理和这些纠正的判定。后果：你改了主意，旧答案不会被自动替换，查询时旧页可能仍排第一，要等接上模型、那段会话提炼过之后才换。安装输出和 `krouter doctor` 都会说你现在是哪种状态。

想先看看再装？下面只有最后一行会改动你的机器：

```bash
git clone https://github.com/398894496-arch/KRouter.git && cd KRouter
./scripts/first_run.sh                      # 在示例库的临时副本上出一张回执
python3 scripts/bootstrap.py --dry-run      # 列出安装会改的每个文件和应用设置，一处都不改
python3 scripts/bootstrap.py --minimal --apps claude --vault ~/notes   # 只装查询、只接 Claude Code、用你的文件夹
```

**卸载：**

```bash
sh ~/.dsh-krouter/current/scripts/uninstall.sh     # 在 clone 里：sh scripts/uninstall.sh；加 --dry-run 先列出来
```

它会停掉并删除夜间任务、路由器、规则、KRouter 的 MCP 条目和钩子、Claude Code 插件（插件市场指向本机文件夹时一并删）和记下的库路径；你的记忆文件夹和钥匙文件一律不动。`--purge` 另外删缓存、状态和 `~/.dsh-krouter`。

## 能接哪些应用

一次安装，本机装了哪个就接哪个，每个应用都按它自己文档里的格式写进它的 MCP 设置。文件里原有的内容全部保留、另存一份备份；读不懂的文件、不是我们写的 `krouter` 条目一律不动；`uninstall.sh` 只删自己加的那一项。

| 应用 | 怎么接 | 状态 |
|---|---|---|
| Claude Code | 插件（会话钩子）和 MCP，安装脚本都会装上 | 已实测 |
| Codex | MCP，加上会话钩子（`~/.codex/hooks.json`；在 Codex 里输入 `/hooks` 信任一次） | MCP 已实测；钩子在 codex-cli 0.155 实测 |
| Cursor | 规则和 skill、MCP（`~/.cursor/mcp.json`），加上会话钩子（`~/.cursor/hooks.json`） | 规则和 skill 已实测；MCP 设置和钩子由测试照 Cursor 文档的格式检查，还没在 Cursor 里实测 |
| DeepSeek Harness | 插件（`dsh plugin --profile web add github:398894496-arch/KRouter`） | 已实测 |
| Claude Desktop | 扩展包：双击 [`KRouter.mcpb`](https://github.com/398894496-arch/KRouter/releases/latest/download/KRouter.mcpb)，点一次安装（不改设置文件、不用重启；点完应用会先联网检查几秒，这期间界面没有反应）。也可以让安装脚本写它的设置文件，但只在应用关着时写：Claude Desktop 开着的时候把设置留在内存里，退出时把整份文件写回去，开着时写进去的条目一重启就没了。安装脚本发现它在运行，就不碰那个文件，改为按你的记忆文件夹做一个扩展包 | **扩展包已在应用里实测**（Claude Desktop 4.23118.1，macOS，2026-11-10）：点一次安装、不用重启就装好，3 个工具都连上；在普通聊天里，一个问题答出结论并给出出处页，一个库里没有的问题被拒答（`recall: none`）。实测用的包写的是 Python 的完整路径（和安装脚本生成的一样）；发布附件里写的是 `python3`，应用会走另一条启动路径，还没实测。设置文件由测试检查过 |
| VS Code（Copilot）· GitHub Copilot CLI · Gemini CLI · Kiro · Zed · Cline CLI | MCP：安装脚本写好它的设置文件；重启一次应用 | 设置按各家文档的格式由测试检查过；还没在应用里实测 |
| 智能体框架：LlamaIndex、LangChain / LangGraph、OpenAI Agents SDK、Pydantic AI、Google ADK、CrewAI、Vercel AI SDK | 自带一个 LlamaIndex 检索器；其他框架用各自的 MCP 客户端：[`docs/FRAMEWORKS.zh.md`](docs/FRAMEWORKS.zh.md) | 都已对着服务实测，CI 也跑；其中三个连整个 agent 循环一起跑过 |
| 其他能跑本地 MCP 服务的应用（Windsurf、opencode、Continue、Roo Code……） | 把下面这段加进应用的 MCP 设置 | 应该能用，我们还没逐个实测：[告诉我们](https://github.com/398894496-arch/KRouter/issues) |
| 团队 | 自己部署的 HTTP 服务：见[给团队用](#给团队用) | 已用 Claude Code、官方 MCP Python SDK 和 JS 客户端通过 HTTP 实测 |
| 只接受远程 MCP 服务的应用 | 同一个 HTTP 服务，前面加 HTTPS | 应该能用，我们还没实测 |
| 你自己的代码 | Python 包和 `krouter` 命令；不依赖任何包的 JavaScript / TypeScript 客户端（见下） | 已实测 |

```json
{ "mcpServers": { "krouter": { "command": "python3",
    "args": ["/Users/you/.agents/skills/krouter-obsidian/scripts/mcp_server.py"] } } }
```

路径要写到你自己的用户目录（Windows 上是 `C:\\Users\\you\\.agents\\…`，命令常常是 `python`）。这个服务只用 Python 标准库，走 stdio，提供三个工具：`krouter_ask` 和 `krouter_status` 只读；`krouter_note` 让你的 AI 记下一行（一个决定、一处纠正、一个事实）。这一行写进当天的笔记页，只当线索，不会写进规则页；它是一次单独的 git 提交，可以撤回。

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

JavaScript / TypeScript（Node 18+），本机的或团队服务都行（[`sdk/js`](sdk/js)；还没发到 npm）：

```js
import { KRouter } from "./sdk/js/index.js";
const a = await KRouter.local().ask("我们怎么发版？");   // 团队服务：KRouter.remote(url, { token })
console.log(a.page, a.how, a.refused);
```

## 给团队用

一个服务装下一个团队的几份记忆，每份是一个放 Markdown 的文件夹、在各自的 git 仓库里；每个人的 agent 通过 MCP 问它。要自己部署，没有 KRouter 云服务。

| | |
|---|---|
| **部署** | `mcp_server.py --http`（只用 Python 标准库，不装包）、Docker 镜像 `ghcr.io/398894496-arch/krouter`、[Compose](deploy/docker-compose.yml)（两份记忆，加一个定时 git pull 的边车）、[Kubernetes 清单](deploy/kubernetes/krouter.yaml)、加固过的 [systemd 服务](deploy/systemd/krouter.service) |
| **隔离** | 一个服务挂好几份记忆，各在 `/mcp/NAME`，各有自己的索引、每条回答上的标签和 token；查一份记忆从不读另一份的文件夹 |
| **鉴权** | 每份记忆一个 bearer token；只要有一份没设 token，服务就拒绝监听本机以外的地址；浏览器来源按白名单放行；访问日志只记问题的哈希，不记原文 |
| **速度** | 见下面的实测；每份记忆常驻 4 个查询进程（`--workers`），查一次不用重新启动 Python |
| **新鲜度** | 最多每 2 秒重新检查一次文件（`--refresh-every`）；通过服务写进去的笔记，下一次查询就查得到；Compose 和 Kubernetes 每 5 分钟拉一次各个仓库 |
| **监控** | `GET /healthz`；Prometheus `GET /metrics`：按记忆、工具、结果分的调用数，拒答数，延迟直方图，启动时建索引的耗时，查询进程数 |
| **写入** | 默认只读；加 `--allow-write` 才开 `krouter_note`：一行一条，一次 git 提交，记进变更记录 |
| **备份、回滚** | 记忆就是那个 git 仓库：像代码一样备份，`git revert` 撤回一次改动；索引是从文件夹重建的缓存 |

用 [`bench/scale/serve_load.py`](bench/scale/serve_load.py) 在合成记忆库上实测，一台 Apple M2 笔记本（8 GB），服务和调用方在同一台机器上，每行 300 次调用，没有一次失败：

| 页数 | 1 个调用方：中位数、每秒答几次 | 8 个调用方：每秒答几次 | 32 个调用方：中位数、p95、每秒答几次 | 常驻内存 | 启动时建索引 |
|---|---|---|---|---|---|
| 1,000 | 5 ms，195 次 | 646 次 | 42 ms，77 ms，742 次 | 203 MB | 0.5 秒 |
| 10,000 | 13 ms，77 次 | 267 次 | 104 ms，112 ms，301 次 | 216 MB | 3.5 秒 |
| 50,000 | 54 ms，17 次 | 72 次 | 377 ms，651 ms，75 次 | 267 MB | 24 秒 |

复现办法、部署步骤、token 和 TLS 见 [`docs/TEAM.md`](docs/TEAM.md)。

## 装完五分钟

1. 问你的 AI：*「上周我们关于 X 是怎么定的？」* 它会从记忆里查，给出答案和出处页；记忆里没有，就直说没有。
2. 打开记忆文件夹：装好之后的每个会话都在里面，每个会话一页，内容是你的提问和每轮最后的回答（安装最后几行给了一条命令，想把近 7 天的也导进来就跑它）。
3. **「要让模型提炼一下定了什么吗？」** 答应后，你已经在用的模型（登录好的 CLI 或 API key）会在最近几个会话的页面顶上写出「定了什么、改了什么」。发之前它会先告诉你要发多少字。

## 之后它自己跟上

什么都不用你维护，也不用你批；只有会把文字发给模型的那两步要先问你：
- **每一轮结束时**（Claude Code、Codex、Cursor 都是）：agent 一答完，这个会话到目前为止的内容就写进它那一页。只在本机做、不调模型，不到一秒，别的窗口的 agent 马上就查得到。
- **你纠正 AI 的时候**：读起来像纠正的话（「以后都……」「改成……」「from now on…」）在你发出的那一刻就记下来。开新会话时，先带上这个仓库记下的决定，纠正排在前面，每条都带来源页。
- **每天夜里**（这个任务会先问你）提炼前一天的会话、整理记忆库；白天还可以再开一个定时任务补记。
- **每一步都看得见。** 每一轮加了什么、取代了什么，都写进[变更记录](#这页用到的词)；记忆文件夹是 git 仓库时，每一轮是一个单独的提交，`import_sessions.py --undo <轮次>` 一条命令就能撤回。
- **某个会话不想被记**，在它的任何一个提问里写上 `#不记`（或 `#nocapture`）。

**在维护者自己的机器上实际跑出来的**（2026-10-30 → 11-09，每个数字都来自它自己的变更记录；[方法和明细](docs/AUTO_CAPTURE.md#5-back-test-on-the-maintainers-machine-2026-10-30--11-09)）：

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/img/capture-days-dark.svg">
  <img alt="2026-10-30 到 11-09 每天写进记忆的条数：一共 714 条，其中 407 条是改了主意" src="docs/img/capture-days-light.svg" width="760">
</picture>

30 轮一共写进记忆 714 条，其中 407 条是改了主意（「原来 A → 改成 B」），每条都注明来自哪个会话，没有一轮需要撤回。维护者同期亲手记下的 8 条纠错里，5 条在下一轮就进了记忆；2 条被提炼漏掉，1 条是 agent 自己用工具时的问题，导入看不到这一层。公开的决定抽取基准（18 段会话里标了 14 条决定，其中 4 段什么都没定；按规则打分）：14 条全部找到，没有一条多写的。题量小：它说明提炼不会凭空编出决定，不能说明从不漏。

## 适不适合你

**适合**：你在用 AI 助手，哪一个都行，却总要把同一个决定反复交代，或者它总拿几周前已经改掉的说法来回答你。还没有笔记？安装脚本会帮你建好文件夹。同时用好几个 AI 是加分项，不是前提：它们会共用同一份记忆。**不适合**：你要基于向量的语义搜索、要把上一轮聊天自动塞进下一轮、要一个别人替你运营的托管记忆服务（自己部署团队服务器可以，见 [`docs/TEAM.md`](docs/TEAM.md)），或者希望装好就是一个装满的大脑。

**不只用于写代码**：同样的事放到短视频工作里，录法一样（Claude Code 加插件、演示库、真实输出）：

![周一定了封面标题规则 A，周三改成 B，周四 agent 答 B 并给出处页；库里没有的问题直接说没有](docs/img/demo-content.gif)

**不需要**：装 Obsidian（它只是可选的查看器）、维护别名表、自己设环境变量。

## 和常见 agent 记忆的区别

| | KRouter | 常见的 agent 记忆 |
|---|---|---|
| 记忆放在哪 | 你能打开、编辑、比对、同步的 Markdown 页 | 数据库或向量库 |
| 纠错之后 | 新页取代旧页，旧页标成「已取代」 | 新旧两条都能匹配上，只能指望对的那条排前面 |
| 什么都对不上时 | 返回 `recall: none`，AI 会说记忆里没有 | 拿最接近的一条，说得很肯定 |
| 每条答案 | 带出处页和回执 | 通常没有出处 |
| 谁在用 | 本机每个 AI 应用都读同一个文件夹（MCP、skill、规则） | 通常只服务一个工具 |

**在用 [claude-mem](https://github.com/thedotmack/claude-mem)？** 不用卸掉。安装时会发现它的记忆库并问你要不要导入（已经在真实安装的 claude-mem 13.35.0 上完整跑通）：会话总结变成页面，每个项目的决定汇成一页，你的模型还能把这些决定分成还有效的和被后来的决定取代的。你不点头，什么都不导入（[细节](docs/DETAILS.zh.md#导入你已经有的东西)）。

## 什么会离开本机

查询从不外发：查找走本地的 SQLite 全文索引，每次约 110 ms。导入会话也只在本机做。只有你点过头的两步（提炼会话、夜间整理）才会把文字发给模型，发给你本来就在用的 CLI 或 API key，用 `--dry-run` 可以先看会发多少。key 和标成机密的页从不外发，也从不引用。每条模型通道能读到什么，见 [`SECURITY.md`](SECURITY.md)。

**备份。** 运行 `backup.py init --dir <一个会同步到别处的文件夹>`，就会每晚给整个库（连同历史）做一个加密备份包；KRouter 自己不连任何云（[细节](docs/DETAILS.zh.md#备份你的库)）。

## 这页用到的词

| 词 | 在这里的意思 |
|---|---|
| 记忆、记忆库、库 | 放 Markdown 页面的那个文件夹（「库」是 Obsidian 对它的叫法） |
| 页 | 一个 Markdown 文件。「规则页」写的是长期有效的决定，回答先从它出；当天的「笔记页」只当线索 |
| 回执 | 每条答案附带的几行：出自哪一页、为什么是这页、有多大把握 |
| `recall: none` | 记忆里没有匹配得上的内容时的回复；AI 收到它就要直说不知道 |
| 分数下限 | 最低匹配分，低于它 KRouter 就拒答，不拿最接近的一页凑数 |
| 已取代 | 被后来的纠正换掉了：旧的还留着、打了标记，但回答时不再用 |
| 提炼 | 让模型在一个会话的页面顶上写出「定了什么、改了什么」。它会把文字发出去，所以做之前先问你 |
| 变更记录 | 记忆库里记下每一轮加了什么、取代了什么的那一页。默认文件夹是中文名；在库的根目录放一个 `krouter-zones.psv` 可以对应到你自己的文件夹 |
| 一份记忆（bank） | 团队服务上的一个记忆库，有自己的地址、索引和 token |
| 会话钩子 | 应用在会话开始或一轮结束时自动跑的一条命令；每一轮就是靠它记下来的 |
| MCP | Model Context Protocol，AI 应用加载外部工具的通用办法 |
| BM25 | 最常见的关键词检索排序公式，这里当作最朴素的对照 |
| 留出题 | 从没拿来调过任何东西的题 |

## 老实的数字

这一页上每个数字属于哪一套、哪个版本、和谁比、哪些结果对我们不利，都在 [`docs/NUMBERS.zh.md`](docs/NUMBERS.zh.md) 的一张表里；各套方案在跑之前就登记进了 [`HELDOUT.md`](bench/memory_honesty/HELDOUT.md)。上面几节没写到的：

| 测了什么 | 结果 |
|---|---|
| 答案准确率按题型分，KRouter 1.3.0 交 3 页（[第 11 套](bench/memory_honesty/HELDOUT.md#set-11-longmemeval-answer-accuracy-scored-the-way-other-projects-report-it-registered-2026-11-09-before-any-run)） | 单段聊天 61/64（用户说的）和 55/56（助手说的），知识更新 69/72，时间推理 97/127，偏好 20/30，跨多段聊天 69/121。另一个评判实例重判 100 道，100 道一致 |
| 输给满分检索的 93 道题丢在哪，交 3 页（[第 12 套](bench/memory_honesty/HELDOUT.md#set-12-the-same-reader-given-different-things-registered-2026-11-09-before-any-run)） | KRouter 引到一部分答案聊天但没引全的 58 道，一段都没引到的 32 道，全引到的 3 道；有 24 道的答案分散在三段以上 |
| 离题问题（公开测试集，CI 跑） | 英文 12/12、中文 6/6 拒答 |
| 和认真做的基线比（[200 道留出题](docs/BENCHMARK.md#third-bench-200-held-out-questions-on-a-vault-nobody-tunes-on-2026-10-13)） | 给纯全文检索加上同样的两条规则，它引错 42 页、KRouter 36 页，答对 96 道对 102 道；两项差距都不显著 |
| 单独一个进程查一次（[规模](docs/BENCHMARK.md#scale-how-big-a-vault-can-get-2026-11-09)） | 1 万页 0.13 秒，5 万页 0.35 秒 |
| 精确命中和向量检索比（CI 跑） | 精确命中会拒答，TF-IDF、MiniLM、BGE-M3 会引一个近邻；本地向量测过了，没有上线（[`DENSE-OPTIN.md`](docs/DENSE-OPTIN.md)） |
| 作者自己的 208 道历史提问，盲评 | KRouter 0.36，加了两条规则的 BM25 0.25（满分 2），配对区间 [−0.02, +0.24]：看不出差距 |

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

- [工作原理和全部选项](docs/DETAILS.zh.md)：安装参数、夜间写手、精确命中和排序召回、四种 agent 接入
- [`docs/NUMBERS.zh.md`](docs/NUMBERS.zh.md)：每个数字和它的测法
- [`docs/TEAM.md`](docs/TEAM.md)：团队共用一份记忆、自己部署的 HTTP 服务和它的 Docker 镜像
- [`SECURITY.md`](SECURITY.md)：每条模型通道能看到什么、能做什么
- [`docs/FOR-AGENTS.md`](docs/FOR-AGENTS.md)：给 agent 判断 KRouter 适不适合它的用户时参考的事实
- [`CHANGELOG.md`](CHANGELOG.md) · [`CONTRIBUTING.md`](CONTRIBUTING.md)：适合新人的 issue 都打了标签

**维护。** 目前只有一个维护者，这是采用它最大的风险，欢迎外部贡献。项目停了你还剩什么、没有作者时怎么继续：[`MAINTAINERS.md`](MAINTAINERS.md)。小版本每周最多一个，补丁随时发；`KROUTER_TAG=v1.3.0`（换成任何 tag）可以固定版本。哪些算稳定接口：[`DETAILS.md` → Stability and versions](docs/DETAILS.md#stability-and-versions)。问题和 bug 提 [issue](https://github.com/398894496-arch/KRouter/issues)；安全问题见 [`SECURITY.md`](SECURITY.md)。

*原名 DSH-KRouter，旧链接、旧 clone 地址和旧安装命令都会自动跳转。* MIT 协议。
