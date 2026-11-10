---
title: "Lesson: When a problem comes and goes, pin down its conditions first"
type: experience-card
status: provisional
card_id: C04
when: fails now and then; works sometimes; cannot reproduce it
source_ref: "[[05 时间日志/会话摘录/example C04]]"
date: 2026-01-01
source: krouter-bench
---

# Lesson: When a problem comes and goes, pin down its conditions first

- Situation: An integration test failed once or twice in ten runs and always passed locally
- Action: Logged the random seed, the concurrency and the time; with the seed fixed it failed every time
- Result: Once reproducible, it was fixed in half an hour
- Lesson: When a problem happens only sometimes, do not start changing things: record the inputs and the environment each time until you find conditions that reproduce it reliably
- When: fails now and then; works sometimes; cannot reproduce it
- Source: [[05 时间日志/会话摘录/example C04]] (public bench example, written by hand, not a real session)
