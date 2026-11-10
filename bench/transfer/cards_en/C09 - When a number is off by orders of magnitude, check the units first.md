---
title: "Lesson: When a number is off by orders of magnitude, check the units first"
type: experience-card
status: provisional
card_id: C09
when: off by a thousand; way too big; way too small; units
source_ref: "[[05 时间日志/会话摘录/example C09]]"
date: 2026-01-01
source: krouter-bench
---

# Lesson: When a number is off by orders of magnitude, check the units first

- Situation: A request timeout was set to 30 and every request timed out at once
- Action: The docs said the parameter is in milliseconds, not seconds
- Result: Set to 30000, it worked
- Lesson: When a result is absurdly large or small, off by hundreds or thousands of times, check the units and defaults before the logic
- When: off by a thousand; way too big; way too small; units
- Source: [[05 时间日志/会话摘录/example C09]] (public bench example, written by hand, not a real session)
