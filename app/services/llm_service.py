import os
import logging
import time
import google.generativeai as genai
from typing import Any, Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .web_search_service import TavilySearch  # pragma: no cover
    from .weather_service import OpenWeather  # pragma: no cover
else:  # lazy optional import at runtime
    try:
        from .web_search_service import TavilySearch  # type: ignore
    except Exception:
        TavilySearch = None  # type: ignore
    try:
        from .weather_service import OpenWeather  # type: ignore
    except Exception:
        OpenWeather = None  # type: ignore

MODEL_NAME = "gemini-2.5-flash-lite"
GENERATION_CONFIG = {
    "temperature": 0.8,
    "top_p": 0.95,
    "top_k": 40,
    "max_output_tokens": 512,
}

logger = logging.getLogger("voice-agent.llm")

API_KEY = os.getenv("GEMINI_API_KEY")
_configured = False
if not API_KEY:
    logger.warning("GEMINI_API_KEY not set at import; will retry on first request.")
else:
    try:
        genai.configure(api_key=API_KEY)
        _configured = True
    except Exception as e:
        logger.error("Failed to configure Gemini: %s", e)


def get_chanakya_persona() -> str:
    return "\n".join([
        "You are Acharya Chanakya, a legendary wise man from ancient India! You’re a brilliant thinker, planner, money expert, lawmaker, and advisor who wrote the Arthashastra and helped build the powerful Maurya Empire.",
        "Act like Chanakya: be super smart, practical, and tough when needed, with amazing skills in leadership, planning ahead, and understanding people.",
        "Talk like Chanakya would: use simple, old Indian-style words, calling the user 'disciple' or 'friend seeking wisdom.' Share easy tips from the Arthashastra about ruling, money, right and wrong, battles, and making peace.",
        "Keep your answers short, smart, and helpful! Give useful advice with a little life lesson or smart trick, and use a strong but kind voice. Skip modern slang.",
        "Answer any question—about life, work, or even fun ideas—like you’re guiding a king or a student with old wisdom made simple for today.",
        "If the question is silly or wrong, gently correct with a lesson about dharma (doing your duty) or artha (earning wisely).",
        "Push for good choices, balancing dharma (being good), artha (money), kama (fun), and moksha (peace of mind) from Chanakya’s Niti Shastra—explain these if needed!",
        "Sprinkle in a few Sanskrit words for fun, like 'dharma' or 'artha,' and tell what they mean so it feels real but not confusing.",
        "If the chat goes off track, ask a fun question like, 'What dream kingdom are you building, disciple?' to get back on point.",
        "Stay in Chanakya’s character all the time, and end with a cool, wise saying if it fits—like a bonus tip!",
        "When you need fresh, real-world facts (news, prices, dates), call the web_search tool and cite sources briefly.",
        "For weather questions, call the get_weather tool to fetch accurate current conditions before answering.",
    ])

class GeminiClient:
    def __init__(self, model_name: str = MODEL_NAME):
        self.model_name = model_name
        self._model = genai.GenerativeModel(model_name, generation_config=GENERATION_CONFIG)
        self._tools = self._build_tools()
        self._tavily = None  # TavilySearch instance, created lazily
        self._weather = None  # OpenWeather instance, created lazily

    def _build_tools(self) -> list[dict[str, Any]]:
        """Define available tools (function-calling)."""
        return [
            {
                "function_declarations": [
                    {
                        "name": "web_search",
                        "description": "Search the web in real-time to retrieve up-to-date information and sources.",
                        "parameters": {
                            "type": "OBJECT",
                            "properties": {
                                "query": {
                                    "type": "STRING",
                                    "description": "The search query to look up on the web",
                                },
                                "max_results": {
                                    "type": "INTEGER",
                                    "description": "Maximum number of web results to include (1-10)",
                                },
                            },
                            "required": ["query"],
                        },
                    },
                    {
                        "name": "get_weather",
                        "description": "Get current weather for a location using OpenWeather.",
                        "parameters": {
                            "type": "OBJECT",
                            "properties": {
                                "location": {
                                    "type": "STRING",
                                    "description": "City or 'city,countryCode' (e.g., 'Delhi' or 'London,UK')",
                                },
                                "units": {
                                    "type": "STRING",
                                    "description": "Units for temperature: 'metric' or 'imperial'",
                                },
                            },
                            "required": ["location"],
                        },
                    },
                ]
            }
        ]

    def _ensure_tavily(self) -> Optional["TavilySearch"]:
        if self._tavily is None and TavilySearch is not None:
            try:
                self._tavily = TavilySearch()
            except Exception as e:
                logger.warning("Tavily unavailable: %s", e)
        return self._tavily

    def _ensure_weather(self) -> Optional["OpenWeather"]:
        if self._weather is None and OpenWeather is not None:
            try:
                self._weather = OpenWeather()
            except Exception as e:
                logger.warning("OpenWeather unavailable: %s", e)
        return self._weather

    def generate(self, prompt: str) -> str:
        global API_KEY, _configured
        if not _configured:
            # Attempt late configuration (dotenv maybe loaded after import)
            api = API_KEY or os.getenv("GEMINI_API_KEY")
            if api:
                try:
                    genai.configure(api_key=api)
                    _configured = True
                    logger.info("Gemini configured lazily.")
                except Exception as e:
                    logger.error("Late Gemini configuration failed: %s", e)
            if not _configured:
                return "LLM API key missing. Configure GEMINI_API_KEY."
        # Basic retry loop
        last_err = None
        for attempt in range(1, 4):
            try:
                result = self._model.generate_content(prompt)
                text = (getattr(result, "text", "") or "").strip()
                if text:
                    return text
                # If safety blocked or empty
                if hasattr(result, "candidates") and result.candidates:
                    reasons = [c.finish_reason for c in result.candidates if hasattr(c, "finish_reason")]
                    logger.warning("Empty LLM text (reasons=%s) attempt=%d", reasons, attempt)
                else:
                    logger.warning("Empty LLM response attempt=%d", attempt)
            except Exception as e:
                last_err = e
                logger.error("Gemini error attempt %d: %s", attempt, e)
                time.sleep(0.4 * attempt)
        return "Sorry, I couldn't process that right now. Please try rephrasing."

    def chat(self, user_text: str, history: Optional[list[dict[str, str]]] = None, overrides: Optional[Dict[str, str]] = None) -> str:
        """Chat with optional tool use and per-call API key overrides.

        history: list of {role: 'user'|'assistant', content: str}
        overrides: optional dict with keys like GEMINI_API_KEY, TAVILY_API_KEY, OPENWEATHER_API_KEY
        """
        global API_KEY, _configured

        overrides = overrides or {}
        # Configure Gemini (override key takes precedence)
        override_key = overrides.get("GEMINI_API_KEY") if isinstance(overrides, dict) else None
        if override_key:
            try:
                genai.configure(api_key=override_key)
                _configured = True
                API_KEY = override_key
            except Exception as e:
                logger.error("Override Gemini config failed: %s", e)
        if not _configured:
            api = API_KEY or os.getenv("GEMINI_API_KEY")
            if api:
                try:
                    genai.configure(api_key=api)
                    _configured = True
                except Exception as e:
                    logger.error("Late Gemini config failed: %s", e)
            if not _configured:
                return "LLM API key missing. Configure GEMINI_API_KEY."

        # Tool clients (allow per-call overrides)
        tavily: Optional["TavilySearch"]
        weather: Optional["OpenWeather"]
        if overrides.get("TAVILY_API_KEY") and TavilySearch is not None:
            try:
                tavily = TavilySearch(api_key=overrides.get("TAVILY_API_KEY"))
            except Exception as e:
                logger.warning("Tavily override unavailable: %s", e)
                tavily = None
        else:
            tavily = self._ensure_tavily()
        if overrides.get("OPENWEATHER_API_KEY") and OpenWeather is not None:
            try:
                weather = OpenWeather(api_key=overrides.get("OPENWEATHER_API_KEY"))
            except Exception as e:
                logger.warning("OpenWeather override unavailable: %s", e)
                weather = None
        else:
            weather = self._ensure_weather()

        # Build a tool-aware model instance with persona as system instruction
        model = genai.GenerativeModel(
            self.model_name,
            generation_config=GENERATION_CONFIG,
            tools=self._tools,
            system_instruction=get_chanakya_persona(),
        )

        # Build contents array
        contents: list[dict[str, Any]] = []
        if history:
            for msg in history[-8:]:
                role = msg.get("role")
                if role == "assistant":
                    contents.append({"role": "model", "parts": [{"text": msg.get("content", "")} ]})
                else:
                    contents.append({"role": "user", "parts": [{"text": msg.get("content", "")} ]})
        if not (history and history[-1].get("role") == "user" and history[-1].get("content") == user_text):
            contents.append({"role": "user", "parts": [{"text": user_text}]})

        # Tool-calling loop (max 2 tool calls)
        last_response: Optional[Any] = None
        for _ in range(2):
            last_response = model.generate_content(contents)
            # Parse tool calls
            calls = []
            try:
                for cand in getattr(last_response, "candidates", []) or []:
                    parts = getattr(getattr(cand, "content", cand), "parts", [])
                    for p in parts:
                        fc = getattr(p, "function_call", None) or getattr(p, "functionCall", None)
                        if fc:
                            calls.append(fc)
            except Exception:
                calls = getattr(last_response, "function_calls", None) or []
            if not calls:
                break
            try:
                logger.info("[LLM] function_calls=%s", [getattr(c, 'name', '') for c in calls])
            except Exception:
                pass
            for call in calls:
                fn_name = getattr(call, "name", "")
                args = getattr(call, "args", {}) or {}
                tool_output: Dict[str, Any] = {"error": "tool not found"}
                if fn_name == "web_search":
                    q = args.get("query", "")
                    mr = args.get("max_results") or 5
                    logger.info("[Tool] web_search query=%r max_results=%s", q, mr)
                    if tavily is None:
                        tool_output = {"error": "Tavily not configured. Set TAVILY_API_KEY and install tavily-python."}
                    else:
                        tool_output = tavily.search(q, mr)
                        try:
                            logger.info("[Tool] web_search results=%d has_answer=%s", len(tool_output.get('results', [])), bool(tool_output.get('answer')))
                        except Exception:
                            pass
                elif fn_name == "get_weather":
                    loc = args.get("location", "")
                    units = (args.get("units") or "metric").lower()
                    logger.info("[Tool] get_weather location=%r units=%s", loc, units)
                    if weather is None:
                        tool_output = {"error": "OpenWeather not configured. Set OPENWEATHER_API_KEY."}
                    else:
                        tool_output = weather.current_weather(loc, units)

                contents.append(
                    {
                        "role": "tool",
                        "parts": [
                            {
                                "function_response": {
                                    "name": fn_name,
                                    "response": {
                                        "name": fn_name,
                                        "content": tool_output,
                                    },
                                }
                            }
                        ],
                    }
                )

        final_text = (getattr(last_response, "text", "") or "").strip() if last_response else ""
        return final_text or "I couldn't find the answer."

    def stream_generate(self, prompt: str, on_chunk=None) -> str:
        """Stream a Gemini response, printing chunks as they arrive.
        Returns the full accumulated text.
        """
        global API_KEY, _configured
        if not _configured:
            API_KEY = API_KEY or os.getenv("GEMINI_API_KEY")
            if API_KEY:
                try:
                    genai.configure(api_key=API_KEY)
                    _configured = True
                except Exception as e:
                    logger.error("Stream config failed: %s", e)
            if not _configured:
                logger.error("Gemini not configured; skipping stream.")
                return ""
        full_parts: list[str] = []
        try:
            stream = self._model.generate_content(prompt, stream=True)
            for chunk in stream:
                try:
                    part = (getattr(chunk, 'text', '') or '').strip()
                except Exception:
                    part = ''
                if part:
                    full_parts.append(part)
                    print(part, end='', flush=True)
                    if on_chunk:
                        try:
                            on_chunk(part)
                        except Exception:
                            pass
            print()  # newline after stream
        except Exception as e:
            logger.error("Streaming Gemini error: %s", e)
        return ''.join(full_parts).strip()


def build_chat_prompt(history: list) -> str:
    lines = [get_chanakya_persona()]
    lines.extend([f"{('User' if msg['role'] == 'user' else 'Assistant')}: {msg['content']}" for msg in history[-10:]])
    lines.append("Assistant:")
    return "\n".join(lines)

    
