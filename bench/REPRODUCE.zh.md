# 复现这些数字

[English](REPRODUCE.md) · 每个数字和它的方法：[`docs/NUMBERS.zh.md`](../docs/NUMBERS.zh.md) · 登记与日志：[`HELDOUT.md`](memory_honesty/HELDOUT.md)

## 大约十秒，不用模型、不用 key、不用下载

```bash
git clone https://github.com/398894496-arch/KRouter && cd KRouter
python3 bench/reproduce.py
```

它重算 18 个已登记的数字（诚实基准在三个库上 KRouter 与 BM25、加两条规则的基线并排；claude-mem 和 basic-memory 存下来的原始回答重新评分；第 40 套的参考资料识别；第 45 套开发半、第 32 和 35 套留出半上的提示钩子单独），每一个都和登记当时写下的值并排打印，写明 `match` 还是 `MISMATCH`，以及它登记在哪里。只有每一行都一致，退出码才是 0。`--zh` 打印“一致 / 不一致”。没有任何东西离开这台机器，查询日志是关的，除临时文件夹外不写任何文件。出现 `MISMATCH` 时，先别相信任何一边：打开它写明的来源，带着两个数开一个 issue。

`python3 bench/reproduce.py --timing` 会在表之外另加这台机器上钩子在小基准库上的延迟：延迟取决于机器和负载，所以从不拿它和任何东西比（首页上的延迟是在一台同时还在跑别的活的笔记本上量的）。

在一台机器上（macOS、Python 3.14）从干净克隆跑过；Linux、Windows 没有跑过。

## 不在这张表里的

| 是什么 | 为什么不在表里 | 自己怎么跑 |
|---|---|---|
| LongMemEval 找到答案会话的数（第 7 套）和拒答规则在它 500 题上的数（第 14、37–39 套） | 不用模型，但数据集不在本仓库里，脚本也不下载 | 自己取 `longmemeval_s_cleaned.json`（许可证见脚本开头），然后 `python3 bench/longmemeval/lme.py convert --data …`、`run --system krouter`、`score` |
| LoCoMo（第 10、18 套） | 同上 | `python3 bench/locomo/locomo.py convert --data locomo10.json`、`run --system krouter`、`score` |
| LongMemEval **答题准确率**（第 11、12、22 套） | 要一个读者模型和一个评判模型 | `bench/longmemeval/qa.py prepare / judge-prepare / score`：脚本写出提示文件，你用自己的读者和评判模型跑完，把回复写回去。登记的那几次两边都用 Claude Sonnet 5.5（Claude Code 子代理）；第 22 套日志写的是约 410 次子代理运行、约 1500 万 token。换读者或评判，数就不同；日志写明了谁读了什么 |
| 整条链的拒答（第 41 套） | 要一个读者模型 | `bench/memory_honesty/endtoend.py`（开头列了步骤）；用量见第 41 套日志 |
| 下意识的**宿主层**（第 33 套、第 35 套宿主半、第 45 套补记：Sonnet 44/48、Haiku 42/48） | 要一个会去查的宿主模型 | `bench/subconscious/both.py prepare set45dev --work DIR`，用你的模型回答批次，再 `score`；登记的四次一共读写 478,381 个 token |
| 经验与技能（第 15–26 套）、真实会话（第 30、31 套） | 宿主模型，以及 Codex 或 Claude Code 的真实会话 | 各套在 `HELDOUT.md` 里的小节写明了脚本和跑了什么 |
| 十个人同时用（第 27 套）、半小时混合负载（第 28 套）、规模表、第 34 套的速度 | 几分钟到几小时的机器时间，而且是计时 | `bench/team/load.py`、`bench/scale/run.py`、`bench/subconscious/speed.py`（命令见 [`docs/TEAM.zh.md`](../docs/TEAM.zh.md) 和 [`docs/BENCHMARK.md`](../docs/BENCHMARK.md)） |
| 真实库上的参考资料自动识别（第 42 套） | 那个库是维护者自己的，没有公开 | 没有可跑的；方法写在 `HELDOUT.md` 里 |
| 第 45 套的留出半 | 有意封存 | 由维护者在开发半上得出结果后打开一次来确认 |

这些运行换算成钱我们没算过：取决于你选的模型。登记日志里数过 token 的，写了每次用了多少。

## 别的系统在“下意识”基准上

[`bench/subconscious/public/`](subconscious/public/README.zh.md)：一个很小的适配器接口（进去一条消息和库里的页面，出来递出的页面或者什么都没递），一个按登记数法计分的脚本，KRouter 钩子和朴素 BM25 基线两个适配器，以及十几行写出自己的适配器的说明。里面没有任何东西安装或调用别的项目的软件。
