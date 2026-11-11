# 路线图

English: [`ROADMAP.md`](ROADMAP.md) · 回到 [README](README.zh.md)

下一步打算做的事，不分先后，不写日期：这里没有一条是承诺，一条只有在发布、并且 [`CHANGELOG.md`](CHANGELOG.md) 里写明之后才会划掉。现在还做不到的，写在 README 的[它不会做什么](README.zh.md#它不会做什么)里。

- **改进拒答的判据。** 问的是记忆里某件事的近邻时，它还是会作答。拒答门槛分析过两次，没有找到能胜过它的规则：第 14 套在 LongMemEval 上，第 37 套在 LongMemEval、LoCoMo 和自家各组上试了 216 条覆盖类规则，可答题最多掉 1 个百分点时最好的只多拒 3 道（[`NUMBERS.zh.md`](docs/NUMBERS.zh.md)）；需要另一类信号。
- **参加一场公开的同台评测。** 加入别人组织的对比，用不是我们出的题。
- **装完一键回填全部历史。** 一条命令把全部历史导进来、分批提炼，而不是默认只做最新的 40 个。
- **会话结束时学习。** 由会话结束的钩子触发学习这一步，不再依赖 agent 自己去调用工具（真实会话里它几乎不调）。
- **跨语言查找。** 用一种语言提问，查到用另一种语言写的页。
- **可选的本地语义层。** 本地向量检索测过，没有上线（[`DENSE-OPTIN.md`](docs/DENSE-OPTIN.md)）；问题是能不能加上它而不丢掉拒答。
- **发到 PyPI 和 npm。** 发布 Python 包（含 LangGraph 的存储）和 JavaScript 客户端。
- **Windows 手工实测。** 在一台真的 Windows 机器上装一遍、接上应用跑一遍；目前只有 CI 里跑过测试。

## 已完成

- **把知识库做成明确的一层**（2.1.0，未发布）：`krouter kb add` 声明参考资料文件夹，回执单列 `knowledge_base:`、不影响置信度，只有资料对得上时第一行写 `memory: none`；`krouter kb suggest` 建议，`krouter kb import` 导入 PDF、Word、HTML（[`CHANGELOG.md`](CHANGELOG.md)）。
