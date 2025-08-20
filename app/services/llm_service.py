import os
import logging
import time
import google.generativeai as genai

MODEL_NAME = "gemini-1.5-flash"
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


class GeminiClient:
    def __init__(self, model_name: str = MODEL_NAME):
        self.model_name = model_name
        self._model = genai.GenerativeModel(model_name, generation_config=GENERATION_CONFIG)

    def generate(self, prompt: str) -> str:
        global API_KEY, _configured
        if not _configured:
            # Attempt late configuration (dotenv maybe loaded after import)
            API_KEY = API_KEY or os.getenv("GEMINI_API_KEY")
            if API_KEY:
                try:
                    genai.configure(api_key=API_KEY)
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
    lines = [
        "You are a helpful, friendly AI assistant who speaks naturally like an Indian English speaker.",
        "Reply in a polite, clear, and engaging manner, providing enough context but not too long.",
        "Use simple examples if needed, keep answers conversational and informative.",
    ]
    lines.extend([f"{('User' if msg['role'] == 'user' else 'Assistant')}: {msg['content']}" for msg in history[-10:]])
    lines.append("Assistant:")
    return "\n".join(lines)
