# Conversation backend (milestone 4)

`sadaf.conversation` provides a standalone async text backend. It receives a
conversation store, optional `MemoryStore`, project context loader, provider,
and tool runtime through its constructor. Importing the module opens no files,
clients, devices, or network connections.

`ContextBuilder` assembles distinct persona, global profile, evidence-backed
memory, mandatory project rules, selected project sections, durable thread
summary, exact recent turns, commitments, task state, source references, and
revalidation flags. Character budgets are allocated by section. Required rules
must fit their reserved allocation in full or preparation fails. Memory entries
include fact IDs and source episode/turn references; sensitive and non-exportable
facts are excluded by the `memory_context` adapter. Project task preparation is
refreshed through `ProjectContextLoader`, which uses milestone 3's fail-closed
policy checks. A thread's first project is pinned; switching projects requires
a new thread ID.

`SQLiteConversationStore` persists exact user/assistant turns separately from
the clearly labeled, unverified summary. The host may store commitments and may
inject a summarizer. Summarization runs only after a configured turn threshold;
it is not an additional rewrite on each turn. `compact` keeps an even number of
exact turns so exchanges are not split. Summarizer failure does not fail a reply.
The host is responsible for reviewing summary quality and managing retention.

`OpenRouterProvider` uses the official Chat Completions endpoint and keeps all
conversation state locally. Its payload includes only model, messages, tools
when present, and stream mode; it does not send `store`, `previous_response_id`,
or generic sampling/reasoning settings. Supported default model capabilities are
declared for `openai/gpt-6.1-sol` and `openai/gpt-6-luna`; unknown models need an
explicit capability declaration. Retries are bounded, and a fallback model is
used only when configured. Calls are synchronous at the HTTP transport layer
and moved to a worker thread for async completion. SSE output is normalized to
text, finish reason, and usage events. A model's account access still depends
on the configured OpenRouter account and was not live-tested here.

Tools are advertised from validated JSON schemas, run asynchronously or in a
worker thread, and return structured success/error observations. Iteration
exhaustion returns and stores an explicit incomplete result. The explicit
`legacy_tool_specs()` adapter maps the existing registry's model-facing fields
to the handlers' actual signatures and imports handlers only when called. The
camera handler is blocked unless the host injects and grants a confirmation
callback. It is not installed by default; hosts choose which tools to expose.
Timed-out synchronous calls cannot be forcibly stopped once their worker thread
has begun, so side-effecting tools should also enforce their own deadlines.

The opt-in live check is `sadaf --no-dotenv live-smoke --confirm-live` after
configuring `OPENROUTER_API_KEY` and `SADAF_REASONING_PROVIDER=openrouter` (or
use normal dotenv loading). It sends one fixed synthetic text request with no
tools, memory, project data, or personal input. It is a connectivity smoke, not
a quality evaluation. No live request was made for milestone 4.

## OpenRouter references checked for this implementation

- [Chat Completions API](https://openrouter.ai/docs/api/api-reference/chat/create-a-chat-completion): endpoint, request/response, and streaming format.
- [Tool calling guide](https://openrouter.ai/docs/guides/features/tool-calling): normalized tool-call loop and capability filtering.
- [GPT-6.1 Sol](https://openrouter.ai/openai/gpt-6.1-sol/providers): selected reasoning model slug and current model details.
- [GPT-6 Luna](https://openrouter.ai/openai/gpt-6-luna): selected extraction model; model page documents function calling.

Provider/account access, live tool behavior, context usefulness, and model
quality remain unverified. The backend is not wired into the legacy voice loop;
voice, extraction, and actual M2 dispatch remain later milestones.
