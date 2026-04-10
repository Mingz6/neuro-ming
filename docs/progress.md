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

- [ ] TTS integration (OpenAI TTS or local)
- [ ] Audio playback in browser
- [ ] WebSocket streaming

## M3: Voice Input (STT)

- [ ] Browser microphone capture
- [ ] STT integration (Whisper)
- [ ] Real-time transcription

## M4: Conversational Loop

- [ ] Combine M1+M2+M3
- [ ] Push-to-talk or VAD
- [ ] Interruption handling
