#!/usr/bin/env python3
"""A synthetic vault for the scale bench: the bundled template plus N generated pages (decisions with dates).

    python3 bench/scale/gen.py 10000 /tmp/v10000

The pages are random but reproducible (seeded by N); nothing here resembles a real vault's content.
"""

import random
import shutil
import sys
from pathlib import Path

ZH = ("发版 流程 封面 标题 规则 客户 报价 合同 部署 服务器 端口 数据库 备份 视频 剪辑 字幕 口播 选题 预算 采购 接口 鉴权 缓存 "
      "日志 告警 测试 上线 回滚 团队 周会 招聘 培训 文档 设计 配色 字体 品牌 渠道 投放 预算 复盘").split()
EN = ("release deploy cover title rule client quote contract server port database backup video caption script budget "
      "api auth cache log alert test rollback team meeting hiring design color font brand channel campaign review "
      "incident").split()
DIRS = ["01 项目", "02 经验与方法", "03 资料与证据", "04 已完成与复盘", "05 时间日志/2026-10"]


def main() -> int:
    n, root = int(sys.argv[1]), Path(sys.argv[2])
    random.seed(n)
    if not root.exists():
        shutil.copytree(Path(__file__).resolve().parents[2] / "template", root)
    for i in range(n):
        folder = root / DIRS[i % len(DIRS)]
        folder.mkdir(parents=True, exist_ok=True)
        w = random.sample(ZH, 3) + random.sample(EN, 2)
        title = f"{w[0]}{w[1]}｜{w[3]} {w[4]} {i}"
        lines = [f"- {random.choice(ZH)}{random.choice(ZH)}用 {random.choice(EN)} {random.randint(1, 999)}，"
                 f"{random.choice(ZH)}改成{random.choice(ZH)}（{random.randint(1, 28)} 日）"
                 for _ in range(random.randint(6, 14))]
        body = "\n".join(lines)
        (folder / f"{title}.md").write_text(f"---\ntitle: {title}\nstatus: active\n---\n\n# {title}\n\n{body}\n",
                                            encoding="utf-8")
    print(n, "pages")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
