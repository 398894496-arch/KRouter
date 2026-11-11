---
title: "Lesson: When a change has no effect, check which copy is actually read"
type: experience-card
status: provisional
card_id: C01
when: changed it but nothing happened; still the old behaviour; the edit did not take
source_ref: "[[05 时间日志/会话摘录/example C01]]"
date: 2026-01-01
source: krouter-bench
---

# Lesson: When a change has no effect, check which copy is actually read

- Situation: Changed nginx's server_name and reloaded several times; nothing changed
- Action: Ran nginx -T to see the loaded config: it was reading another file with the same name under /etc/nginx/conf.d
- Result: Deleting that old file made the change take effect at once
- Lesson: When a change has no effect, first make sure the system actually reads the copy you changed, before doubting the change itself
- When: changed it but nothing happened; still the old behaviour; the edit did not take
- Source: [[05 时间日志/会话摘录/example C01]] (public bench example, written by hand, not a real session)
