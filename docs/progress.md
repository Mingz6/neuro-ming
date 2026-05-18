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

> Reference: `neuro-ming/comms/2026-05-09-summary.md` (voice memo — conversational AI architecture)

**Decision (2026-05-18): Use Pipecat framework for M3+M4.**
The voice memo's "PykeCat sub-agents" = Pipecat + pipecat-subagents (transcription garbled the name).
tend repo (`~/code/playground/tend`) is the reference implementation (291 commits, 8.5/10 quality).
Pipecat handles STT + TTS + VAD + interruption + pipeline orchestration — no need to hand-roll.

- [ ] Install `pipecat-ai` with extras: `pipecat-ai[deepgram,openai,silero]`
- [ ] Create `core/voice_pipeline.py` — Pipecat pipeline with Local Transport (mic/speaker)
- [ ] STT: Deepgram Nova-3 via Pipecat (best value, real-time streaming)
- [ ] VAD: Silero VAD via Pipecat (voice activity detection — knows when user stops talking)
- [ ] Wire existing `core/personality.py` system prompt into Pipecat LLM processor
- [ ] Real-time partial transcription display (Pipecat emits interim results)
- [ ] **Evaluate TTS in Pipecat context:**
  - Option 1: Azure OpenAI TTS (already working, keep current)
  - Option 2: ElevenLabs via Pipecat (better naturalness, ~$20/mo)
  - Option 3: Cartesia Sonic (ultra-low latency, Pipecat native)

## M4: Conversational Loop

> Reference: `neuro-ming/comms/2026-05-09-summary.md` — two-tier voice AI architecture from voice memo
> **Framework: Pipecat + pipecat-subagents** (confirmed — same stack as tend)

**Architecture goal:** fast conversational shell (cheap model) + async Opus workers + shared bus

```
User Voice
    │
    ▼
STT (Deepgram)
    │
    ▼
Fast Shell (Haiku / cheap model)  ←─── always on, low latency
    │   ├── simple reply → TTS → voice out
    └── heavy task? → tool call → spawn Opus worker
                                        │
                                    work done
                                        │
                                    write → shared bus
                                        │
                            Haiku reads bus → TTS announce
```

- [ ] **Two-tier LLM split (Pipecat pipeline)**
  - Fast shell: GPT-4o-mini or Haiku as the Pipecat LLM processor — handles all voice I/O
  - Workers: Opus via **pipecat-subagents** for heavy tool execution
  - Shell never blocks on worker — Pipecat pipeline stays responsive
  - **Future: OpenAI Realtime API (Speech-to-Speech)** — skip STT+TTS entirely, ~300ms latency
- [ ] **Shared message bus (pipecat-subagents pattern)**
  - pipecat-subagents uses a shared message bus between agents (same as tend's Hub/Brain/Worker)
  - Workers post `{task_id, status, result, timestamp}` when done
  - Main pipeline announces completed tasks via TTS
  - Simplest start: in-process asyncio, upgrade to Redis later
- [ ] **Queue + announce UX**
  - Immediate acknowledgement: "I've queued that, will let you know when it's done"
  - Pipeline remains available for new requests while worker runs
  - Proactive announcement when worker finishes (no user re-prompt needed)
- [ ] **Parallel workers**
  - Multiple tool calls can fire simultaneously (email + calendar + weather)
  - Each posts independently to shared bus
  - Pipeline announces each as they complete
- [ ] VAD-based turn detection (Silero VAD — included in Pipecat)
- [ ] Interruption handling (Pipecat built-in — cancels TTS when user speaks)
- [ ] **Framework: pipecat-ai + pipecat-subagents** (confirmed — "PykeCat sub-agents" from voice memo)
  - Reference implementation: `~/code/playground/tend` (Hub/Brain/Worker pattern)
  - pipecat-subagents GitHub: https://github.com/pipecat-ai/pipecat-subagents

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

