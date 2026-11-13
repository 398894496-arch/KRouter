"""Rebuild the speed vault of sets 34, 39 and 45: bench/scale/gen.py 10000 plus 2,000 alias rows and trigger lines (seeded).
The original build script of set 34 is not in the repository, so this is a reconstruction (three trigger phrases a page).

    python3 bench/subconscious/mk_v10k.py REPO_ROOT OUT_DIR"""
import random, re, subprocess, sys
from pathlib import Path
REPO = Path(sys.argv[1]); root = Path(sys.argv[2])
subprocess.run([sys.executable, str(REPO / "bench/scale/gen.py"), "10000", str(root)], check=True, capture_output=True)
rnd = random.Random(10000)
pages = sorted(p for p in root.rglob("*.md") if "｜" in p.name)
(root / "90 系统文件/自动化").mkdir(parents=True, exist_ok=True)
rows, trig = [], []
hit = None
for i, p in enumerate(pages):
    rel = str(p.relative_to(root)).replace("\\", "/")
    title = p.stem
    words = re.findall(r"[一-鿿]{2}|[A-Za-z]{3,}", title)
    if i % 5 == 0 and len(rows) < 2000:
        name = f"代号{i:05d}"
        rows.append(f"S{len(rows):04d}|{name}|{rel}|{title} 的结论")
        if hit is None and i > 1000:
            hit = f"{name} 这边 {title.split('｜')[0]} 怎么处理的"
    trig.append(f"{rel}|{';'.join([f'{title.split(chr(0xff5c))[0]}{w}怎么办' for w in words[:2]] + [f'{title.split(chr(0xff5c))[0]}的做法'])}")
(root / "90 系统文件/canonical_sources.psv").write_text("\n".join(rows) + "\n", encoding="utf-8")
(root / "90 系统文件/自动化/下意识触发词.psv").write_text("\n".join(trig) + "\n", encoding="utf-8")
print(len(pages), "pages", len(rows), "alias rows", len(trig), "trigger lines")
print("HIT", hit)
