---
title: "Lesson: When dates are off by one or break after midnight, check time zones first"
type: experience-card
status: provisional
card_id: C10
when: off by one day; after midnight; wrong date
source_ref: "[[05 时间日志/会话摘录/example C10]]"
date: 2026-01-01
source: krouter-bench
---

# Lesson: When dates are off by one or break after midnight, check time zones first

- Situation: The daily report kept missing the last few hours of each day
- Action: The server cut days in UTC while the users were in UTC+8
- Result: Cutting days in local time made the numbers match
- Lesson: When dates are off by one day or things break after midnight, first check who cuts the day in which time zone
- When: off by one day; after midnight; wrong date
- Source: [[05 时间日志/会话摘录/example C10]] (public bench example, written by hand, not a real session)
