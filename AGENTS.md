# Working on Sadaf

Before implementing changes, read `.project-state/README.md`,
`.project-state/STATUS.md`, and `.project-state/HANDOFF.md`. Read the roadmap
and decisions when relevant to the task. Inspect current Git status; the
baseline in `.project-state/EXISTING_WORK.md` records earlier unfinished work.
User instructions take precedence over these repository instructions.

At the end of a work session, update status and handoff with actual changes,
verification, remaining issues, and the next concrete step. Append meaningful
milestones to the session log and accepted architecture decisions to decisions.
Do not mark planned or simulated functionality as implemented or live-tested.

Preserve unrelated changes. Never put secrets, personal memories, raw
conversations, or credentials in development state. Use offline fixtures by
default. Do not start the legacy memory store or migrate real memories merely
to inspect the code: its reads can prune data. Stage explicit files/hunks when
committing; do not stage the entire dirty checkout.
