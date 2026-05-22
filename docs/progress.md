# Progress Tracker

## M1: Chatbot with Personality

- [x] Repo scaffolded
- [x] Personality system prompt defined
- [x] Personality upgraded — real Ming persona (mined from brain repo)
- [x] PII scrubbed from persona (no location, no employer name, no family details)
- [x] LLM wrapper (OpenAI)
- [x] Multi-provider support (6 providers: azure-openai, openai, groq, together, openrouter, ollama)
- [x] Async LLM calls (AsyncOpenAI / AsyncAzureOpenAI)
- [x] Switched to Azure OpenAI GPT-5.2
- [x] In-memory conversation history
- [x] FastAPI web server
- [x] Input validation (4k char max, empty choices guard, HTTP error check)
- [x] Chat UI (dark theme, message bubbles)
- [x] README with run instructions
- [x] Git repo initialized
- [x] Local testing with API key
- [x] Screenshot for README

## M2: Voice Output (TTS)

- [x] TTS integration (Azure OpenAI tts deployment — separate resource in northcentralus)
- [x] Audio playback in standalone chat UI (mute toggle + replay button)
- [x] Audio playback in SolidJS widget (mute toggle + replay button)
- [ ] WebSocket streaming (deferred to M4)

## M3: Voice Input (STT)

> References: `neuro-ming/comms/2026-05-09-summary.md` (voice memo), `specs/m3-m4-pipecat-voice.md` (Tend code study)

**Decision (2026-05-21, post Tend code study): Do NOT add Pipecat for M3.**
Pipecat's `LocalAudioTransport` assumes Pi/desktop, not browser. Browser audio via WebSocket + raw STT is simpler and gets M3 done faster. Pipecat evaluated for M5+ standalone desktop build.

Tend reference (`~/code/playground/tend`) is still the architectural blueprint — port patterns, not the framework.

- [ ] `core/stt.py` — Deepgram primary (streaming, 100ms), Azure STT fallback, Whisper offline
- [ ] `web/audio_router.py` — WebSocket `/ws/voice` endpoint, PCM 16kHz mono buffering
- [ ] Push-to-talk in browser UI (hold space = record, release = send)
- [ ] Wire STT transcript → existing `core/llm.py` chat path (no new LLM code needed)
- [ ] TTS spike: ElevenLabs vs current Azure nova (same sentence, pick by ear)
- [ ] `.env.example`: add `STT_PROVIDER`, `DEEPGRAM_API_KEY`, `STT_ENABLED=false`
- [ ] Verify `/chat` text endpoint unchanged (no regression)

## M4: Conversational Loop (Two-Tier Brain + Workers)

> References: `neuro-ming/comms/2026-05-09-summary.md`, `specs/m3-m4-pipecat-voice.md`

**Architecture:** Fast shell (Haiku, <300ms) stays always-on. Heavy tasks spawn async Claude CLI workers that bill against subscription (not API tokens — key billing trick from Tend). ProactiveAnnouncer delivers results via TTS even while shell is idle.

```
User Voice
    │
    ▼
STT (Deepgram)          fast, streaming
    │
    ▼
Fast Shell (Haiku)      low latency conversational shell
    │   ├── simple reply → TTS → voice out
    └── do_task() tool call
                │
           AsyncTaskBus (asyncio.Queue)
                │
        Claude CLI worker (Opus, subprocess, subscription billing)
                │
            result → ProactiveAnnouncer
                │
        TTS announce (even if user is silent)
        + append to LLM context (next turn knows)
```

**Key insight from Tend:** Workers never set `ANTHROPIC_API_KEY` in subprocess env — Claude CLI falls back to its own OAuth credentials (`~/.claude/.credentials.json`), billing the user's Claude subscription instead of per-token API. This makes Opus workers nearly free for personal use.

- [ ] `core/bus.py` — minimal `asyncio.Queue` task bus (`enqueue`, `on_complete`, `subscribe`)
- [ ] `workers/claude_cli.py` — ported from Tend; CLAUDE_CLI_CLEAR_ENV (30+ vars), ClaudeRunSpec, subprocess spawn
- [ ] `core/announcer.py` — ported from Tend; cooldown 300s/category, defer-while-active, drain_pending, context append
- [ ] `core/llm.py` — add `do_task(request: str)` tool, model split: Haiku shell / Opus workers
- [ ] Queue+announce UX: immediate ack ("on it"), async TTS announce on completion
- [ ] Parallel workers: multiple `do_task` calls run concurrently, each posts to bus independently
- [ ] Worker timeout + error handling (default 120s, spoken fallback on failure)
- [ ] Browser "working..." indicator, clears on announce

## M5: Persona Eval Harness

> Borrowed from `azure/aistudio-copilot-sample` (eval-as-code) + Azure-Samples Customer Assist (Azure AI Evaluation SDK shape). Catch persona drift before M3+ stack more layers.

- [ ] `core/eval/` package — ground truth YAML + grader + runner
- [ ] 15-20 ground-truth questions across 4+ life domains, PII-scrubbed
- [ ] LLM-as-judge with deterministic banned-phrase check (sourced from anti-AI-voice rules)
- [ ] Markdown + JSON reports under `reports/eval/`, baseline committed
- [ ] CI exit code based on aggregate score >= 4.0
- [ ] **Foundry decision point** — evaluate upgrading `ai-mingz-dev` (Azure OpenAI) → Foundry resource to unlock Azure AI Evaluation SDK + auto-tracing. Upgrade is in-place (endpoint + keys preserved). See [`brain/cheatsheets/azure-ai-foundry-patterns.md`](../../../brain/cheatsheets/azure-ai-foundry-patterns.md). Decision criteria: if rolling our own grader is &lt;200 lines, stay on plain AOAI; if we want continuous eval / XPIA testing / cluster analysis, upgrade.
- [ ] **OTel GenAI semconv on telemetry** — when wiring App Insights, use standard span attributes (`gen_ai.system`, `gen_ai.request.model`, `gen_ai.response.id`, `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`). Free Foundry compatibility — same KQL works post-upgrade.

See queued task: `~/code/brain/copilot/delegate/queue/2026-04-19-neuro-ming-m5-eval-harness.md`

## M6: Conversation Simulator

> Borrowed from Azure-Samples `Solution_Accelerators/Advanced_RAG` (synthetic-conversation simulator) + Market Research Analyst (persona-aware queries). Drives the M5 harness over multi-turn flows so memory + persona stability are tested, not just one-shots.

- [ ] Synthetic user-turn generator (persona-archetype seeded — curious dev, frustrated tenant, casual chat)
- [ ] Multi-turn driver: feeds simulator turns → neuro-ming `core/llm.py` → captures responses
- [ ] Plug results into M5 grader for trait-stability scoring across turns
- [ ] Dialog scenarios stored as YAML, replayable

## M7: Safety Guardrails

> Borrowed from Azure-Samples Customer Assist + Sales Analyst (Azure AI Content Safety as input/output filter). Public VTuber surface = mandatory before M8 hosted.

- [ ] Input filter (block prompt injection / harmful asks) before reaching `core/llm.py`
- [ ] Output filter (block harmful generations) before TTS / response
- [ ] Per-category thresholds in config (hate, violence, self-harm, sexual)
- [ ] Bypass for trusted local sessions (env-gated)
- [ ] **Foundry Content Safety SDK** — use `azure-ai-contentsafety` for input + output filtering. Single SDK call (~30 lines). Per-category severity thresholds (0–7). Works against plain Azure OpenAI today; auto-included if/when Foundry-resource upgrade happens. See [`brain/cheatsheets/azure-ai-foundry-patterns.md`](../../../brain/cheatsheets/azure-ai-foundry-patterns.md).

## M8: Hosted Deployment

> Borrowed from Azure-Samples `azure.yaml` + `azd` template shape. One-command deploy; same infra story as Advanced_RAG.

- [ ] `azure.yaml` for `azd up`
- [ ] Bicep for App Service / Container App + Azure OpenAI references via Key Vault
- [ ] Custom domain + HTTPS
- [ ] Persistent session store (replaces in-process M1 store — see M11)

## M9: Observability + Pre-launch Red Team

> Borrowed from every Azure-Samples agent sample: Application Insights + Custom Telemetry from day 1, not bolted on later. Worker-center mirrors this same gap.

- [ ] Application Insights wiring (request, dependency, exception) using **OTel GenAI semantic conventions** (`gen_ai.system`, `gen_ai.request.model`, `gen_ai.response.id`, `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`) — free Foundry compatibility, same KQL works post-upgrade
- [ ] Custom events: per-turn latency, model used, token counts, cost estimate
- [ ] Trace ID correlation across LLM calls + TTS
- [ ] Dashboard JSON committed under `infra/dashboards/`
- [ ] **Foundry AI Red Teaming Agent** — before public launch (mingz.dev `ChatWidget` exposed), run automated red-team scans: prompt injection, XPIA (cross-prompt injection through pasted URLs), policy violations. Requires Foundry resource upgrade or one-shot Foundry project alongside `ai-mingz-dev`. Document attacks caught + mitigations applied. See [`brain/cheatsheets/azure-ai-foundry-patterns.md`](../../../brain/cheatsheets/azure-ai-foundry-patterns.md) (Control Plane section).

## M10: Bring-Your-Own-LLM Routing

> Borrowed from Azure-Samples Customer Assist ("Bring Your Own LLM" — task-aware routing). neuro-ming already has 6 providers; missing piece is per-task model selection (cheap for retrieval/embedding, smart for response).

- [ ] Routing config: `{task: model}` map (e.g., `embed: text-embedding-3-small`, `respond: gpt-5.2`, `judge: gpt-5.2`, `summarize: gpt-5-mini`)
- [ ] `core/llm.py` accepts task hint, picks provider+model
- [ ] Cost telemetry per task (feeds M9)

## M11: Persistent Session Store

> Drops the M1 in-process `Memory` class. Required before M12 — can't learn across sessions if sessions die with the process.

- [ ] Pick backend (sqlite local, Cosmos / Postgres for hosted)
- [ ] Schema: sessions, turns, metadata
- [ ] Backfill `core/memory.py` interface — same `add_message` / `get_messages` surface
- [ ] TTL / cleanup policy

## M12: Learning & Memory (RAG)

> Borrowed heavily from Azure-Samples `Advanced_RAG` (metadata-enriched chunks, ingestion service) + Market Research Analyst (Report Comparator, persona-aware queries) + Customer Assist (memory as evaluable artifact).

- [ ] **Metadata-enriched memory units** — store `{role, content, topic, entities, mood, timestamp, ref_ids}`, not raw `{role, content}`. Embed enriched text.
- [ ] **Ingestion service** — distill conversation history into structured "session reports" (Market Research Analyst Report Generator pattern)
- [ ] **Report Comparator** — diff new sessions vs old, surface drift / growth / recurring topics
- [ ] **Persona-aware retrieval** — queries reflect active persona facets, not raw user text
- [ ] **Domain-specific search skill** — bias retrieval toward identity-relevant chunks (vs generic semantic match)
- [ ] Vector store: Azure AI Search (hosted) or sqlite-vec (local)
- [ ] Eval coverage in M5 harness for memory recall + persona consistency under retrieval
- [ ] **Foundry IQ exploration** — evaluate Foundry IQ as the knowledge base for grounding agent answers in `~/code/brain/` (citations included). Privacy gate: must exclude `family/`, `tax/`, `property/`, `crna/secrets/`, `1on1/` before any ingestion. If shipped, becomes the "talk to Ming's external brain" portfolio piece. Decision deferred to M12 review.
- [ ] **Fine-tune small model on Ming voice (stretch)** — if prompt-engineering hits a ceiling on persona drift, evaluate fine-tuning Llama/Phi-1B on blog posts + commits + Teams history via Foundry. Only if M5 grader shows score plateau under retrieval. Otherwise skip — not worth the data-prep effort.

See pattern reference: [`~/code/brain/cheatsheets/azure-ai-foundry-patterns.md`](../../../brain/cheatsheets/azure-ai-foundry-patterns.md)

