"""Lazy singletons for model adapters. Tests replace them with set_override()."""
from typing import Any

from app.ml.freshness_models import DirectoryFreshnessRegistry
from app.ml.hygiene_detectors import build_hygiene_detector
from app.ml.recognizers import build_recognizer
from app.ml.stt import build_stt

_factories = {
    "recognizer": build_recognizer,
    "freshness": DirectoryFreshnessRegistry,
    "hygiene": build_hygiene_detector,
    "stt": build_stt,
}
_instances: dict[str, Any] = {}
_overrides: dict[str, Any] = {}


def _get(key: str):
    if key in _overrides:
        return _overrides[key]
    if key not in _instances:
        _instances[key] = _factories[key]()
    return _instances[key]


def set_override(key: str, obj) -> None:
    _overrides[key] = obj


def clear_overrides() -> None:
    _overrides.clear()
    _instances.clear()


def get_recognizer():
    return _get("recognizer")


def get_freshness_registry():
    return _get("freshness")


def get_hygiene_detector():
    return _get("hygiene")


def get_stt():
    return _get("stt")
