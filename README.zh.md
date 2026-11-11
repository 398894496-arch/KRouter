# KRouter

**让 agent 拥有下意识：提到就想起，联想到相关的一片，还能举一反三。**

*「下意识」是个比喻，说的是不用你开口问就自动想起：在你本机查一下，不调模型，什么都不发出去。*

KRouter 是给 coding agent（Claude Code、Codex、Cursor、DeepSeek Harness、Hermes、OpenClaw），以及任何接了 MCP 的应用（比如 Claude Desktop）用的本地 Markdown 记忆：你提到以前定过的事，agent 就想起来，相关的也一起带出；一件事里的经验能换个任务用；改了主意会替换旧答案；每个回答都注明出自哪一页。个人使用不需要 API key，不需要服务器；团队服务和用模型提炼是可选的（见下文）。

> **你：** 下午我要把剪藏原件挪到归档文件夹里。
>
> **agent：** 提醒一下：你的偏好页「02 经验与方法/Agent/用户偏好与工作约束.md」里写着不要移动剪藏原件。下午要挪进归档文件夹的话，是想这次例外，还是改成复制一份过去？
>
> **你：** 楼里的咖啡机又坏了。
>
> **agent：** 这确实烦人。需要我帮你写条报修消息，或者查查该找谁处理吗？

你只是顺口提了一句，没有问；KRouter 在你的话里认出了一件定过的事，把它和出处页一起交给 agent。第二句和库里的事都无关，它什么都没加，agent 照常回话。两句 agent 的回复是真实跑出来的：Claude Sonnet 5.5（Claude Code 的子代理，不带工具），2026-11-10，看到的就是下面折叠块里的那段内容，原样照抄；换一个 agent，怎么回由它决定。

<details>
<summary>实际递给 agent 的内容（提问钩子在中文样例库上的原始输出）</summary>

```text
你   > 下午我要把剪藏原件挪到归档文件夹里。
钩子 > KRouter 记忆提示（从用户的记忆库里想起的，不是用户这句话里说的；和这句话无关就不用管）：
       - 「剪藏原件」 → 不要移动剪藏原件 〔02 经验与方法/Agent/用户偏好与工作约束.md，别名〕
       用到就注明出处页。
你   > 楼里的咖啡机又坏了。
钩子 > （什么都没加）
```

</details>

## 安装

```bash
curl -fsSL https://github.com/398894496-arch/KRouter/releases/latest/download/bootstrap.sh -o /tmp/krouter-install.sh && sh /tmp/krouter-install.sh
~/.dsh-krouter/current/scripts/krouter doctor                              # 给出结论：OK，或者缺什么、怎么修
~/.dsh-krouter/current/scripts/krouter search "我们之前 X 是怎么定的？"      # 问第一句
```

什么都不问，本机装了哪个 AI 应用就接哪个。已有的文件夹一个文件都不改，只补缺的；卸载不碰你的记忆。Windows、Claude Code 插件、`--minimal`、它会动哪些文件、不配 key 时哪些能用、怎么卸载：见 [`docs/INSTALL.zh.md`](docs/INSTALL.zh.md)。

**不用安装、不用 key，几秒钟亲眼看一遍**：同样的过程，在一个用完即删的临时记忆库上跑。

```bash
uvx --from git+https://github.com/398894496-arch/KRouter krouter demo --lang zh      # 或者在 clone 里：PYTHONPATH=sdk python3 -m krouter.cli demo --lang zh
```

用你自己的库、Claude Desktop 和 Obsidian：见[写东西的例子](docs/OVERVIEW.zh.md#在-claude-desktop-里用写东西的库)。

### 提到就想起

每一句话都在本机查一遍，会话开始时还先给一份「定过的事」的索引，所以换了说法也接得住。留出集 24 次提及（三分之二没说页面上的名字）：**Sonnet 5.5 想起 24 / 24，Haiku 5.5 23 / 24**；本该什么都不变的话，分别有 1 / 24 和 2 / 24 让它出了声（[第 35 套](bench/memory_honesty/HELDOUT.md#set-35-the-subconscious-as-a-whole--the-prompt-hook-then-the-host-reading-a-standing-index-registered-2026-11-10-before-any-case-existed)）。

### 联想到相关的一片

一次查询交 5 页：3 页和问题对得上，再加最多 2 页是库里和它们相关联的（互相链接、新页取代旧页、同一段会话、共有的少见词、常被一起引用）。LongMemEval 留出的一半、各交 5 页：答案需要的会话全在里面的，**235 道里 210 道，关键词搜索 198 道；跨多段会话的题 40 对 31**（[第 18 套](bench/memory_honesty/HELDOUT.md#set-18-does-following-the-vaults-own-connections-bring-the-whole-answer-registered-2026-11-10-before-the-associative-path-was-written-or-any-held-out-question-was-run)）。

### 举一反三

一件事里得到的经验，换一件处境相同的事时会被提出来；反复被证实的经验会长成技能，事情对得上时 agent 自己去取。留出集：换了题材的任务，提出对的经验 **14 / 14（Sonnet 5.5）和 11 / 14（Haiku 5.5）**，英文 **14 / 14 和 13 / 14**（第 15、16 套）；技能起草对了 16 / 16，取用并照做 12 / 12（第 24、25 套，[`bench/memory_honesty/HELDOUT.md`](bench/memory_honesty/HELDOUT.md)）。

### 托底：你能核对的那一层

每个回答都注明出自哪一页；你的记忆里没有的，回执直接写「没有」，只对上相近内容时写明有多大把握，不拿一条差不多的冒充答案，你存的参考资料也不会被当成你定过的事；纠错之后新结论直接取代旧结论，不会两个一起冒出来；而且都看得见：记忆是一个纯 Markdown 文件夹，能在 [Obsidian](https://obsidian.md) 或任何编辑器里打开、修改，`krouter view`、`krouter why` 显示它记了什么、为什么这样答。你现在用的 AI 就能接，有一个就够。

**拒答分两层，只有第一层是 KRouter 的。** LongMemEval 的 30 道不可答题，只看 KRouter 自己的回执，9 道直接写 `recall: none`；再加上读题模型，30 道里 29 道回答「没提到」，但什么都不给读题模型时，30 道它也全答「没提到」，所以第二个数主要是模型的功劳。KRouter 做的是：库里完全没有对上的内容时直接写没有；对上的只是相近内容时，把依据和把握等级交给模型，不把一条差不多的当答案。这不是没有例外的保证：这 30 道里有 22 道，排第一的页是一段和所问的事相近的真实会话。你声明成[知识库](#它也是你的知识库)的参考资料不算记忆的答案：只有它们对得上时，回执第一行就是 `memory: none`。我们在开发数据上找过一条能多拒近似题的规则（第 37 套），没有一条够好，所以上面的数字不变。改为在回执第一行写明是哪一种：`memory: direct`、`memory: related`（只有相关的页：只有某一页里有一句话直接回答了问题才作答，否则说记忆里没有）或 `memory: none`；那 30 道是 0 / 21 / 9。严格模式（`KROUTER_STRICT=1`，默认关）把 `related` 当 `none`；在只有会话页的记忆上，这意味着它几乎什么都不答（第 38 套）。方法和其他测试见 [`docs/NUMBERS.zh.md`](docs/NUMBERS.zh.md)。

### 它不会做什么

- 样本量小：每一套只有几十例。
- 这些评测里，宿主是把要取哪一页写出来，没有真的去调工具。
- 真实会话里，宿主几乎不会主动写经验卡（第 30、31 套：两个宿主都是 4 次里 0 次）；学习靠钩子和夜间整理。
- Cursor 上每句话那一层用不了（它的钩子加不了上下文），只有会话开始的索引。
- 5 页版本的答题正确率没有重跑（第 22 套已登记，没有跑）。
- 2.0 没有在 Windows 上实测。
- 问的是记忆里某件事的近邻时，它还是会作答，多半是 `low` 或 `medium`。段落级证据（第 39 套）在 LoCoMo 上多拒了（223 道里 18 → 61），在 LongMemEval 上没有（30 道里 9 → 10），所以默认关。
- 参考资料不用声明，逐页自动认（第 40 套：留出的 32 篇外来资料认出 30 篇，你自己的 43 页误判 0 页），只在合成库上测过；认错了用 `krouter kb mine 页面` 改。

[![ci](https://github.com/398894496-arch/KRouter/actions/workflows/ci.yml/badge.svg)](https://github.com/398894496-arch/KRouter/actions/workflows/ci.yml) [![release](https://img.shields.io/github/v/release/398894496-arch/KRouter)](https://github.com/398894496-arch/KRouter/releases/latest) [![license](https://img.shields.io/badge/license-MIT-blue)](LICENSE) · English: [`README.md`](README.md)

**工程事实**，每一条现在就能核对：项目创建于 2026-08，目前一个维护者（[`MAINTAINERS.md`](MAINTAINERS.md)）。

- 每次推送都在 Linux、macOS、Windows 上跑全量测试（2.1.0 时 687 个；`python3 -m pytest -q`），另有一个容器冒烟测试（[`ci.yml`](.github/workflows/ci.yml)）。
- 每个发布版带 SHA-256 校验和与 GitHub 构建来源证明（`gh attestation verify <安装包> --repo 398894496-arch/KRouter`）；一行安装只用 tag、从不拉 `main`，运行任何东西之前先核对校验和。
- 发布之后，有一个任务把本页给出的每条安装命令对着线上地址实跑一遍（[`release_smoke.py`](scripts/release_smoke.py)、[`release.yml`](.github/workflows/release.yml)）；容器镜像是 `ghcr.io/398894496-arch/krouter`。
- 已登记在官方 MCP Registry，名字是 `io.github.398894496-arch/krouter`。
- 评测先登记再跑（没这样做的行，[`docs/NUMBERS.zh.md`](docs/NUMBERS.zh.md) 里都写明了）；题集和脚本都在仓库里（[`HELDOUT.md`](bench/memory_honesty/HELDOUT.md)、[自己复现](#自己复现)）。
- [`SECURITY.md`](SECURITY.md)、[`CHANGELOG.md`](CHANGELOG.md)，升级 `./scripts/install.sh --upgrade`，卸载 `./scripts/uninstall.sh`，回到更早的版本用 `KROUTER_TAG=`（[`DETAILS.zh.md`](docs/DETAILS.zh.md)）。你问的问题从不离开本机。

![周一定了 A，周三改成 B，周四 agent 答 B 并引用那条纠错；库里没有的问题直接拒答](docs/img/demo.gif)

开始用不需要 key：查询、出处、拒答都不调模型；改了主意照样算数：新页排在前面并标出冲突，agent 也能在你纠正的那一轮就把纠正落实（[没有模型时哪些能用](docs/INSTALL.zh.md#没有-api-key-时)）。

| 我想…… | 从这里开始 |
|---|---|
| 装之前先看它怎么答、怎么被纠正、怎么拒答 | `krouter demo`（上面这行） |
| 看它记了什么、为什么这样答 | [`krouter view`、`krouter why`](#看得见它记了什么) |
| 给我已经在用的 AI 应用接上记忆 | [安装](#安装)：一行，什么都不问，本机装了哪个应用就接哪个（`--minimal`：只装查询、只接你点名的） |
| 看能接哪些应用 | [能接哪些应用](#能接哪些应用) |
| 让它读我已有的笔记和文档 | [它也是你的知识库](#它也是你的知识库) |
| 给团队共用一份记忆：每人一个令牌，谁改了什么查得到 | [给团队用](#给团队用) |
| 从自己的代码里调用 | [从你自己的代码里用](#从你自己的代码里用) |
| 自己复现这些数字 | [自己复现](#自己复现) |
| 弄清楚什么会离开本机 | [什么会离开本机](#什么会离开本机) |
| 看这一页挪出去的全部内容（写东西的例子、各套评测的长说明、每个应用的实测记录） | [`docs/OVERVIEW.zh.md`](docs/OVERVIEW.zh.md) |

## 给团队用

**只在一台机器上测过，还没有真实团队用过几周。**一个服务装下你们团队的一份记忆：放在 git 仓库里的一个 Markdown 文件夹，自己部署（没有 KRouter 云服务）。每个人一个令牌，每次写入都记在写的人名下，「这条是谁在什么时候改的」查得到（`krouter_changes`）；两个人对同一个决定给出相反的纠正时，后到的生效，先到的保留为被取代，回执里点名。十个人的 agent 在一台笔记本上同时读写（第 27 套）：三种规模下各 440 次调用 0 次出错，每种规模的 204 次写入都记到了对的人名下、一条不丢；1 万页连跑 30 分钟：21,218 次调用 0 错误。**只在单机上测过，没有真实团队长期使用的记录。** 部署、令牌、TLS 和这些数字：见 [`docs/TEAM.zh.md`](docs/TEAM.zh.md)。

## 它也是你的知识库

把 KRouter 指向你已有的 Markdown 文件夹（Obsidian 库、文档仓库、笔记目录），里面每一页都能被查到，并带出处。文件夹里的页分两种：**你的记忆**（你定过的事、规则、纠正、会话提炼出来的东西）和**你的知识库**（参考资料：文章、剪藏、研究材料、别人写的文档）。两种都能查到；只有你的记忆算「你定过什么」。

```bash
krouter kb add "研究资料"           # 把一个文件夹声明成知识库（就是记忆文件夹里 krouter-kb.txt 的一行）
krouter kb mine "笔记/随笔.md"      # 被认成资料、其实是你自己写的页（或文件夹）
krouter kb import 报告.pdf          # 把 PDF、Word、HTML 转成知识库里的一页 Markdown
```

名字带 `剪藏`、`Clippings`、`Web clips` 的文件夹，和页头是网页剪藏插件写的页，不用声明也算知识库。查询时知识库的页单独列一块，每条带标题、出处和命中的那一行，不影响置信度；只有它们对得上时，回执第一行就是 `memory: none`：

```text
memory: none（你的记忆里没有这件事；只有知识库里的参考资料对得上，列在 knowledge_base 下面）
…
recall: none (no page covers enough of the question; do not guess)
knowledge_base: 你知识库里的参考资料（文章、剪藏、文档，是别人写的，不是你定过的事）。作为资料引用、给出处；不要说成你的决定
- 研究资料/某次账单故障复盘.md kb=declared score=…
  title: 某次账单故障复盘
  L5: 迁移过程中账单服务的数据库连接被占满……
```

**它不做的：** 只检索 Markdown；`import` 用你本机已有的工具转换别的格式（`markitdown`、`pandoc`，PDF 也可以用 `pdftotext`；纯 HTML 不需要任何工具），一个都没有时会告诉你装哪个。没有向量检索（[测过，没有上线](docs/DENSE-OPTIN.md)）。没声明的页按来历和样子逐页分（来源行、署名、像文章的标题和篇幅），`krouter why` 会说为什么（[细节](docs/DETAILS.zh.md#剪藏和别人写的材料)）。

## 从你自己的代码里用

`pipx install "git+https://github.com/398894496-arch/KRouter"`，然后在 Python 里 `krouter.ask("我们怎么发版？")` 给出出处页、一句话结论、库里有没有；`krouter.note(…)` 记一笔。LangGraph 的长期记忆也能放在这个文件夹里（`krouter.integrations.langgraph.KRouterStore`）；JavaScript、LlamaIndex 和别的框架的 MCP 客户端：见 [`docs/INSTALL.zh.md`](docs/INSTALL.zh.md#从你自己的代码里用) 和 [`docs/FRAMEWORKS.zh.md`](docs/FRAMEWORKS.zh.md)。

## 能接哪些应用

一次安装，本机装了哪个就接哪个，每个都按它自己文档里的格式写设置；文件里原有的内容保留、另存一份备份，`uninstall.sh` 只删自己加的。每个应用完整的实测记录：[`docs/OVERVIEW.zh.md`](docs/OVERVIEW.zh.md#能接哪些应用完整)。

| 应用 | 怎么接 | 实测到什么程度 |
|---|---|---|
| Claude Code | 插件（会话钩子，含每句话那一层）和 MCP，安装脚本都会装上 | 应用里实测过，也在真实会话里跑过（[`VERIFY.md`](docs/VERIFY.md#platforms-and-real-sessions-200-candidate-2026-11-10)） |
| Codex | MCP 加会话钩子（`~/.codex/hooks.json`；在 Codex 里 `/hooks` 信任一次），含每句话那一层 | codex-cli 0.155.0-alpha.9.2（2026-11-09）：发现工具、带出处答对、拒答，钩子都跑了；20 个真实小任务 |
| Cursor | 规则和 skill、MCP、会话钩子；没有每句话那一层（它的钩子加不了上下文），用会话开始的索引 | Cursor 命令行 agent 2026.11.05（2026-11-09）：列出工具、带出处答对、拒答，钩子写出了会话页；3 个真实任务 |
| DeepSeek Harness | 插件：`dsh plugin --profile web add github:398894496-arch/KRouter` | 已实测 |
| Hermes | MCP：`hermes mcp add krouter --command python3 --args …/mcp_server.py`（[做法](docs/INSTALL.zh.md#hermes-和-openclaw)）；只有查询工具，没有钩子 | Hermes Agent 0.18.2（2026-11-10），单独的配置目录：连上，列出 5 个工具；那里没问问题（没有登录模型） |
| OpenClaw | 技能目录：OpenClaw 读 `~/.agents/skills`，安装脚本正好把 KRouter 放在那里（[做法](docs/INSTALL.zh.md#hermes-和-openclaw)）；也能走 MCP | 已在真实使用中以技能方式运行（1.2.x）；2.x 还没在 OpenClaw 里跑过；MCP 这条没试 |
| Claude Desktop | 双击 [`KRouter.mcpb`](https://github.com/398894496-arch/KRouter/releases/latest/download/KRouter.mcpb)，点一次安装；或者应用关着时由安装脚本写设置文件 | 扩展包在应用里实测（4.23118.1，macOS，2026-11-10）：工具连上、带出处答对、库里没有的拒答；测的是写了完整 Python 路径的包，和安装脚本做的一样 |
| VS Code（Copilot）· Copilot CLI · Gemini CLI · Kiro · Zed · Cline CLI | MCP：安装脚本写好各自的设置文件；重启一次应用 | 设置按各家文档的格式由测试检查过 |
| 其他能跑本地 MCP 服务的应用（Windsurf、opencode、Continue、Roo Code……） | 把下面这段加进应用的 MCP 设置 | 我们没跑过：[告诉我们](https://github.com/398894496-arch/KRouter/issues) |
| LangGraph 长期记忆（不走 MCP） | `krouter.integrations.langgraph.KRouterStore`（[`FRAMEWORKS.zh.md`](docs/FRAMEWORKS.zh.md#langgraph-存储长期记忆)） | 真实的图里实测（langgraph 1.0 和 1.2），CI 也跑 |
| LlamaIndex、LangChain、OpenAI Agents SDK、Pydantic AI、Google ADK、CrewAI、Vercel AI SDK | 自带 LlamaIndex 检索器；其他用各自的 MCP 客户端（[`FRAMEWORKS.zh.md`](docs/FRAMEWORKS.zh.md)） | 对着服务实测，CI 也跑；其中三个连整个 agent 循环一起跑过 |
| 你自己的代码 | Python 包和 `krouter` 命令；不依赖任何包的 JavaScript / TypeScript 客户端 | 已实测 |

```json
{ "mcpServers": { "krouter": { "command": "python3",
    "args": ["/Users/you/.agents/skills/krouter/scripts/mcp_server.py"] } } }
```

已登记在官方 MCP Registry，名字是 `io.github.398894496-arch/krouter`（[登记条目](https://registry.modelcontextprotocol.io/v0/servers?search=io.github.398894496-arch/krouter)），指向发布页上的 `KRouter.mcpb`，从注册表里找 MCP 服务的应用能搜到它。

路径要写到你自己的用户目录（Windows 上是 `C:\\Users\\you\\.agents\\…`，命令常常是 `python`）。这个服务只用 Python 标准库，走 stdio，提供三个工具：`krouter_ask` 和 `krouter_status` 只读；`krouter_note` 让你的 AI 记下一行（一个决定、一处纠正、一个事实）。这一行写进当天的笔记页，只当线索，不会写进规则页；它是一次单独的 git 提交，可以撤回。

## 和 MemOS、Hindsight 放在一起看

| | KRouter | MemOS | Hindsight |
|---|---|---|---|
| 怎么跑、要装什么 | 一个 Markdown 文件夹加本地索引；只用 Python 标准库，一条命令装好，不用服务、不要 key | 云（API key）、自部署（Neo4j + Qdrant）或本地插件（Node.js） | PostgreSQL + pgvector 上的一个服务加一个 LLM key，或 Hindsight Cloud |
| 不问也想起 | 在有每句话钩子的宿主里，每句话都在本机查一遍（Cursor 没有，见「接哪些」的宿主列表），不调模型；热启动中位数：110 页的测试库 83–87 ms，1 万页库 116–126 ms（整个钩子进程，p95 最高 144 ms；第 34 套，2.1.0 之前测的；2.1.0 的提问钩子在 1 万页库上热启动 p95 是 129–131 ms，第 39 套）；会话开始还有一份索引 | 插件在「任务开始前」「每次 agent 运行前」召回 | 给 coding agent 的包在 agent「开始工作时」注入记忆 |
| 结论带出处 | 每个回答都带，附回执 | 页面上没有说明 | observation 保留原话引文和证据数 |
| 知识库 | 参考资料逐页自动认出（也可声明），单独列出，可从 PDF / Word / HTML 导入；没有向量检索 | 「Multi-Cube Knowledge Base Management」 | 页面上没有作为单独一层说明 |
| 敢说不知道 | **整条链（第 41 套，2026-11-11，读题模型 Haiku 5.5 和 Sonnet 5.5）：LongMemEval 30 道不可答题里 29 / 28 道说了记忆里没有；LoCoMo 陷阱题 60 道里 55 / 38；40 道可答题对照里分别误拒 11 / 7 道；事先定的过关线没达到；同一个 Haiku 什么都不给时 40 道里 39 道这样说。** 检索层：回执 30 道：9 道 `none`、21 道 `related`（只有相关的页）、0 道 `direct`；早先加读题模型 29 / 30，但不给材料时也是 30 / 30 | 页面上没有数字 | 页面上没有数字 |
| 标准评测 | 只测检索，按作者标注评分；还没参加同台评测 | 自报（OmniMemEval）：LongMemEval 89.20、LoCoMo 88.83 | LongMemEval 最好成绩（厂商图表，2026-01），部分由别人复现 |
| 规模（GitHub，2026-11-11） | 49 星，一个维护者 | 12 352 星 | 60 340 星；有托管，承诺 99.9% 可用 |

每一格的出处和日期，以及为什么这些数字不能比大小：[`docs/COMPARE.zh.md`](docs/COMPARE.zh.md)。


## 十个项目并排看

十个开源记忆项目，每一格只写那家自己 GitHub 页面上的说法（2026-11-11 抓取）；“页面上没有说明”只表示 README 没写，不代表做不到。

|  | 怎么跑 | 核心功能要 key 吗 | 不问也想起 | 回答带出处 | 页面上的评测数字 | 星数 |
|---|---|---|---|---|---|---|
| **basic-memory** | 本地 `uv tool install`，文件在本机；另有云版 | 本地：页面没提 key；云：登录 | Claude Code 插件：会话开始简报；其余页面上没有说明 | 页面上没有说明 | 无评测数字 | 4,550 |
| **claude-mem** | `npx claude-mem install`；本机 SQLite | 要选提供方：自家 observer（30 天试用）、自己的 OpenRouter/Gemini key、或 Anthropic 订阅 | “会自动出现在新会话里” | 每条观察有 ID，可引用 | 无基准数字（只写“约 10 倍 token 节省”） | 115,909 |
| **cognee** | pip 安装；Docker；云 | 本地快速上手不要；要“生成回答”才设 LLM key | 页面上没有说明（有 Claude Code、Codex 插件） | “可检查召回到的证据” | 自报 BEAM：0.79（100K，20 题）、0.67（10M，探索性） | 33,232 |
| **graphiti** | Python 框架；自备图数据库（Neo4j、FalkorDB、Neptune）和 LLM | 默认 OpenAI，需 `OPENAI_API_KEY` | 页面上没有说明 | 每个事实可追溯到原始 episode | 无数字（有论文链接） | 32,727 |
| **Hindsight** | 服务器（Docker、pip、Helm）、Python 内嵌、云 | 快速上手要 LLM key；页面写可用本地模型 | 编码 agent 包启动时注入；LLM 包装每次调用自动存取 | 观察附原文引用和证据计数 | 只有图表（LongMemEval，2026-01）；写“已被他人复现”，无数字 | 60,340 |
| **KRouter** | 一个 Markdown 文件夹 + SQLite；一行安装；无服务 | 查询不需要；只有可选的提炼用模型 | 在有每条消息钩子的宿主里，每条消息本机查一遍（Cursor 没有，见「接哪些」的宿主列表），不调模型；热启动中位数：110 页的测试库 83–87 ms，1 万页库 116–126 ms（整个钩子进程，p95 最高 144 ms；第 34 套，2.1.0 之前测的；2.1.0 的提问钩子在 1 万页库上热启动 p95 是 129–131 ms，第 39 套） | 每个回答说出页面并附回执 | 自报：LongMemEval 留出半 210/235（BM25 198，仅检索）；LoCoMo 991/1,540 | 49 |
| **Letta** | npm 装终端工具；`letta server`；云 | 页面上没有说明 | 页面上没有说明 | 页面上没有说明 | 无数字 | 25,413 |
| **mem0** | 库（pip/npm）、自托管（docker compose）、云 | 要 LLM（默认 OpenAI）；云要注册 key | 页面上没有说明（示例是代码里手动检索） | 页面上没有说明 | 自报（托管平台）：LoCoMo 92.5，LongMemEval 94.4，BEAM 64.1/48.6 | 68,777 |
| **MemOS** | 四个入口：云 API、自托管（Neo4j+Qdrant）、云插件、本地插件（Node.js，SQLite） | 云：要 key；自托管：.env 里填 key；本地插件：页面上没有说明 | DeepSeek Harness 插件：自动召回；OpenClaw 云插件：每次运行前召回 | 页面上没有说明 | 自报（OmniMemEval）：LoCoMo 88.83，LongMemEval 89.20 等十项 | 12,352 |
| **Supermemory** | 云（插件、托管 MCP）、本地一个二进制、Docker | 本地：嵌入无需 key，首次启动生成本地 key；云：页面上没有说明 | “后台运行，下次对话你的 AI 已经认识你” | 页面上没有说明 | 自报：三个基准都写 “#1”（无分数）；LongMemEval Recall@15 95% | 31,592 |

每一格的出处和日期、完整版：[`docs/COMPARE-ALL.zh.md`](docs/COMPARE-ALL.zh.md)。别家的数是别的题、别的模型，不能互相排名，也不能和 KRouter 的排名；这张表不排名，也不说谁第一。

## 第一天：把过去的会话带进来

做一次就行：让 agent 把你以前的会话导进来，它第一天就认识你以前定过的事。前两步不调模型、内容不离开本机；第三步用你 agent 的订阅额度（每个会话至少一次调用，默认只做最新的 40 个，不会一次把全部历史做完）：见 [`docs/INSTALL.zh.md`](docs/INSTALL.zh.md#把以前的会话导进来)。

```bash
python3 ~/.agents/skills/krouter/scripts/import_sessions.py --days 3650 --dry-run --distill        # 看数量，不写入
python3 ~/.agents/skills/krouter/scripts/import_sessions.py --days 3650 --local                    # 全部导入，不调模型
python3 ~/.agents/skills/krouter/scripts/import_sessions.py --days 3650 --distill --distill-max 40  # 提炼最新的 40 个
```

## 看得见它记了什么

什么都不藏，而且有一页可以看。两条命令都只读。

```bash
krouter why "我们哪天发版"      # 这一次查询是怎么得出结果的，用人话讲
krouter view                    # 只在本机的一个网页：打印 http://127.0.0.1:<端口>/，不会替你打开
krouter view --demo             # 在一个用完即删的样例记忆库上看同一个页面（加 --open 才会用默认浏览器打开）
```

![krouter view「试一句」：两页对计费数据库说法不同，较新的一页排第一并标出冲突，每一页都有对上的词、得分和层级](docs/img/view-why-zh.png)

`why` 会讲：对上了哪个别名或哪些词、每一页为什么排在这个位置、置信度为什么是这一档、哪些页是沿联想带出来的（从哪一页出发）、谁取代了谁；库里没有时，是问题里哪个词库里找不到。`view` 再加上：页面列表和搜索（几万页也是分页读）、以一页为中心的关联和每条边的来由、经验卡被提出和被采纳的次数、最近几晚做了什么，以及一个直接跑 `why` 的输入框。它只绑 127.0.0.1，只回应 GET（所以改不了记忆库），不从网上加载任何东西，中英文都能用，深浅色都能看，手机宽度不破版。[怎么读](docs/DETAILS.zh.md#看得见krouter-why-与-krouter-view)。

## 什么会离开本机

查询从不外发：查找走本地的 SQLite 全文索引（热启动中位数：110 页的测试库 83–87 ms，1 万页库 116–126 ms（整个钩子进程，p95 最高 144 ms；第 34 套，2.1.0 之前测的；2.1.0 的提问钩子在 1 万页库上热启动 p95 是 129–131 ms，第 39 套））。导入会话也只在本机做。只有你点过头的两步（提炼会话、夜间整理）才会把文字发给模型，发给你本来就在用的 CLI 或 API key，用 `--dry-run` 可以先看会发多少。key 和标成机密的页从不外发，也从不引用。每条模型通道能读到什么，见 [`SECURITY.md`](SECURITY.md)。

**备份。** 运行 `backup.py init --dir <一个会同步到别处的文件夹>`，就会每晚给整个库（连同历史）做一个加密备份包；KRouter 自己不连任何云（[细节](docs/DETAILS.zh.md#备份你的库)）。

## 用数字说话

按基准作者自己的标注机械评分、不调模型：LongMemEval 留出的一半里，KRouter 给的 5 页把答案需要的会话交齐的是 **235 道里 210 道，纯关键词检索 198 道**（跨多个会话的题 47 道里 40 道对 31 道；[第 18 套](bench/memory_honesty/HELDOUT.md#set-18-does-following-the-vaults-own-connections-bring-the-whole-answer-registered-2026-11-10-before-the-associative-path-was-written-or-any-held-out-question-was-run)）。5 页版本的答题正确率还没测（第 22 套）；3 页时（1.3.0）是 500 道答对 400 道，和 BM25 打平。我们自己的 200 道留出题：KRouter 引错 26%，claude-mem 64%，basic-memory 78%；给纯检索加上 KRouter 那两条规则就和它打平。整节原文和弱点：[`docs/OVERVIEW.zh.md`](docs/OVERVIEW.zh.md#用数字说话)；每个数字和方法：[`docs/NUMBERS.zh.md`](docs/NUMBERS.zh.md)。

## 自己复现

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

- [`docs/COMPARE.zh.md`](docs/COMPARE.zh.md)：和 MemOS、Hindsight 放在一起看，每一格都有出处
- [`docs/COMPARE-ALL.zh.md`](docs/COMPARE-ALL.zh.md)：十个开源记忆项目并排看，每一格都有出处和日期
- [`docs/OVERVIEW.zh.md`](docs/OVERVIEW.zh.md)：这一页挪出去的部分，原样保留：写东西的例子、各套评测的长说明、每个应用的实测记录、装完之后和它自己跟上、适不适合你、和常见记忆的区别、用到的词、老实的数字
- [工作原理和全部选项](docs/DETAILS.zh.md)：安装参数、夜间写手、精确命中和排序召回、四种 agent 接入
- [`docs/NUMBERS.zh.md`](docs/NUMBERS.zh.md)：每个数字和它的测法
- [`docs/TEAM.zh.md`](docs/TEAM.zh.md)（完整的英文说明在 [`docs/TEAM.md`](docs/TEAM.md)）：团队共用一份记忆、自己部署的 HTTP 服务和它的 Docker 镜像
- [`SECURITY.md`](SECURITY.md)：每条模型通道能看到什么、能做什么
- [`docs/FOR-AGENTS.md`](docs/FOR-AGENTS.md)：给 agent 判断 KRouter 适不适合它的用户时参考的事实
- [`ROADMAP.zh.md`](ROADMAP.zh.md)：下一步打算做什么，不写日期
- [`CHANGELOG.md`](CHANGELOG.md) · [`CONTRIBUTING.md`](CONTRIBUTING.md)：适合新人的 issue 都打了标签

**维护。** 目前只有一个维护者，这是采用它最大的风险，欢迎外部贡献。项目停了你还剩什么、没有作者时怎么继续：[`MAINTAINERS.md`](MAINTAINERS.md)。小版本每周最多一个，补丁随时发；`KROUTER_TAG=v2.1.0`（换成任何 tag）可以固定版本。哪些算稳定接口：[`DETAILS.md` → Stability and versions](docs/DETAILS.md#stability-and-versions)。问题和 bug 提 [issue](https://github.com/398894496-arch/KRouter/issues)；安全问题见 [`SECURITY.md`](SECURITY.md)。

*原名 DSH-KRouter，旧链接、旧 clone 地址和旧安装命令都会自动跳转。* MIT 协议。
