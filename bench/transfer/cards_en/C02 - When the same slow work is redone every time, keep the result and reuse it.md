---
title: "Lesson: When the same slow work is redone every time, keep the result and reuse it"
type: experience-card
status: provisional
card_id: C02
when: every time from scratch; downloads it again; waiting too long
source_ref: "[[05 时间日志/会话摘录/example C02]]"
date: 2026-01-01
source: krouter-bench
---

# Lesson: When the same slow work is redone every time, keep the result and reuse it

- Situation: Every CI build downloaded all dependencies again; each run took 12 minutes
- Action: Cached the dependency directory keyed on the lockfile hash
- Result: Builds dropped to 3 minutes
- Lesson: When the same slow step is redone from scratch every time, store its result and reuse it while the inputs have not changed
- When: every time from scratch; downloads it again; waiting too long
- Source: [[05 时间日志/会话摘录/example C02]] (public bench example, written by hand, not a real session)
