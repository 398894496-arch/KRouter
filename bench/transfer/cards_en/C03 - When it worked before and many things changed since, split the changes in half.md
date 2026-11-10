---
title: "Lesson: When it worked before and many things changed since, split the changes in half"
type: experience-card
status: provisional
card_id: C03
when: it used to work; suddenly broken; no idea which change did it
source_ref: "[[05 时间日志/会话摘录/example C03]]"
date: 2026-01-01
source: krouter-bench
---

# Lesson: When it worked before and many things changed since, split the changes in half

- Situation: A test broke after a dependency upgrade; 40 commits since it last passed
- Action: Used git bisect to halve the range; found the bad commit in 6 steps
- Result: Much faster than reading the commits one by one
- Lesson: When something used to work, now does not, and a lot changed in between, do not guess one change at a time: split the changes in half, test, and keep halving the broken half
- When: it used to work; suddenly broken; no idea which change did it
- Source: [[05 时间日志/会话摘录/example C03]] (public bench example, written by hand, not a real session)
