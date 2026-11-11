---
title: "Lesson: Before an action you cannot undo, keep a copy you can restore"
type: experience-card
status: provisional
card_id: C06
when: delete it; overwrite; wipe; cannot undo
source_ref: "[[05 时间日志/会话摘录/example C06]]"
date: 2026-01-01
source: krouter-bench
---

# Lesson: Before an action you cannot undo, keep a copy you can restore

- Situation: About to drop a production table that seemed unused
- Action: Exported the whole table and its schema first, then dropped it
- Result: A report still read it the next day; restored in ten minutes
- Lesson: Before deleting, overwriting or wiping anything that cannot be undone, keep a copy you can restore exactly
- When: delete it; overwrite; wipe; cannot undo
- Source: [[05 时间日志/会话摘录/example C06]] (public bench example, written by hand, not a real session)
