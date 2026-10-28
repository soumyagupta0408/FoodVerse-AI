from app.core.config import get_settings
from app.core.errors import ModelUnavailable


class FasterWhisperSTT:
    def __init__(self, size: str):
        self.name = f"faster-whisper/{size}"
        self._size = size
        self._model = None

    def transcribe(self, path: str) -> dict:
        if self._model is None:
            try:
                from faster_whisper import WhisperModel
            except ImportError as exc:
                raise ModelUnavailable("Speech-to-text needs the 'faster-whisper' package (see requirements-ml.txt).") from exc
            try:
                self._model = WhisperModel(self._size, device="cpu", compute_type="int8")
            except Exception as exc:
                raise ModelUnavailable("Whisper model could not be loaded. Run scripts/download_models.py") from exc
        segments, info = self._model.transcribe(path, vad_filter=True)
        text = " ".join(s.text.strip() for s in segments).strip()
        return {"text": text, "language": getattr(info, "language", None)}


class UnavailableSTT:
    name = "none"

    def transcribe(self, path: str) -> dict:
        raise ModelUnavailable("Speech-to-text is disabled (STT_PROVIDER=none). Type your request instead.")


def build_stt():
    s = get_settings()
    return FasterWhisperSTT(s.stt_model) if s.stt_provider == "faster-whisper" else UnavailableSTT()
