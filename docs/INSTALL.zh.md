# 安装 KRouter

README 只留了最短的一条路（一行安装，再跑 `krouter doctor` 和问第一句）。其余关于安装的都在这里：Windows、Claude Code 插件、`--minimal`、安装会新建或改动的每个文件、不配 key 时哪些能用、装之前先看看、卸载，以及从你自己的代码里调用。

```bash
curl -fsSL https://github.com/398894496-arch/KRouter/releases/latest/download/bootstrap.sh -o /tmp/krouter-install.sh && sh /tmp/krouter-install.sh
```

先把脚本存成文件再运行：下载失败就停在这一步，退出码非零（`curl … | sh` 会拿空脚本跑一遍，还报成功）。Windows（PowerShell）：`irm https://github.com/398894496-arch/KRouter/releases/latest/download/bootstrap.ps1 | iex`
· 只装 Claude Code 插件：`/plugin install krouter --marketplace 398894496-arch/KRouter`（[版本要求和更新办法](DETAILS.zh.md#claude-code-插件)）。

唯一的前提是 Python 3；装了 ripgrep 只是让大库的原文搜索快一点。两种装法都什么都不问，选一种（参数跟在脚本后面：`sh /tmp/krouter-install.sh --minimal --apps claude`）：

| | 默认 | `--minimal`（最小安装） |
|---|---|---|
| 查询带出处、库里没有就直说 | 有 | 有 |
| 接哪些应用 | [下面这张表](../README.zh.md#能接哪些应用)里本机装了的全部 | 只接你用 `--apps claude,codex,cursor,…` 点名的（不点名就一个都不接） |
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
| `~/.agents/skills/krouter/` | 路由器 |
| `~/.config/krouter/vault` | 记着记忆在哪，给钩子和 MCP 服务用 |
| `~/.claude.json`（`claude mcp add`）、`~/.claude/settings.json`（插件和它的市场） | Claude Code |
| `~/.codex/config.toml`（`codex mcp add`）、`~/.codex/hooks.json` | Codex |
| `~/.cursor/mcp.json`、`~/.cursor/hooks.json`、`~/.cursor/rules/` | Cursor |
| [下面表里](../README.zh.md#能接哪些应用)其他应用各自的 MCP 设置文件 | 只动本机装了的；改过的文件旁边留一份 `*.krouter-bak` |
| Claude Desktop 的 `claude_desktop_config.json` | 只在应用关着时写（用扩展包的话：点安装后应用会先联网检查几秒，界面没有反应；只点一次、等它好，再点一次可能会把它卸掉）；开着时一个字不改：给你一个 `~/.config/krouter/KRouter.mcpb` 去双击，或者退出应用后跑安装最后打印的那条 `--connect claude-desktop` 命令 |
| `~/.cache/krouter/`、`~/.local/state/krouter/` | 搜索缓存（可重建）和导入进度 |

2.0 的实测范围：macOS（安装、升级、卸载、在各应用里）；Linux 在干净的 `python:3.12-slim` 容器里（安装、从 2.0 以前的目录升级、查询、拒答、`doctor`、卸载；容器里没有定时器，`--timer` 现在会明说夜间任务**没有**装上）。**Windows 这版没有实测**：没有可连上的 Windows 机器；2026-10-11 那次检查见 [`docs/VERIFY.md`](VERIFY.md)，旧目录搬家的逻辑由一个测试固定。

安装过程中除了下载本身，没有任何内容离开本机。装完：

```bash
~/.dsh-krouter/current/scripts/krouter doctor     # 一句结论：正常，或缺什么、用哪条命令补
~/.dsh-krouter/current/scripts/krouter search "上周 X 最后定了什么？"
```

（在 clone 里用 `./scripts/krouter`；装了 Python 包、`krouter` 在 PATH 上，直接 `krouter`。）记忆文件夹就是纯 Markdown，用任何编辑器打开都行，喜欢的话也可以用 Obsidian。各个工具按这个顺序找它：`KROUTER_VAULT`，其次 `OBSIDIAN_VAULT`（旧名字，照样认；两个都设了以 `KROUTER_VAULT` 为准），最后是安装时记在 `~/.config/krouter/vault` 里的路径。

### 没有 API key 时

查询、带出处的回答、库里没有就直说、本地导入会话、记下读起来像纠正的话，都照常；改了主意有三道保障：

1. **新页排前面。** 两页导入的会话对这个问题都答得差不多，较新的那页写了改动（`改成`、`换成`、`switched … to`、`instead of` 等）而且点到了这件事：新页排第一，回执写 `recall_conflict: an earlier page says otherwise`。不调模型；换别的说法改主意，它认不出来。
2. **agent 当轮落实。** 你纠正它时，它调 `krouter_correct`：旧页标成已取代，下一次查询就给新答案。前提是 agent 真的去调（MCP 的说明里要求它调）。
3. **夜间借你已登录的 agent。** 开了夜间任务、又没有 key 时，提炼和纠正候选的判定借用一个已登录的 AI 编程命令行的订阅额度（`claude --print` 等；Codex 要设 `KROUTER_ALLOW_CODEX=1`），每天最多 30 次，每次记在库里；`KROUTER_HOST_CLI=0` 关掉。用 Codex 真跑过一次：会话提炼了，旧页标成了已取代。

既没有 key、也没登录任何命令行时，提炼（每页开头的「定了什么、改了什么」）、其余的夜间整理和纠正候选的判定都不跑；前两道没接住的改动，查询时旧页仍可能排第一。2026-11-10 在临时 HOME 里不配 key 实测：周一定 PostgreSQL、周三改 SQLite，导入、不提炼：SQLite 那页排第一并带冲突提示；调过 `krouter_correct` 之后，旧页已取代，纠正页排第一。安装输出和 `krouter doctor` 都会说你现在是哪种状态。

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


### Hermes 和 OpenClaw

**Hermes**（Hermes Agent）把 KRouter 当作一个 stdio 的 MCP 服务接入。安装脚本不写 Hermes 的设置，自己加一次：

```bash
hermes mcp add krouter --command python3 --args ~/.agents/skills/krouter/scripts/mcp_server.py
hermes mcp test krouter      # 连上并列出 krouter_ask、krouter_status、krouter_note 等工具
```

这会在 Hermes 的 `config.yaml` 里写一条 `mcp_servers.krouter`（`HERMES_HOME` 可以让 Hermes 用另一个配置目录）。记忆文件夹和别的应用一样从 `~/.config/krouter/vault` 读，也可以在 `--args` 前加 `--env KROUTER_VAULT=<文件夹>`。Hermes 只拿到查询工具：KRouter 没有给它的会话钩子，所以没有每句话那一层，也没有会话开始的索引。在 Hermes Agent 0.18.2 上试过（2026-11-10，单独的 `HERMES_HOME`）：服务连上，五个工具都列出来了；在那里没有问问题（那份配置里没有登录任何模型）。

**OpenClaw** 从 `~/.agents/skills` 读技能（它的「个人 agent 技能」目录，[OpenClaw 文档：Skills](https://docs.openclaw.ai/tools/skills)），安装脚本正好把 KRouter 放在那里（`~/.agents/skills/krouter/`）。不用再做别的：agent 读那里的 `SKILL.md`，通过技能里的路由脚本查记忆，`sh ~/.agents/skills/krouter/scripts/route_knowledge.sh search "<问题>"`（回执和 `krouter_ask` 一样）。这条路有人在用：一台外部用户的机器（维护者帮忙装的）自 2026-10-26 起用这种方式跑 KRouter 1.2.1；2.x 还没有在 OpenClaw 里跑过。OpenClaw 也能接 MCP 服务（[OpenClaw 文档：MCP](https://docs.openclaw.ai/tools/mcp)），这条我们没试过：

```bash
openclaw mcp add krouter --command python3 --arg ~/.agents/skills/krouter/scripts/mcp_server.py
openclaw mcp probe krouter
```

## 把以前的会话导进来

建议装完做一次：让 agent 把这台机器上已有的会话（Claude Code、Codex、Cursor）导进来，这样它第一天就认识你以前定过的事。分三步，前两步都不调模型。

```bash
python3 ~/.agents/skills/krouter/scripts/import_sessions.py --days 3650 --dry-run --distill       # 1. 看数量，不写入
python3 ~/.agents/skills/krouter/scripts/import_sessions.py --days 3650 --local                   # 2. 全部导入，不调模型
python3 ~/.agents/skills/krouter/scripts/import_sessions.py --days 3650 --distill --distill-max 40 # 3. 提炼最新的 40 个
```

1. **预演。** 什么都不写、什么都不发。最后一行写着有多少个会话（`sessions`）、会写几页（`pages`）、第 3 步会把几个会话交给模型（`distilled`）、多少字（`chars`）。做第 3 步之前先把这几个数告诉用户。
2. **导入。** 每个会话一页，放在 `05 时间日志/会话摘录/`（英文库是 `05 Journal/Sessions/`）：你的提问和每一轮最后的回答，已脱敏。不调模型，内容不离开本机。导进来马上就能查；以前问过、当时没记下答案的问题，不会被当成答案。
3. **提炼。** 每个会话交给模型通道，在那一页写上「定了什么、改了什么」：你配了 key 就用 key，否则借一个已登录的 AI 编程命令行的订阅额度（`claude --print` 等；Codex 要设 `KROUTER_ALLOW_CODEX=1`）。每个会话至少一次调用，长的会更多。`--distill-max`（默认 40）取最新的这么多个会话；已经提炼过的不会再发。走已登录的命令行时另有每天 30 次的上限（`KROUTER_HOST_CLI_MAX`），每次都记在库里的订阅调用记录页。**2.0 不会自己把全部历史分批做完**：想往前多做，换一天把第 3 步再跑一次，把数字调大（80、120……）。没有 key、也没登录任何命令行时，它只说一次 `distill skipped`，摘录照写，正常退出。

怎么撤回：每一轮提炼在变更记录（`90 系统文件/自动化/记忆变更记录.md`）里有编号；记忆文件夹是 git 仓库时（在里面 `git init` 一次），`import_sessions.py --undo <编号>` 撤回那一轮。第 2 步写的是新文件，每个会话一页，在 `05 时间日志/会话摘录/`：删掉就撤回了。Windows 上用 `python` 和 `%USERPROFILE%\.agents\skills\krouter\scripts\import_sessions.py`。

2026-11-10 在临时 HOME 里用 5 个合成会话、不配模型实测：预演报 5 个会话、5 个待提炼、7,800 字，什么都没写；导入写了 5 页，什么都没发；第 3 步说 `distill skipped: no model lane …`，退出码 0。

## 从你自己的代码里用

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

JavaScript / TypeScript（Node 18+），本机的或团队服务都行（[`sdk/js`](../sdk/js)；还没发到 npm）：

```js
import { KRouter } from "./sdk/js/index.js";
const a = await KRouter.local().ask("我们怎么发版？");   // 团队服务：KRouter.remote(url, { token })
console.log(a.page, a.how, a.refused);
```
