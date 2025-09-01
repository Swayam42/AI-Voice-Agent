---
name: 🐞 Bug report
about: Report a bug to help us improve
title: "[BUG] "
labels: bug
assignees: ""
---

### Describe the bug
A clear and concise description of the issue.
- Actual result:
- Expected result:

### Impact
- Severity: [blocker | high | medium | low]
- Frequency: [always | often | sometimes | rare]

### Affected area (check all that apply)
- [ ] Mic/WebSocket streaming (/ws)
- [ ] STT (AssemblyAI)
- [ ] LLM (Gemini) response
- [ ] Tool: Tavily web_search
- [ ] Tool: OpenWeather get_weather
- [ ] TTS (Murf) REST (/generate_audio)
- [ ] TTS (Murf) WebSocket (streamed speech)
- [ ] Settings modal / API keys gate
- [ ] Debug endpoints (/debug/*)
- [ ] UI (chat bubbles, audio playback)
- [ ] Deployment (Render/Vercel/Railway)

### Steps to Reproduce
1) Scenario: [voice chat | text chat | TTS | echo | debug route]
2) Local or Cloud: [local dev | Render URL]
3) Exact steps:
   - Go to: [page/URL]
   - Action: [click mic / upload file / call endpoint]
   - Input: [prompt, city name, etc.]
   - Observe: [what happened]

### Reproduction method
- Local dev:
  - Python: `python -m venv .venv && .venv\Scripts\activate && pip install -r requirements.txt`
  - Run: `cd app && uvicorn main:app --reload`
  - Endpoint used: [e.g., POST /agent/chat/{session_id} | WS /ws | /debug/...]
- Cloud:
  - Provider: [Render/Railway/Other]
  - App URL: https://
  - Start command: `cd app && uvicorn main:app --host 0.0.0.0 --port $PORT`

### Request details (if LLM/tool-related)
- Prompt or user text:
- Final transcript (from logs, if voice):
- Gemini tool calls observed (if any): [web_search / get_weather / none]
- Tool inputs/outputs (short snippet):

### Screenshots / Logs
- Server logs (relevant excerpt):
- Browser console errors:
- Network/WS notes (e.g., WS closed code, HAR if possible):
- Render build/runtime log snippet (if deployed):

### API keys & config (do NOT paste real keys)
- Using in-app session keys? [yes/no]
- Keys provided during session: [AssemblyAI, Gemini, Murf, Tavily, OpenWeather]
- .env fallback present on server? [yes/no]
- Model/version: [gemini-1.5-flash or other]
- TTS voice: [en-US-charles or other]

### Environment
- OS: [Windows 11 / macOS 14 / Ubuntu 22.04]
- Browser: [Chrome 120 / Edge 125 / Safari 17]
- Python: `python --version`
- FastAPI/Uvicorn: [versions]
- Dependencies changed recently? [yes/no]

### Media (optional but helpful)
- Attach a short audio sample (≤10s) that reproduces the issue.
- Screenshot or screen recording if UI-related.

### Additional context
Anything else that helps (rate limits/429s, flaky network, steps
