# M2 task protocol (offline implementation)

`sadaf.tasks` defines typed task requests, durable receipts/events, and the
`M2Client` semantic protocol. The protocol intentionally contains no URLs,
HTTP methods, payload assumptions, or service-specific status mapping. No M2
repository or API contract was available during implementation. `FakeM2Client`
is the only included client.

A `TaskRequest` pins user, project, thread, repository/worktree, dependencies,
policy source revisions, decisions, outcome/scope, acceptance criteria, allowed
actions, result requirements, idempotency key, and any explicitly permitted
personal context. The host remains responsible for selecting only context the
user permits. Request snapshots and every receipt change are stored in SQLite
transactions by `SQLiteTaskStore`.

`TaskOrchestrator` limits active work, queues mutations to the same repository
and worktree, waits for dependencies, and blocks dependents after failed or
cancelled prerequisites. Idempotency keys return the existing receipt only
when the complete request matches. Reconciliation queries existing remote run
IDs and submits queued unsent work; the client contract must honor the key too
when a real adapter is eventually added. Cancellation acceptance remains
`cancel_requested` until a later status confirms `cancelled`. A successful
status without a retrievable result, or without a complete result and concrete
artifacts or validation evidence, is downgraded to failure. Partial results
remain stored with their errors and are not reported as successful.

Policy/context refresh code can pass revalidation flags to
`TaskOrchestrator.revalidate`; the saved request keeps its original project and
policy revisions even if the active conversation changes projects. Speech
interruption is outside this task API and cannot cancel work implicitly.

The fake exposes explicit controls to advance, await input, finish, fail, and
confirm cancellation. Offline tests use temporary databases and never contact
M2 or a provider. A real adapter remains blocked on a supplied contract.
