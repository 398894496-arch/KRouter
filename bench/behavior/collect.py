#!/usr/bin/env python3
"""Fold a RECORD_DIR of record.json files into one results file (paths shortened), and print judge's counts.
    python3 collect.py SET.json RECORD_DIR OUT.json"""
import json
import re
import sys
from pathlib import Path

recs = []
for f in sorted(Path(sys.argv[2]).glob("*/record.json")):
    r = json.loads(f.read_text(encoding="utf-8"))
    text = json.dumps(r, ensure_ascii=False)
    r = json.loads(re.sub(r"/private/tmp/[^\s\"\\)]*?/(proj|mem)/", r"<run>/\1/", text))
    for c in r.get("calls", []):
        c["result"] = re.sub(r"/private/tmp/[^\s\"\\|]*", "<run>", c.get("result", ""))[:300]
    recs.append(json.loads(re.sub(r"/Users/fe1/[^\s\"\\']*?/skill/", "<repo>/skill/", json.dumps(r, ensure_ascii=False))))
Path(sys.argv[3]).write_text(json.dumps(recs, ensure_ascii=False, indent=1), encoding="utf-8")
print(len(recs), "records ->", sys.argv[3])
