# Local project context (milestone 3)

`sadaf.projects` is an offline library. It opens nothing on import and is not
wired into the legacy voice loop, a provider, a cloud service, or M2. Use explicit
application authorization when constructing the registry and its adapter map.
Never grant a context root containing real legacy memories for development.

## Registration and use

Create an independent registry SQLite database, explicitly allow context roots,
then register a user-scoped project ID, context root, repository reference, and
owner. `initialize_project(root)` creates seven missing Markdown templates and
preserves existing files. Roots must already exist. Registered context roots
cannot overlap, even across users; organization policies have their own roots
and can be attached to multiple projects within a user scope.

```python
from pathlib import Path
from sadaf.projects import (
    LocalMarkdownSource, ProjectContext, ProjectRegistry, initialize_project,
)

# All paths below refer to synthetic, separately authorized development data.
base = Path('/tmp/sadaf-synthetic-project')
root = base / 'context'
root.mkdir(parents=True, exist_ok=True)
initialize_project(root)
registry = ProjectRegistry(base / 'registry.sqlite', authorized_roots=(root,))
registry.register_project('fixture-user', 'demo', context_root=root,
                          repository='fixture://demo', owner='fixture-owner')
source = LocalMarkdownSource(root, base / 'revisions.sqlite')
context = ProjectContext({('fixture-user', 'demo'): source})
snapshot = registry.activate('fixture-user', 'thread', 'demo', context)
packet = context.prepare_dispatch(registry, user_id='fixture-user',
                                  project_id=snapshot.project_id,
                                  keywords=('interfaces',),
                                  global_preferences={'tone': 'concise'})
# Future orchestration pins packet.snapshot to the task. It must handle blockers.
source.close()
registry.close()
```

Registration and actor authentication are host-application responsibilities.
This is a local trusted library, not a multi-user security service. The source
map is an injected capability keyed by user and source identity. Local adapters
must match registered roots. Nonlocal adapters must enforce the same identity
boundary against their actual service contract; the test fake uses opaque
revisions and has no network API.

## Authority and context

Registry metadata assigns owner and authority; text cannot promote itself.
Organization `POLICIES.md` and project `POLICIES.md` are mandatory and retained
in full. Every context document carries project ID, source ID, content revision,
owner, trust classification, and verification status. Known project documents
are knowledge, `WORKING_STYLE.md` is style, and additional Markdown is untrusted.
Quoted source content stays separate from binding rules.

Machine-checkable policies use `- MUST key = value`, outside fenced examples.
Different values for the same key block activation and preparation, including
organization/project conflicts. Malformed MUST entries block too. Agreeing rules
retain all source/revision references. Prose is binding context and is retained
without truncation, but the library cannot prove semantic consistency of prose
or equivalence between differently worded keys. These require owner review.
An empty initial policy template means no declared rules; creating a template
does not establish that an owner has approved the project's real policy set.

Working preferences use `- key = value`: project style overlays the supplied
global preferences; keyed mandatory rules constrain both. This library neither
reads personal memory nor exports it to an execution service. Existing scoped
memory APIs remain separate. Knowledge retrieval selects matching Markdown
sections only within this project's snapshot; empty search terms select none.
Full policy text has a reserved character budget (default 16,000); overflow
raises `PolicyBlocked` instead of silently truncating. This is not a tokenizer
budget. Token allocation belongs in milestone 4's context builder.

## Revisions, updates, and unavailable context

The document-source protocol exposes list/revision manifests, exact revision
reads, and expected-revision updates. Local revisions are SHA-256 of file bytes;
a separate SQLite archive retains observed versions for historical reads.
Direct-child Markdown only is allowed; path traversal and file/root symlinks
are rejected. Archive data is project context, not development handoff data;
keep it in an authorized runtime location and manage retention separately.

Refresh double-collects all manifests around exact revision reads, with three
attempts before blocking unstable context. Activation stores selection only
after successful policy checks. `prepare_dispatch` always refreshes and uses an
explicit original project ID. A cached snapshot older than 60 seconds, a missing
policy, an unavailable source, an unverified policy, a conflict, or oversized
policies blocks governed preparation. No stale cache or empty-policy fallback
is used. Multi-source coherence is optimistic; there is no cross-service atomic
transaction and a source may change after verification.

`update_document` requires the registered owner as an authenticated actor, a
nonempty reason, and the expected revision. Conversation/extraction has no
automatic write route. The caller must authenticate the actor independently;
an actor string is not a credential. Updating an organization policy affects
all attached projects. The local adapter uses an advisory flock and unique
fsynced temporary file with atomic replacement. Cooperating writers serialize;
external edits detected before replacement raise `RevisionConflict`. Editors
that ignore the lock can still race the final replace; local files cannot offer
a universal server-side compare-and-swap guarantee. File mode becomes private
on replacement. Revisions retain content, not a full actor/reason audit log.

`revalidate(registry, pinned_snapshot)` returns `policy_changed_requires_revalidation`,
`project_context_changed`, `required_context_unavailable`, or an empty tuple.
The future task orchestrator must act on these flags before continuing governed
work. It must never redirect a running task when the user's active project
changes. No running task engine, automatic pause, cloud sync, or M2 dispatch is
implemented by this milestone. Close registry and local source connections
explicitly when done. The local lock adapter currently targets Unix/macOS.
