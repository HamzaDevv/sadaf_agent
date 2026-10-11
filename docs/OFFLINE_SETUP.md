# Offline foundation (milestone 1)

The supported foundation runtime is CPython 3.13; `.python-version` selects
3.13.3. The legacy README installation instructions describe the earlier voice
application. Use this setup for development. `main.py` remains the legacy app;
`python -m sadaf` is the safe foundation entry point.

## Reproducible installation

With uv installed and Python 3.13 available:

```sh
uv sync --locked
uv run --frozen python -m sadaf doctor
uv run --frozen python -m sadaf text --message "Synthetic setup probe"
uv run --frozen python -m pytest -q
```

`uv.lock` pins the full dependency resolution. Setup may download packages;
doctor, text, and tests themselves need no network, hardware, or credentials.
After installation, use `.venv/bin/python` directly (or `uv run --offline
--frozen ...`). Default dependencies contain only the settings-file reader;
the default dev group adds pytest and pytest-asyncio. No provider SDK, audio driver, or vector
store is imported by the foundation.

Optional `providers`, `audio`, and `vector` extras have bounded constraints and
locked versions. Install only when the corresponding integration is needed:
`uv sync --locked --extra vector`. Audio may require PortAudio/system build
tools. Resolution does not establish hardware or live-service compatibility.
These extras are not a complete replacement for the legacy tools dependency
list in `requirements.txt`.

The graph code imports `google.genai`, which is supplied by `google-genai`,
not `google-generativeai`; the vector extra and legacy requirements now use
the matching SDK. See the [official SDK](https://github.com/googleapis/python-genai).

## Configuration and safety

`.env.example` contains placeholders only. Keep existing `.env` and keys;
copy the example only for a fresh checkout. `load_settings()` reads `.env`
from its explicit root (CLI: current working directory), then overlays process
environment values. It does not search parent directories or mutate the process
environment. Tests pass explicit mappings or use sanitized subprocesses.

Reasoning and extraction each accept `fake` or `openrouter`; voice accepts
`disabled`, `fake`, or `openai`; embeddings accept `disabled`, `fake`, or
`google`. Enabled roles require a model; configured live roles also require
their matching key. Model IDs remain configurable, with no live default or
claim that a model is available. Doctor validates configuration without making
requests; it never reports credential presence as verified live capability.
Text mode requires all roles to be offline and always identifies fake output.
It uses an injected provider and turn store with ephemeral, isolated history.
It performs no extraction, M2 submission, voice capture, or durable writes.

Data defaults to ignored `.sadaf-dev/`, with separate profile/persona paths.
Configuration rejects legacy/data overlap and symlink escapes. No directories,
profiles, or databases are created by doctor or text mode. `SADAF_M2_ENDPOINT`
is optional; its HTTP(S) URL is validated without inventing or contacting an
API. URL credentials/query/fragment are rejected. There is no M2 adapter yet.
Secrets are excluded from settings representations and diagnostics.

Default `python -m pytest` collects only `tests_offline/` and uses
`--confcutdir=tests_offline` to avoid the legacy root `conftest.py`, which
imports the live proxy. The offline suite blocks network connection attempts
and checks imports, configuration, injected history, failure handling, and
synthetic legacy-data preservation. For additional certainty or tool-driven
collection, pass `-c pytest.ini --confcutdir=tests_offline tests_offline`.
Legacy tests require a separate explicit review; they are not part of the
safe default test run.

## Legacy graph and migration hazard

Do not start `main.py`, instantiate `memory.graph_store.MemoryGraphStore`,
or run `scripts/migrate_memory.py` to inspect personal data. Construction opens
Chroma and an embedding client; `get_all_nodes()` invokes lazy pruning that can
archive nodes, delete vector entries, and write graph/archive files during a
read. The legacy migration passes an outdated multi-argument `upsert_node`
signature and can partially modify a store before failing. Atomic JSON rename
also does not prevent lost updates from concurrent writers.

Milestone 2 will implement transactional, side-effect-free reads and a
backup-aware, dry-run, idempotent migration into a separate target. Until then,
use copied synthetic fixtures only; the real memory directory has not been
opened or migrated by this milestone.
