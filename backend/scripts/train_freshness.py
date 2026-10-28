"""Train a per-category freshness classifier (MobileNetV3-small, CPU friendly) and evaluate it on held-out data.

Dataset layout (you supply it and MUST check its licence):
    data/<category>/fresh/*.jpg   data/<category>/moderate/*.jpg   data/<category>/spoiled/*.jpg
(two classes are fine; use the folder names as the labels)

Usage: python scripts/train_freshness.py data/banana --category banana --epochs 8
Outputs models/freshness/<category>/{model.pt,labels.json,metrics.json}

The split is stratified and fixed by --seed. Test images are never used for training or model selection.
Duplicate/near-duplicate photos across splits are the usual cause of inflated scores: de-duplicate first.
"""
import argparse
import json
import random
from collections import defaultdict
from pathlib import Path

import torch
from PIL import Image
from torch import nn
from torch.utils.data import DataLoader, Dataset
from torchvision import models, transforms

MEAN, STD = [0.485, 0.456, 0.406], [0.229, 0.224, 0.225]


class Items(Dataset):
    def __init__(self, items, tf):
        self.items, self.tf = items, tf

    def __len__(self):
        return len(self.items)

    def __getitem__(self, i):
        path, y = self.items[i]
        return self.tf(Image.open(path).convert("RGB")), y


def split(root: Path, seed: int):
    labels = sorted(p.name for p in root.iterdir() if p.is_dir())
    by_class = defaultdict(list)
    for y, lab in enumerate(labels):
        by_class[y] = sorted(p for p in (root / lab).iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"})
    rng, out = random.Random(seed), {"train": [], "val": [], "test": []}
    for y, files in by_class.items():
        rng.shuffle(files)
        n = len(files)
        a, b = int(n * 0.7), int(n * 0.85)
        out["train"] += [(f, y) for f in files[:a]]
        out["val"] += [(f, y) for f in files[a:b]]
        out["test"] += [(f, y) for f in files[b:]]
    return labels, out, {labels[y]: len(f) for y, f in by_class.items()}


def evaluate(net, loader, n_classes):
    net.eval()
    cm = [[0] * n_classes for _ in range(n_classes)]
    with torch.no_grad():
        for x, y in loader:
            for t, p in zip(y.tolist(), net(x).argmax(1).tolist()):
                cm[t][p] += 1
    total = sum(map(sum, cm)) or 1
    per = {}
    for c in range(n_classes):
        tp = cm[c][c]
        prec = tp / max(1, sum(cm[r][c] for r in range(n_classes)))
        rec = tp / max(1, sum(cm[c]))
        per[c] = {"precision": round(prec, 4), "recall": round(rec, 4)}
    return {"accuracy": round(sum(cm[i][i] for i in range(n_classes)) / total, 4), "per_class": per, "confusion_matrix": cm, "n": total}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("data_dir")
    ap.add_argument("--category", required=True)
    ap.add_argument("--epochs", type=int, default=8)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", default="models/freshness")
    a = ap.parse_args()
    torch.manual_seed(a.seed)
    labels, sets, counts = split(Path(a.data_dir), a.seed)
    print("class counts:", counts, "split sizes:", {k: len(v) for k, v in sets.items()})
    train_tf = transforms.Compose([transforms.Resize((224, 224)), transforms.RandomHorizontalFlip(), transforms.ColorJitter(0.1, 0.1), transforms.ToTensor(), transforms.Normalize(MEAN, STD)])
    eval_tf = transforms.Compose([transforms.Resize((224, 224)), transforms.ToTensor(), transforms.Normalize(MEAN, STD)])
    loaders = {k: DataLoader(Items(v, train_tf if k == "train" else eval_tf), batch_size=32, shuffle=k == "train") for k, v in sets.items()}
    net = models.mobilenet_v3_small(weights=models.MobileNet_V3_Small_Weights.DEFAULT)
    net.classifier[-1] = nn.Linear(net.classifier[-1].in_features, len(labels))
    opt, loss_fn = torch.optim.AdamW(net.parameters(), lr=1e-3), nn.CrossEntropyLoss()
    best, best_state = -1.0, None
    for ep in range(a.epochs):
        net.train()
        for x, y in loaders["train"]:
            opt.zero_grad()
            loss_fn(net(x), y).backward()
            opt.step()
        val = evaluate(net, loaders["val"], len(labels))
        print(f"epoch {ep + 1}: val acc {val['accuracy']}")
        if val["accuracy"] > best:
            best, best_state = val["accuracy"], {k: v.clone() for k, v in net.state_dict().items()}
    net.load_state_dict(best_state)
    test = evaluate(net, loaders["test"], len(labels))
    out = Path(a.out) / a.category.lower()
    out.mkdir(parents=True, exist_ok=True)
    torch.save(net.state_dict(), out / "model.pt")
    (out / "labels.json").write_text(json.dumps({"labels": labels, "image_size": 224, "version": f"seed{a.seed}-ep{a.epochs}"}))
    (out / "metrics.json").write_text(json.dumps({"class_counts": counts, "val_accuracy": best, "test": test, "seed": a.seed}, indent=2))
    print("held-out test:", test["accuracy"], "->", out)


if __name__ == "__main__":
    main()
