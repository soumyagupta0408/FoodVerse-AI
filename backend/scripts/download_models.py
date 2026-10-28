"""Download every model once so the app can run offline afterwards.

Usage: python scripts/download_models.py [--skip recognizer|hygiene|stt]
Needs internet and `pip install -r requirements-ml.txt`. Sizes are approximate: food ViT ~350 MB,
OWL-ViT base ~600 MB, Whisper base ~150 MB.
"""
import argparse
import sys

from app.core.config import get_settings


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip", action="append", default=[])
    args = ap.parse_args()
    s = get_settings()
    failed = []
    try:
        from transformers import pipeline
    except ImportError:
        print("Install requirements-ml.txt first.")
        return 1
    if "recognizer" not in args.skip and s.recognizer_provider == "hf":
        print(f"-> recognizer {s.recognizer_model}")
        try:
            pipeline("image-classification", model=s.recognizer_model)
        except Exception as exc:  # noqa: BLE001
            failed.append(("recognizer", exc))
    if "hygiene" not in args.skip and s.hygiene_detector_provider == "owlvit":
        print(f"-> hygiene detector {s.hygiene_detector_model}")
        try:
            pipeline("zero-shot-object-detection", model=s.hygiene_detector_model)
        except Exception as exc:  # noqa: BLE001
            failed.append(("hygiene", exc))
    if "stt" not in args.skip and s.stt_provider == "faster-whisper":
        print(f"-> whisper {s.stt_model}")
        try:
            from faster_whisper import WhisperModel

            WhisperModel(s.stt_model, device="cpu", compute_type="int8")
        except Exception as exc:  # noqa: BLE001
            failed.append(("stt", exc))
    for name, exc in failed:
        print(f"FAILED {name}: {exc}")
    print("LLM: run `ollama pull " + s.ollama_model + "` separately.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
