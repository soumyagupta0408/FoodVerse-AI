"""Per-category freshness classifiers loaded from models/freshness/<category>/{model.pt,labels.json}.

A category only exists if someone trained and placed a model there (see scripts/train_freshness.py).
No generic fallback model is provided on purpose: freshness cues differ by food.
"""
import json
import logging
from pathlib import Path

from PIL import Image

from app.core.config import get_settings
from app.core.errors import ModelUnavailable

log = logging.getLogger("foodverse.ml")


class TorchFreshnessClassifier:
    def __init__(self, category: str, directory: Path):
        self.category = category
        meta = json.loads((directory / "labels.json").read_text())
        self.labels: list[str] = meta["labels"]
        self.image_size = int(meta.get("image_size", 224))
        self.version = str(meta.get("version", "unversioned"))
        self.name = f"mobilenet_v3_small/{category}"
        self._dir = directory
        self._model = None

    def _load(self):
        if self._model is not None:
            return self._model
        try:
            import torch
            from torchvision import models
        except ImportError as exc:
            raise ModelUnavailable("Freshness models need 'torch' and 'torchvision' installed.") from exc
        net = models.mobilenet_v3_small(weights=None, num_classes=len(self.labels))
        net.load_state_dict(torch.load(self._dir / "model.pt", map_location="cpu"))
        net.eval()
        self._model = net
        return net

    def predict_proba(self, image: Image.Image) -> dict[str, float]:
        import torch
        from torchvision import transforms

        tf = transforms.Compose([
            transforms.Resize((self.image_size, self.image_size)), transforms.ToTensor(),
            transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
        ])
        with torch.no_grad():
            probs = torch.softmax(self._load()(tf(image.convert("RGB")).unsqueeze(0)), dim=1)[0].tolist()
        return dict(zip(self.labels, probs))


class DirectoryFreshnessRegistry:
    def __init__(self, root: Path | None = None):
        self.root = root or get_settings().freshness_models_dir
        self._cache: dict[str, TorchFreshnessClassifier] = {}

    def categories(self) -> list[str]:
        if not self.root.exists():
            return []
        return sorted(p.name for p in self.root.iterdir() if (p / "model.pt").exists() and (p / "labels.json").exists())

    def get(self, category: str):
        key = category.strip().lower()
        if key not in self.categories():
            return None
        if key not in self._cache:
            self._cache[key] = TorchFreshnessClassifier(key, self.root / key)
        return self._cache[key]
