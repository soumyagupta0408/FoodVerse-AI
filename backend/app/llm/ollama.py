import httpx

from app.core.config import get_settings
from app.llm.base import LLMBadResponse, LLMUnavailable, parse_json_text


class OllamaClient:
    def __init__(self, base_url: str, model: str, timeout: int):
        self.base_url, self.name, self.timeout = base_url.rstrip("/"), model, timeout

    def _post(self, payload: dict) -> str:
        try:
            r = httpx.post(f"{self.base_url}/api/chat", json=payload, timeout=self.timeout)
        except httpx.ConnectError as exc:
            raise LLMUnavailable(f"Cannot reach the local language model at {self.base_url}. Start Ollama and run `ollama pull {self.name}`.") from exc
        except httpx.TimeoutException as exc:
            raise LLMUnavailable("The local language model took too long to answer. Try a smaller model or a shorter request.") from exc
        if r.status_code == 404:
            raise LLMUnavailable(f"Model '{self.name}' is not installed. Run `ollama pull {self.name}`.")
        if r.status_code >= 400:
            raise LLMUnavailable(f"Language model error ({r.status_code})")
        try:
            return r.json()["message"]["content"]
        except (KeyError, ValueError) as exc:
            raise LLMBadResponse("Unexpected response from the language model") from exc

    def chat(self, system: str, user: str) -> str:
        return self._post({"model": self.name, "stream": False, "options": {"temperature": 0.3},
                           "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]})

    def generate_json(self, system: str, user: str, schema: dict) -> dict:
        text = self._post({"model": self.name, "stream": False, "format": schema, "options": {"temperature": 0.4},
                           "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]})
        return parse_json_text(text)


class NoLLM:
    name = "none"

    def chat(self, system, user):
        raise LLMUnavailable("No language model is configured (LLM_PROVIDER=none).")

    def generate_json(self, system, user, schema):
        raise LLMUnavailable("No language model is configured (LLM_PROVIDER=none).")


_client = None
_override = None


def set_llm_override(client) -> None:
    global _override
    _override = client


def get_llm():
    global _client
    if _override is not None:
        return _override
    if _client is None:
        s = get_settings()
        _client = OllamaClient(s.ollama_url, s.ollama_model, s.llm_timeout_seconds) if s.llm_provider == "ollama" else NoLLM()
    return _client
