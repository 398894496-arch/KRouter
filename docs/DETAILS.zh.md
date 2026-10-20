# KRouter 详细说明

<!-- krouter-status:start (source: docs/STATUS.zh.md; run scripts/sync_status.py) -->
> **`main` 的当前状态（最新发布版 v1.2.1，2026-10-20）：测过什么，没测过什么。** 一行安装拿到的是最新发布版；
> CHANGELOG.md 里「Unreleased」下的改动只在 `main` 上。给评估 agent 的全部事实和出处：
> [`docs/FOR-AGENTS.md`](https://github.com/398894496-arch/KRouter/blob/main/docs/FOR-AGENTS.md)。
> - **留出测评**（合成的 110 页库上 200 道从没调过分的题，*不是*真实流量）：KRouter 引错 26%，80 道库里答不了的题
>   拒答 47 道，120 道可答题答对 102 道。默认设置下 claude-mem 引错 64%、basic-memory 78%，分别答对 72 和 45 道；
>   两者都没有拒答机制。给 BM25 加上 KRouter 那两条规则（跳过已被取代的页、匹配太弱就拒答），它就和 KRouter 打平：
>   领先来自这两条规则默认开着，不是排序算法。
> - **新查询上的真实流量盲测**（[VERIFY.md](https://github.com/398894496-arch/KRouter/blob/main/docs/VERIFY.md) 第 4 层）：
>   还没跑，要等攒够 50 条新查询。
> - **留出题是谁写的：** claude.ai 里单独会话中的 Claude Opus，不是真人。真人写的一套在计划中。
> - **发版节奏：** 1.2.0（2026-10-19）比原定的 11-12 提前，是维护者的决定。之后小版本每周最多一个，补丁随时发；
>   `KROUTER_TAG` 可以固定版本。
> - **夜间任务：** 一行安装只装查询，什么都不问；加 `--ask` 才问要不要导入会话、开夜间任务。从 clone 手动跑 `install.sh`
>   会直接装（`KROUTER_NO_TIMER=1` 跳过）。查询从不出本机。
> - **夜间写入通道：** API key 通道本机不跑任何进程；grok（内核沙箱）和 claude（工具白名单）只能动库；Codex 能读整个账号、
>   只写库，所以只有你点名或设 `KROUTER_ALLOW_CODEX=1` 才用；其他 CLI 没有约束，不设 `KROUTER_ALLOW_UNCONFINED=1` 就不会被选用。对照表见 [SECURITY.md](https://github.com/398894496-arch/KRouter/blob/main/SECURITY.md)。
<!-- krouter-status:end -->

首页没写的都在这里：安装选项、什么会离开本机、证据、版本、夜间写手怎么工作、四个挂载、和常见 agent 记忆的对比。回到[首页](../README.zh.md)。

## 导入你已经有的东西

- **agent 会话**（`import_sessions.py`）：Claude Code、Codex 和 Cursor agent 的会话记录，每个会话每天一页，放在 `05 时间日志/会话摘录/`。只留你的提问和每轮最后的回答，先脱敏；工具输出、思考过程、注入的上下文、子 agent 和无头运行都不收。加 `--distill` 让模型写出「定了什么、改了什么」。`--consent` 之后，夜间任务每天导入前一天的会话；`--file 路径` 只导一个会话，插件的会话结束 hook 用的就是这个。
- **claude-mem**（`import_claude_mem.py`，已在 claude-mem 13.35.0 的真实安装上跑通）：按会话所在仓库的路径（claude-mem 的 `cwd`）区分项目；老版本没有这个字段，那些会话照样导入，但不会自动带进新会话。只读打开 `~/.claude-mem/claude-mem.db`。会话总结和记录写进 `05 时间日志/claude-mem/`；每个项目的「决定」汇成一页，放在 `02 经验与方法/从 claude-mem 导入/`，状态是 `status: candidate`。加 `--distill` 会把这些决定分成「还有效的」和「被取代的」。
- **会话 hook**（Claude Code 插件里的 `session_hook.py`）：会话结束时，在后台导入刚结束的这个会话；新会话开始时，带上这个仓库（按 git 根目录匹配，不按文件夹名）最近的至多 8 条决定，每条注明出处页。默认只带你确认过的页（`status: active` 或 `confirmed: true`）里的全部条目，加上其他页里的纠错条目，并标「待确认」。没同意之前两个都不做；`KROUTER_INJECT=all` 全部带上，`KROUTER_INJECT=0` 都不带。

## 安装 —— 一行，什么都不用懂

```bash
curl -fsSL https://raw.githubusercontent.com/398894496-arch/KRouter/main/scripts/bootstrap.sh | sh
```

Windows（PowerShell，不需要管理员）：

```powershell
irm https://raw.githubusercontent.com/398894496-arch/KRouter/main/scripts/bootstrap.ps1 | iex
```

它会下载最新发布版（tag，永远不是 `main`），先按 release 里的 `SHA256SUMS` 核对 SHA-256，再在 `文稿/第二大脑` 建一座库（系统语言是中文就用中文模板），装好路由器和 agent 规则，并在 Obsidian 里打开这座库。默认到此为止：只装查询，什么都不问，没有内容离开本机。加 `--ask` 才会问要不要导入最近的 agent 会话、要不要装夜间任务，并用一句话说清：会用哪个 CLI、以什么权限运行，每晚会发出多少页、多少 token——数字来自在新库上的一次预演。没有终端可问就当不要；`--timer`、`--import` 表示事先同意。升级时保留你以前同意过的。想固定在某个版本：`… | KROUTER_TAG=v1.2.1 sh`（Windows 先设 `$env:KROUTER_TAG`）。已有的库（`… | sh -s -- --vault ~/MyVault`）一个文件都不动，只补缺失的骨架文件。同一行再跑一次就是升级。唯一的前提是 Python 3（Windows 脚本缺 Python 时会用 winget 自动装）。最后一行会告诉你还剩哪一步：登录一个 AI 编程工具，或者贴一个 API key。之后不需要维护任何东西——锁名词只是可选的快捷方式，不是前提；召回自己就能按页面标题和正文答，答不了就直说，不硬猜。哪天晚上的活没干成，会弹桌面通知说明原因。数据去向、CLI 写入器能看到什么：[`SECURITY.md`](../SECURITY.md)。

## 什么会离开本机，要花多少

- **查询从不外发。** 查找全在本地：一个 SQLite 全文缓存加 Python 标准库，每次约 110 ms。
- **夜间任务会把库里的文字发给一个模型**——你登录的那个 AI 编程工具（花你的订阅额度），或你给的 API key。发出去的是：昨天的日志（用来蒸馏）、规则页和主题页（用来预先算答案）、和各个主题相关的片段、路由器没答好的问题。`extras/host-daily-evolution/run.sh --dry-run` 会先列出要发什么、多少 token，什么都不发。`KROUTER_NIGHTLY=0` 关掉夜间步骤。
- **夜间写手受限运行；API key 通道在本机什么都不运行。** grok 在内核沙箱里跑（只能碰知识库和路由器）；claude 的工具被限定为读写知识库、运行路由器；Codex 能读你的账户，其他 CLI 什么都能碰——安装时的提示会说清你选的是哪种。细节：[`SECURITY.md`](../SECURITY.md)。
- **key 从不放在库里，也从不外发、从不打印。** 贴在钥匙页上的 key 下次运行会挪进 `~/.dsh-krouter-keys.env`（权限 600）。名字或标记表明是机密的页（凭据、密钥、credential、secret、password，或 `secret: true`）从不外发、从不引用；其他地方像 key 的文字一律显示为 `<redacted>`。
- **花费**：自带模板第一晚约 4,000 token；有一百来个规则页和主题页的库约 16 万 token。之后每晚只重做改过的页。用订阅的 CLI，花的是额度不是钱。

## 备份你的库

库的 git 历史（如果有）能撤回一次改坏，但扛不住硬盘坏了、电脑丢了，或者勒索软件把整个文件夹加密。要防这些，得有一份放在别处的副本，而且是真的恢复过的副本。`backup.py` 就做这件事；不给它指定文件夹，它就不运行。

```bash
python3 ~/.agents/skills/krouter-obsidian/scripts/backup.py init --dir "<一个会同步到别处的文件夹>"
# 把 ~/.dsh-krouter-keys.env 里的 KROUTER_BACKUP_PASSPHRASE 复制进密码管理器，然后：
python3 ~/.agents/skills/krouter-obsidian/scripts/backup.py saved
```

之后夜间任务每晚写一个备份包，并且先把它重新打开验一遍，验过了才算数。连续三天没有一次恢复成功，或者密码还只存在这台电脑上，`status` 都会说出来，你的 agent 也就会告诉你。为什么这样设计：

- **写进文件夹，不接云接口。** 指向 iCloud 云盘（`~/Library/Mobile Documents/com~apple~CloudDocs/…`）、OneDrive、Dropbox、Google 或百度网盘的同步文件夹、移动硬盘或 NAS 都行。账号、重试、版本这些事，它们的客户端本来就会处理，KRouter 不碰任何一家。每个备份包先写完整再改名放进去，之后不再改动，同步客户端不会上传半个文件，也不会把两个版本合在一起。
- **两个地方比一个可靠。** `KROUTER_BACKUP_DIR` 可以写多个文件夹，用 `|` 隔开（比如一个云盘文件夹加一块移动硬盘）。每处各写一个包、各验一遍，一处失败不影响另一处。
- **不要拿云盘直接同步正在用的库，也不要把库明文推到 git 托管站**，私有仓库也不行。两台电脑同时写的时候，同步客户端会把 `.git` 弄坏；而且库里常有带 token 的插件设置（KRouter 扫了一个真实的库，历史里就有四个这样的文件）。备份包是整个文件夹连同 `.git` 一起加密。
- **一律加密，一律验证。** 用 `openssl` 做 AES-256 加密（PBKDF2，60 万轮），整个文件再加 HMAC 校验，损坏或被改过在解密前就能发现。之后做一次完整的试恢复：页数和清单对得上，历史过得了 `git fsck`。没有不加密的选项。
- **密码是唯一的命门。** 它存在钥匙文件里，在库外面，所以不会被打进备份包。如果电脑和密码一起丢了，备份就打不开了，所以一定要在密码管理器里也存一份。
- **按规则保留：** 最新 7 个，再加最近 4 周、6 个月里每周、每月各最新的一个。
- **链接还是链接。** 空文件夹会还原；软链接还原后指向原来的位置。但它指向的库外内容不在备份包里：每次备份都会报告 `links_outside`（有几个链接指向库外），那些文件夹要另外备份。
- **恢复不依赖 KRouter。** 用 `backup.py restore <备份包> --into <新文件夹>`（从不覆盖已有文件夹）；或者在任何装了 openssl 和 tar 的电脑上手动恢复：
  `openssl enc -d -aes-256-cbc -pbkdf2 -iter 600000 -md sha256 -in <备份包> -out vault.tar.gz && tar -xzf vault.tar.gz`。
- **自己亲手试一次。** `backup.py verify --latest` 会在临时文件夹里打开最新的备份，什么都不改；再真的 `restore` 到一个新文件夹一次，用 Obsidian 打开看看。

## 证据一览

| 证明什么 | 结果 | 怎么读 |
|---|---|---|
| 锁按协议写的工作 | 模板上 25/25 个主题、39/39 个别名、0 冲突 | 穷举，clone 下来可复现（CI） |
| 锁对比近邻检索 | TF-IDF、MiniLM、BGE-M3 会硬凑隔壁页的地方，锁会拒 | 冻结回放，可复现（CI） |
| 召回宁可拒答也不硬猜 | 英文模板：离题和半离题拒答 12/12。中文模板：6/6 和 5/6，正确页排第一 9/12——清空别名表也一样 | 公开基准，可复现（CI） |
| 真实流量（作者的库） | 92 个真实路由查询盲评：0.62 → 1.47（满分 2，≤0.5.1 → 0.9.0） | **开发集**——剩余的失败就是在这些查询上逐条分析的。留出合成集上自 0.6 起持平（88% / 75% → 88% / 71%）。新查询攒够 50 条后再盲评（不早于 2026-10-20） |
| 问答卡 | 同一批 92 条消融：看不出收益（±0.05） | 等新查询的实测结果再定，可能改为默认关闭 |

方法、细节和还没解决的：[`docs/VERIFY.md`](VERIFY.md)。

## 稳定性与版本

1.x 遵循语义化版本。下面这些是稳定的，只在大版本里改，而且附迁移办法：库的目录结构和区名文件、别名表格式、agent 读的回执字段（`retrieval_status`、`canonical_match`、`canonical_source`、`recall:`、`how`、`host_action`）、各个路由、MCP 工具 `krouter_ask` / `krouter_status`、`KROUTER_*` 环境变量，以及导入器写的页面标记（`source: krouter-import`、`source: krouter-claude-mem`）。小版本可以加步骤和选项，也可以调打分；每次调打分都要在公开基准上附改动前后的数字（[`CONTRIBUTING.md`](../CONTRIBUTING.md)）。新功能的小版本最多一周一个，修复类的补丁版本修好就发。一行安装取的是最新**发布版**，从不取 `main`；要固定在某个版本，见上面的 `KROUTER_TAG`。[`CHANGELOG.md`](../CHANGELOG.md) 写明改了什么、为什么改，包括外部评审发现了什么。

## 你的 Agent 会忘。这套系统把它写下来。

聊天不是记忆。人和人要记的东西不一样，所以**没有任何第二大脑会在 clone 里装着别人的笔记**——这套也不会。你下载的是操作系统：骨架、路由、每天自动蒸馏的写入器。你的名词、项目、纠错，用过之后才长出来。

**自动记住 = 每天封账、蒸馏，写进库里。** 不是上一句下一轮立刻灌回去。五道门过了，当天自动写成准经验（`provisional`），不问。正式经验（`active`）下次同类任务再问你。

检索先试一道可选的别名锁（一个短名词 → 那一页 + 双 SHA-256）；大多数问题对不上它，由排序召回来答。别名表不用维护：自带一份样例，只有想把某个短名词固定到某一页时才值得加一行。排序召回会——规则页优先，附一句为这个问题预先算好的 `answer (generated):`；库里没有一页覆盖得了，就给 `recall: none`。没有向量库要养。打不中那一页，进化就没发生。

```mermaid
flowchart LR
  L1[L1 封当天] --> L2[L2 蒸馏]
  L2 --> L3[L3 两步晋升]
  L3 --> L4[L4 夜间整合]
  L4 --> L5[L5 打到那一页]
```

| 层 | 做什么 | 不许做什么 |
|---|---|---|
| L1 日志 | `05` 一天一篇 | 把流水账当成可复用方法 |
| L2 蒸馏 | 蒸馏。摘要不能代替原文 | 自动写成 `active` |
| L3 晋升 | 五道门过了 → **当天自动 `provisional`**。下次同类先问。采纳且该次验收 → `active` | 自动写成 `active`。门过了还不写准经验 |
| L4 整合 | 夜间：反复出现的主题 → 一页带出处的主题档案；每个规则页/主题页 3–5 张问答卡；从路由器自己没答好的问题里学触发词；体检页列出失效项 | 照抄权威页、页面改了还用旧卡、编造说法、改动来源页 |
| L5 锁 + 召回 | 短名词 → 那一页 + 双 SHA。未命中 → 在可重建的 FTS5 缓存上排序召回，附 `answer (generated):`；覆盖不足 → `recall: none`。进程内约 30 ms，每次命令行调用约 110 ms（`python3`，只用标准库） | 向量回退、引用隔壁、猜 |

完整规则：[`PROTOCOL.md`](../PROTOCOL.md) · [`docs/ARCHITECTURE.md`](ARCHITECTURE.md) · [`docs/VERIFY.md`](VERIFY.md)

## 证据细节（四层，不要混）

拆开写。总账：[`docs/VERIFY.md`](VERIFY.md)。

### 1. 实现正确性 — 代码做了协议写的那件事

对本仓 `template/` 别名表穷举：**25/25** 主题、**39/39** 别名、**0** 冲突。这是查完表，不是抽样，也不证明「算法聪明」。

别名锁这一层的改写不变量：整句改写 **25/25** 不会触发别名锁（设计如此，不会把整句当 AND）；列出的短名词 **25/25** 打到金标页。没触发别名锁的改写会继续走排序召回：在 200 道留出题上，120 道可答题答对 102 道，大多数和页面用词不同。这是实现正确性。**这不是五次新会话 LLM 盲测。** `template/` 是干净的最小样例——下限，不是私库的实际难度。

```bash
python3 tests/fixtures/clone_25/run.py
python3 -m pytest -q tests/test_clone_25.py
```

[`tests/fixtures/clone_25/`](../tests/fixtures/clone_25/)。`verify_canonical_map.py` 验的是**你的**库，**复现不了**作者历史上的 26/26 · 156/156。

### 2. 对照优势 — 锁 vs 词法 TF-IDF、MiniLM、BGE-M3

四句话拆开。**N=36**（正命中 16、取代 4、近邻 4、负查询 12）。MiniLM 和 BGE-M3 **做过和 `tfidf_map` 同一套余弦地板扫描**。`matches_lock` = 正命中全对 **且** 负查询全拒 **且** 假近邻 0。

- **结论 A（已封）：** 不知情的 TF-IDF 打到失效发版页。同一套 `invalid_at` 过滤之后，余弦在取代切片上和锁打平——那是元数据，不是排序。
- **结论 B（词法 TF-IDF）：** 6 道 CJK 改写分数低于 12 道负查询里最强的那道。没有 TF-IDF 阈值能对齐锁。
- **结论 C（MiniLM，轻量级）：** 精度问题，不是阈值问题。未设阈值时 `H15` 发版已经打到封账页，不是发版页——阈值只能丢掉匹配，不能把错页改对。中文改写不再倒挂（这点和 TF-IDF 不同）。重放 `dense_vectors.json`（冻结向量，不是现场下模型）。
- **结论 D（BGE-M3，中量级向量）：** 临界失手，卡在一道近邻题。发版答对；正命中 16/16。阈值 0.40：16/16 命中，12 道毫不相干负查询（N01–N12）全拒；剩下的是近邻切片 `B03` 生产事故 → 定时器页（不是那 12 道里的一道）。阈值 0.45：假近邻清零，掉一道真命中。没有对齐锁的操作点。重放 `dense_m3_vectors.json`。在这个合同上（没有就空着、不许引用隔壁），羽量级打过这套中量级——这就是「比主流上了 embedding 的 RAG 更好」。重量级（混合 + rerank）不打：体重不对，不是欠的一场。

现场重放（`python3` + `rg`）：clone_25 和词法/TF-IDF 行。向量两行：带指纹的 JSON，不是「陌生人自己再跑一遍编码器」。

```bash
python3 tests/fixtures/lock_vs_neighbor/run.py
python3 -m pytest -q tests/test_lock_vs_neighbor.py
```

[`tests/fixtures/lock_vs_neighbor/`](../tests/fixtures/lock_vs_neighbor/) · [`docs/LOCK_VS_NEIGHBOR.md`](LOCK_VS_NEIGHBOR.md)。不是 LongMemEval。

### 3. 实战自陈 — 不在本仓

作者活库 2026-08-21：连续封账 72 天；30 条真实任务；LLM 25/25；26/26 主题、156/156 别名。**本仓不含验证材料。** 不是回执。要量**你的**表，跑 `python3 scripts/verify_canonical_map.py --map … --vault …`。要数**你的**封账天数和缺口，跑 `python3 scripts/verify_sealed_days.py --vault …`。那不验证作者的 72 天。

### 4. 真实流量 — 不在本仓

前三层用的都是有人为测试写的题。这一层用的是作者的 agent 真实发给路由器的问题：30 天 Codex / Claude Code / Cursor 会话里去重后的 92 条（全部调用里一半是重复提问）。每条分别过旧路由和新路由，两份输出随机打乱成 X / Y，由 LLM 评判各打 0（没用）/ 1（相关但还得翻）/ 2（直接答到）。同样的输出重评，均分会有约 ±0.05 的波动，差距小于 0.1 当作噪声。

| 版本 | 改了什么 | 均分（满分 2） | 直接答到 | 没用 |
|---|---|---|---|---|
| ≤ 0.5.1 | 锁 + 整句字面 grep | 0.62 | 14 | 49 |
| 0.9.0 | + L1 召回、范围扩大、自学习触发词、主题档案、问答卡 | **1.47** | **55** | **12** |

同一轮、同样 92 条。各版本两两对比和合成独立题：[`docs/VERIFY.md`](VERIFY.md)。

## 十五分钟 — 在自带 template 上拿到回执

这段只证明锁能在**本仓 `template/`** 上打到 `Q01`，不是在你已有的库上。不蒸馏昨天。不需要 GPU、Docker、嵌入进程。`first_run.sh` 故意不继承 `OBSIDIAN_VAULT`；要换一棵树，设 `KROUTER_FIRST_RUN_VAULT`。

```bash
git clone https://github.com/398894496-arch/KRouter.git
cd KRouter
python3 -m venv .venv && . .venv/bin/activate
python3 -m pip install -r requirements.txt
./scripts/first_run.sh
```

每次路由都给回执，调用方能分清「权威」和「猜的」：

```
retrieval_status: canonical-match
canonical_source: /YourVault/Agent第二大脑.md
canonical_id: Q01
source_verified_at: 2026-01-01
source_sha256: d8c1d5af…
canonical_map_sha256: c55b8715…
canonical_match: true
```

CI 每次 push 跑 pytest（含 clone_25、lock-vs-neighbor、召回基准、封账天数）、这支脚本、DSH 桥。查询时不联网；夜间步骤会把页面发给你的模型（见文末要告诉宿主的事）。

未命中就是未命中：`canonical_match: false` 加提示。`suggest homz` 只给**提示**，不是命中。换一个名词，或者往别名表加一行——就是你库里的 `90 系统文件/canonical_sources.psv`：

```
Q11|deploy;deployment;怎么发版|02 经验与方法/发布/发布流程.md|只从 main 发
```

## 打开每天的写入器

这就是产品。`install.sh` 会装上夜间任务（`KROUTER_NO_TIMER=1` 跳过）；一行安装默认不装，`--ask` 时先问你。

把 `template/` 拷到你的库，然后：

```bash
export OBSIDIAN_VAULT=/path/to/YourVault
./scripts/install.sh            # 以后升级：./scripts/install.sh --upgrade · 卸载：./scripts/uninstall.sh
```

别名表是你的，放在**库里**（`90 系统文件/canonical_sources.psv`），跟着库同步，升级不会动它；安装只在第一次放进十个样例名词，之后再也不碰。开始写自己的名词时，`python3 ~/.agents/skills/krouter-obsidian/scripts/propose_aliases.py` 会从你的库里起草候选，写到 `90 系统文件/自动化/别名候选.md`——勾上要的行，再加 `--apply` 运行。没勾的一行都不会进表。建议固定在某个发布 tag，不要直接跟 `main`。

**先 API key：** key 只存在 `~/.dsh-krouter-keys.env`（权限 600），永不留在库里。贴在 [`90 系统文件/自动化/自进化钥匙.md`](../template-zh/90%20系统文件/自动化/自进化钥匙.md) 也行——下一次运行会把它挪进那个文件，页面上留一句说明——因为库里的东西 CLI 写入器读得到，库同步到哪儿它就跟到哪儿。写入器锁定该家旗舰模型，蒸馏并写准经验。

**没有 key：** 用已经登录的 CLI 做同一件事——`grok`、官方 Codex、`claude`、`cursor-agent`、`opencode`、`kimi`、`pi`、`vibe`、`antigravity`，夜间步骤认的是同一份名单。没有第二份 env。不要用 PATH 上的 `agent`。文件：[`extras/host-daily-evolution/`](../extras/host-daily-evolution/)。

- 五道门过了 → **当天自动写 `provisional`**
- 正式 `active` 不自动：下次同类先问，采纳且该次验收才升
- 失败就留待总结，不许空过一天
- 封账之后同一个定时器接着跑夜间维护（见 **锁之后**）；`KROUTER_NIGHTLY=0` 关掉。`extras/host-daily-evolution/run.sh --dry-run` 先列出会发什么、写什么，不调模型
- 定时器：macOS 用 launchd（日志在 `~/Library/Logs/dsh-krouter-daily.log`）；Linux 用 systemd 用户定时器，没有 systemd 就写一行带标记的 crontab；Windows 用计划任务（`scripts/install_windows_task.ps1`）
- **先**把 `OBSIDIAN_VAULT` 指到那座库再跑 `install.sh`，否则不挂定时器
- `dsh plugin add` 是挂载，不是这个写入器。`lamp: unused` 是你把定时器关了

装到 `~/.agents/skills/krouter-obsidian`、`~/.cursor/rules/krouter-obsidian.mdc`、`~/.cursor/rules/ask-product.mdc`。Cursor 规则先跑 `status`，收据里有 `host_action` **必须告诉宿主**。若 `~/.agents/skills/krouter-obsidian` 已在，不带 `--upgrade`（与 `--force` 相同）会 exit 1；两者都只换代码，别名表、台账和软链原样保留。`uninstall.sh` 删掉定时器、Cursor 规则、hook 和 skill，别名表还没进库的先救进库，库本身不动（先用 `--dry-run` 看；`--purge` 另外清掉可重建的缓存和查询日志）。不会覆盖正在用的 `obsidian-knowledge-router`。定时器钉死本仓库的 `krouter-obsidian`。问的匹配器是 L3：一句最多一条准经验；`record` 不写 `active`；采纳且该次验收后 `promote` 才升正式。触发词是你自己的，写在准经验页或 `ask-triggers.json`。Codex / Claude 仍要贴 [`extras/codex/AGENTS.snippet.md`](../extras/codex/AGENTS.snippet.md)。

本机已登录 CLI 时的订阅通道：grok 在内核沙箱 `krouter` 里运行（只碰知识库和路由器），claude 用 `--permission-mode dontAsk` 加白名单（知识库和路由器），Codex `exec --sandbox workspace-write`。见 [`SECURITY.md`](../SECURITY.md)。

## 什么情况不该装

- 你需要**语义**检索（靠向量理解意思）。召回是按词的（词、中文双字、触发词）：能找到不少换了说法的问题，也会漏一些（留出题里可答题答对 102/120）。本地向量目前只在开发分支上。
- 笔记以英文为主，又不打算换掉中文样例名词。目录名可以配置：库根目录放一个 `krouter-zones.psv`，把默认布局映射到你的（`90 系统文件|System`、`Agent第二大脑.md|Home.md`）。DSH 桥仍按默认目录名。
- 你想要聊天自动灌下一轮，或云记忆 API。

## 四个挂载，一座库

共享的是库——别名表就在库里——不是第二套协议。Windows 走 `route_knowledge.py`（同一套路由）；DSH 在 win32 上优先用它。

| 挂载 | 仓库里有什么 |
|---|---|
| Cursor | `install.sh` → `extras/cursor/krouter-obsidian.mdc` |
| Codex | `extras/codex/AGENTS.snippet.md` |
| Claude Code | `extras/claude-code/CLAUDE.snippet.md` |
| DeepSeek Harness | DSH 插座。克隆后：`dsh plugin add /path/to/this/repo`。目录：`dsh plugin --profile web add github:398894496-arch/KRouter`。只读工具，含 **correction**；`memory` 是库内路由，不是聊天记忆。卸插件不删库 |

```bash
node extras/dsh/test-bridge.mjs
dsh plugin --profile web add github:398894496-arch/KRouter
```

需要 `python3`、`rg`、PyYAML。测试：`python3 -m pip install -r requirements-dev.txt && python3 -m pytest -q`。

## 锁之后：召回、主题档案、问答卡、夜间维护

锁仍然单独裁决——只有 `canonical_sources.psv` 里的行能认领一页，来源被标成 superseded / retired / rejected 就失效。下面这些只负责排序、拒答，或写 `provisional` 的机器页。

- **L1 召回**（`recall_index.py`）。未命中时从 `~/.cache/krouter/` 下的 SQLite FTS5 缓存里答（只用标准库，无服务、无向量；删掉约 2 秒重建）。中文切双字、英文切词；规则页优先，已取代的页下沉；一个词的查询（`DSH`）直接落到同名页。覆盖不足就给 `recall: none`。单页路由（`preference`、`correction`）找不到会扩到全库，并标 `scope_widened`。
- **主题档案**（`consolidate_topics.py`）。`90 系统文件/自动化/主题档案清单.psv` 里列的主题，从日志整合成 `02 经验与方法/主题档案/主题｜…md`：每条事实带出处，权威页只链接不照抄，证据变了才重写。问题点到这个主题时才给它加权。
- **问答卡**（`answer_cards.py`）。每个规则页/主题页 3–5 张「问题 → 一句话答案」，答案只取自该页、绑定该页内容哈希；路由器把最贴近的一张作为 `answer (generated):` 给出。卡要过两道才算数。词面一道，写卡、建索引、读卡时都查：答案里的每个数字、路径、命令、英文词都在原页作为完整词出现（`3` 不算出现在 `30` 里），答案用词大多来自原页，问题至少有一个实词在原页出现。然后是模型第二遍，每张卡核一次：问题是不是在问这一页，答案是不是答了这个问题，有没有说反或添加。只靠词面拦不住半离题的问题、张冠李戴的答案、说反的句子；在作者库上造了 160 张这样的卡，第二遍全部拦下，真卡一张没误杀。没通过的卡、页面改过的旧卡，既不参与排序也不给答案；像密钥的内容进不了库。依据是页面，不是卡片。
- **夜间维护**。`reconsolidate.py` 读路由器自己的查询日志（`~/.local/state/krouter/`），让模型把没答好的问题对到召回候选里的某一页，或判 none——学到的是触发词，不是锁。`checkup.py`（不调模型）生成 `90 系统文件/自动化/下意识体检.md`：失效的锁和触发词、取代后召回仍偏旧页的、60 天没人用过的规则页。

日更封账后，自带定时器运行 `nightly.py`：`compile_subconscious.py` → `reconsolidate.py` → `consolidate_topics.py` → `answer_cards.py` → `checkup.py`。每步独立，都不改变封账本身的退出码；`KROUTER_NIGHTLY=0` 关掉。每一步的结果——跑了、跳过、部分失败还是失败，原因，走的哪条模型通道，调了几次、发出去多少字——写进 `90 系统文件/自动化/夜间维护.md` 和健康页；`status` 会读出来，步骤被跳过、失败或三天没跑时打印 `host_action`。需要模型的步骤和写入器走同一条通道：厂商表、旗舰锁、CLI 名单都只有一份，在 `llm.py`，写入器从这里导入。先 `*_API_KEY`，顺序与写入器相同（DeepSeek、OpenAI、Anthropic……Gemini），模型取 `KROUTER_LEARN_MODEL`，否则取厂商模型目录里的旗舰；再用写入器会选的那个 CLI；`KROUTER_LEARN_CLI` 是宿主特意指定的 CLI，排第一。`checkup.py` 还会列出过期、对不上原文、问题离页、未经核对、问题过宽的问答卡。测试：`tests/test_recall_index.py`、`tests/test_api_lane.py`、`tests/test_install_nightly.py`、`tests/test_zones.py`、`tests/test_recall_bench.py`。

## 不是 Mem0，不是笔记软件

![clone 时是操作系统；两周后装着你封的日子、你的名词、你采纳的方法](img/fills-up.svg)

| | 这套操作系统 | 常见 Agent 记忆 |
|---|---|---|
| clone 里有什么 | 协议 + 骨架 + 路由 + 写入器 | 同样是空仓库 |
| 过完好的一天 | 蒸馏；五道门过了当天自动 `provisional`；下次先问 → 可能 `active` | 把会话压缩了下次灌进提示词 |
| 过完一次纠错 | 改权威页。下次必须打开它 | 重新嵌入，盼着旧块自己烂掉 |
| 怎么找到那一页 | 按词排序召回，覆盖不足就拒答；可选的别名锁能把短名词固定到某一页 | 语义近邻 |
| 一个主题反复出现好几周 | 夜间整合成一页带出处的主题档案 | 碎片散在各个会话里 |
| 同一个问题又问一遍 | 确定地给同一页和它的 `how`；有合适的核对过的问答卡就附上 | 重新检索、重新读 |
| 你要养什么 | 你的名词和主题清单。没有向量库 | 索引、同步、注入、过期 |

想要把整段聊天自动灌进下一轮（装了 Claude Code 插件后，新会话会带上这个仓库最多 8 条记下的决定，不是聊天本身）、云记忆 API、或语义近邻，跳过。见 **什么情况不该装**。
