<div align="center">

# Chanakya AI Voice Agent (30‑Day Build)

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)  
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111-009688?logo=fastapi)](https://fastapi.tiangolo.com/)
[![AssemblyAI](https://img.shields.io/badge/STT-AssemblyAI-5932F3)](https://www.assemblyai.com/)
[![Gemini LLM](https://img.shields.io/badge/LLM-Gemini-4285F4)](https://ai.google.dev/)
[![Murf AI](https://img.shields.io/badge/TTS-Murf.ai-FF8800)](https://murf.ai/)

Natural, voice‑first conversational AI inspired by Acharya Chanakya: Speak → Transcribe (AssemblyAI) → Reason (Gemini, Chanakya persona) → Respond with realistic speech (Murf)

</div>

<p align="center">
  <img src="app/static/images/demo.gif" alt="Demo Conversation" />
</p>

## ✨ Core Features

- One‑tap voice chat (microphone → AI answer with auto‑played voice)
- Multi‑stage pipeline: STT → LLM → TTS
- Persistent in‑memory session history (per browser session id)
- Real‑time web search via Tavily (Gemini Function Calling)
- WebSocket live transcripts + streamed TTS playback
- Sidebar Tools:
  - Text to Speech generator (choose text → Murf voice output)
  - Echo Bot (record → transcribe → re‑speak your words in another voice)
- Replay last AI audio + chat bubble UI
- Clean, minimal vanilla JS frontend (no heavy frameworks)

## 🧠 Architecture Flow

1. User presses Start Speaking → Browser records audio (MediaRecorder)
2. Audio uploaded to `/agent/chat/{session_id}`
3. AssemblyAI transcribes bytes → text
4. Chat history compiled into a Gemini prompt
5. Gemini generates assistant reply
6. Murf API converts reply text to speech (voice: en-US-ken)
7. Frontend auto‑plays the returned audio & renders chat bubbles

```
User Voice → FastAPI → AssemblyAI → Gemini → Murf → Browser Playback
```

Also supports real‑time streaming via WebSocket (`/ws`) with partial transcripts and chunked TTS audio.

## 🗂️ Project Structure

```
app/
├── main.py                # FastAPI entrypoint (routes import service layer)
├── services/              # Separated domain/service logic
│   ├── stt_service.py     # AssemblyAI transcription helpers
│   ├── tts_service.py     # Murf.ai TTS client wrapper
│   ├── llm_service.py     # Gemini client + prompt builder + function calling
│   ├── murf_ws_service.py # Murf WebSocket streaming (chunked TTS)
│   ├── web_search_service.py # Tavily search wrapper
│   └── streaming_transcriber.py # AssemblyAI streaming transcription
├── schemas/               # Pydantic request/response models
│   └── tts.py             # TextToSpeechRequest, ChatResponse, etc.
├── templates/
│   └── index.html         # UI shell (chat + sidebar tools)
├── static/
│   ├── css/style.css      # Styles (layout + responsive + theme)
│   ├── JS/script.js       # Frontend logic (record, upload, autoplay)
│   ├── images/            # Logo, screenshot, demo GIF
│   │   ├── logo.png
│   │   ├── ui-screenshot.png
│   │   └── demo.gif
│   └── sounds/            # Mic UI feedback
│       ├── mic_start.mp3
│       └── mic_stop.mp3
├── uploads/               # (Optional) temp upload storage placeholder
requirements.txt           # Dependencies
.env                       # Secret API keys (NOT committed)
.gitignore                 # Ignore rules
README.md                  # This file
```

## 🔑 Environment Variables (.env)

Create a `.env` file in the project root:

```
ASSEMBLYAI_API_KEY=your_assemblyai_key
GEMINI_API_KEY=your_gemini_key
MURF_API_KEY=your_murf_key
TAVILY_API_KEY=your_tavily_key

# Optional UI/voice tuning
MAX_UI_ANSWER_CHARS=120   # 0 to disable trimming
MAX_TTS_CHARS=240         # per TTS chunk for Murf WS
```

### Where to get API keys

- AssemblyAI: https://www.assemblyai.com/app/account
- Gemini (Google AI Studio): https://aistudio.google.com/app/apikey
- Murf AI: https://murf.ai/api (Account settings → API key)
- Tavily: https://app.tavily.com/ (Dashboard → API Keys)

Tip: copy `.env.example` to `.env` and fill your values. Never commit `.env`.

## 🚀 Quick Start

```bash
# 1. Create & activate a virtual environment
python -m venv .venv
.venv\Scripts\activate  # Windows

# 2. Install dependencies
pip install -r requirements.txt

# 3. Add your .env file (see above)

# 4. Run the server (simple dev mode)
cd app && python main.py

# 5. Open in browser
http://127.0.0.1:8000/

# (Alt) Use uvicorn directly for auto-reload (optional)
# uvicorn app.main:app --reload
```

## 📡 Key Endpoints

| Method | Endpoint                   | Purpose                                       |
| ------ | -------------------------- | --------------------------------------------- |
| POST   | `/agent/chat/{session_id}` | Voice chat: audio → transcription → LLM → TTS |
| POST   | `/tts/echo`                | Echo tool (repeat what you said with Murf)    |
| POST   | `/generate_audio`          | Direct text → speech (Murf)                   |
| POST   | `/transcribe/file`         | Raw transcription (AssemblyAI)                |
| WS     | `/ws`                      | Streaming: partial transcripts + chunked TTS  |
| GET    | `/debug/web_search`        | Tavily test: `?query=your+question`           |
| GET    | `/debug/llm_chat`          | LLM (no audio): `?q=hello`                    |
| POST   | `/debug/llm_chat_text`     | LLM (no audio): `{ "text": "hello" }`         |

## 🧪 Tech Highlights

- FastAPI backend with service + schema layering (clean separation)
- AssemblyAI transcription (resilient + fallback path)
- Google Gemini (gemini-1.5-flash) via reusable client & retry logic
- Gemini Function Calling with a `web_search` tool backed by Tavily
- Murf AI TTS wrapped in a lightweight client (consistent error handling)
- Murf WebSocket streaming with safe chunking to speak full answers
- MediaRecorder + multipart upload for low-latency voice capture
- Autoplay + replay logic with audio unlock and retry
- Structured Pydantic responses for clearer API contracts

## 🔄 Session Handling

Browser session id is appended to the URL (query param). History is stored in an in‑memory dict (`CHAT_HISTORY`) — suitable for prototyping; swap with Redis or DB for production scaling.

## 🛡️ Notes / Limits

- Not production-hardened (no auth, rate limiting, or persistence yet)
- API keys must remain secret (.env not committed)
- In-memory history resets on server restart (swap with Redis/DB later)
- Gemini key must be loaded before first request (lazy reconfigure added)

## 🤝 Contributing

Prototype phase — feel free to open issues with ideas (latency, UI/UX, voice packs, multilingual support). PRs welcome after discussion.

<!--## 📄 License

Add a LICENSE file (MIT recommended) if you plan to open source formally.-->

## 🙌 Acknowledgements

- AssemblyAI for speech-to-text
- Google Gemini for language understanding
- Murf AI for high-quality synthetic voices
- FastAPI for the rapid backend framework

---

Built as part of a 30‑Day AI Voice Agent Challenge by <a href="https://murf.ai/" target="_blank">Murf.ai</a>
