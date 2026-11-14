# “提一句就想起来”的公开基准

[English](README.md) · 登记与日志：[`HELDOUT.md` 第 45 套](../../memory_honesty/HELDOUT.md) · 所有不需要模型的已登记数字，一条命令对表：[`bench/reproduce.py`](../../reproduce.py)

给一个系统一条消息和一个小知识库，它回答“递出了哪几页”，或者“没出声”。这个基准只问这一件事。不需要模型、不需要 key、不联网，计分脚本是纯 Python。

| | |
|---|---|
| 知识库 | 110 页：60 页现行手册（英文 30、中文 30，主题大体平行）、30 页被取代的旧页（每种语言 15 页，各在其新页旁边）、20 页日志当干扰。就是 [`bench/memory_honesty/vault3`](../../memory_honesty/vault3)。 |
| 消息 | 120 条**编出来的**口语消息（[第 45 套](../../memory_honesty/HELDOUT.md)的开发半），由两个全新的 Claude Sonnet 5.5 子代理只看页面清单写成：48 条提到某一页（其中 42 条没说出页面叫什么）、24 条说的是改过的规则（旧页不能来）、48 条不该有任何动作（六类：无关、同名另一个意思、常用词、粘贴的文本、同领域但库里没有的事、一句“好的”）。第 32、35 套（各 60 条）套得进同一个接口：`--cases set32dev` / `set35dev`。 |
| 计分 | **想起**（期望的页在递出的页里）、**改主意**（新页递出，递出旧页不算对）、**安静时出声**（该安静的消息拿到了任何页）、**错页**（想起或改主意消息里递出的其他页）、**旧页**（递出了被取代的页）。数法就是登记的那一套，没改，和 `bench/subconscious/run.py` 是同一段计分代码。 |

```bash
python3 bench/subconscious/public/score.py --adapter krouter-hook              # KRouter 的提示钩子单独
python3 bench/subconscious/public/score.py --adapter bm25-naive --opt live_only=1 --opt floor=22
python3 bench/subconscious/public/score.py --adapter my_adapter.py --cases set35dev --show
python3 bench/subconscious/public/score.py --adapter bm25-naive --sweep floor=0,10,20,30   # 每个取值一行
```

## 给别的系统写适配器（十几行）

适配器是一个 Python 文件，两个函数。`setup` 带着页面调用一次；`handle` 每条消息调用一次，返回这个系统递出的页面路径（空列表 = 没出声）：

```python
# my_adapter.py：消息里含有某页标题就递出那一页（故意写得很笨的系统）
PAGES = []

def setup(pages, **options):                # pages: [{"path", "title", "text", "status", "names"}, ...]
    PAGES[:] = [p for p in pages if p["status"] != "superseded"]

def handle(message):                        # -> ["Handbook/Status page.md"] 或 []
    return [p["path"] for p in PAGES if p["title"].lower() in message.lower()][:1]
```

`status` 为 `superseded` 表示这页已被新页取代（页首也写着）；`names` 是团队给这页列的名字（KRouter 的别名表，适配器可以用也可以不用）；`--opt key=value` 会作为关键字参数传给 `setup`；可选的 `close()` 在结束时调用。计分脚本会检查 `handle` 返回的是字符串列表，并把不是期望页的任何路径算作错页。

**不是 Python？** `score.py --export DIR` 写出 `DIR/pages.jsonl` 和 `DIR/messages.jsonl`（只有消息文本和编号，不含期望答案）。每条消息写一行 `{"id": "...", "pages": ["Handbook/X.md"]}`（安静就写空列表），再跑 `score.py --answers answers.jsonl`。

自带的两个适配器不安装、不调用任何别家的系统，这里也不报别家的数。如果你用适配器跑了别的记忆系统，请写明怎么配置的、给了它什么；下表只是这两个自带适配器的参照。

## 两个自带适配器的得分（开发半，用上面的命令重算）

| 第 45 套开发半，120 条 | 想起（共 48） | 改主意（共 24） | 安静时出声（共 48） | 错页 | 旧页 |
|---|---|---|---|---|---|
| **`krouter-hook`**：提示钩子对每条消息做的查找（别名表和触发词在任何案例之前写好，加全文召回；不用模型） | **7**（42 条没说页名的里 1 条） | **7** | **2** | **0** | **0** |
| `bm25-naive`，永远回答（所有页，每条消息给第一名） | 16 | 11 | 42 | 41 | 3 |
| `bm25-naive`，只用现行页，永远回答 | 17 | 13 | 42 | 38 | 0 |
| `bm25-naive`，只用现行页，门槛 22（在第 35 套开发半上选择分最高） | 4 | 4 | 2 | 2 | 0 |
| `bm25-naive`，只用现行页，加上页面名字，门槛 24（同一规则） | 5 | 5 | 1 | 1 | 0 |

第 35 套开发半（24 想起、12 改主意、24 安静）：`krouter-hook` 6 / 2 / 2 / 0 / 0；四行 BM25 依次 10 / 1 / 23 / 24 / 8、10 / 8 / 23 / 17 / 0、2 / 1 / 0 / 0 / 0、3 / 1 / 0 / 0 / 0。第 32 套开发半：`krouter-hook` 5 / 5 / 0 / 0 / 0；BM25 依次 9 / 1 / 23 / 26 / 7、8 / 5 / 23 / 23 / 0、0 / 1 / 0 / 3 / 0、0 / 1 / 0 / 2 / 0。

**怎么读。**每条都回答的关键词匹配比钩子想起得多（48 条里 16–17 条，钩子 7 条），同时对 48 条该保持安静的消息里 42 条也点了某一页：这个基准看的既是找得到页，也是别乱出声。调到和钩子一样安静时（门槛在第 35 套上选，不在第 45 套上选），朴素 BM25 落在同一个低区间（48 条里 4–5 条，钩子 7；出声 1–2 条，钩子 2）：钩子领先几条，只有 48 和 24 条样本，没有区间（钩子的阈值是在第 32 套开发半上定的，从没在第 45 套上定过）。这和我们别处说的一致：**钩子单独安静、但找到的少**；把整条链抬上去的（这一半上 Sonnet 5.5 44/48、Haiku 5.5 42/48）是会话开始时的常驻索引加上宿主模型自己去取，那需要模型，不在这个基准里。换一个门槛、分词或案例集，BM25 的几行就会动。

## 不在这里的，和原因

- **宿主层**（会话开始的索引加一个会去查的模型：[第 45 套补记](../../memory_honesty/HELDOUT.md)里的 44/48、42/48、38/48）需要模型。用你自己的模型跑：`python3 bench/subconscious/both.py prepare set45dev --work DIR` 写出提示批次；用你要测的宿主模型把每一项回答到 `DIR/replies_<host>.jsonl`；`both.py score --work DIR --host <host>` 计分。登记的那几次用的是 Claude Code 子代理加指定模型；四次一共读写 478,381 个 token。换一个宿主模型，数就不同。
- **第 45 套的留出半**（120 条）保持封存。`score.py` 够不到它（`--cases set45held` 会被拒绝），`reproduce.py` 里也不跑，由维护者在开发半上得出结果之后打开一次来确认。针对开发半调过的系统，不能说明它在留出半上的表现。
- **真实消息。**这里每一条都是编的，出自同一个模型家族，对着一个小库。它说明一个系统在这类口语消息上的行为，不是对任何人真实使用的估计。库里每页手册有中英两份，所以取了正确页的另一种语言的对应页，会被算错（对英文偏悲观）。
- **速度。**`python3 bench/reproduce.py --timing` 单独打印这台机器上的钩子延迟。
