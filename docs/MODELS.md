# Models, data and provenance

Nothing here was trained by this project. No metrics are claimed. Every model below must be evaluated by you before relying on it.

| Task | Default | Type | Approx. size | CPU speed (expected) | Licence (verify before use) |
|---|---|---|---|---|---|
| Food recognition | `nateraw/food` (ViT fine-tuned on Food-101) via Transformers | pretrained, Hugging Face | ~350 MB | ~0.3–1 s/image | check the model card; Food-101 data is for research use |
| Freshness | **none shipped.** Per-category MobileNetV3-small you train | custom | ~10 MB each | <0.1 s/image | your dataset's licence |
| Hygiene | `google/owlvit-base-patch32` zero-shot detector | pretrained | ~600 MB | ~2–6 s/frame | Apache-2.0 (verify) |
| Speech-to-text | faster-whisper `base` (int8) | pretrained | ~150 MB | faster than real time | MIT / model terms (verify) |
| LLM | `qwen2.5:3b-instruct` via Ollama (7B optional with 16 GB RAM) | pretrained, local | ~2 GB (3B) | ~5–10 tokens/s (3B, CPU) | check the Ollama model page |
| Nutrition | your CSV (USDA FoodData Central, IFCT…) via `scripts/load_nutrition.py` | dataset | n/a | n/a | USDA data is public domain; check IFCT terms |

Model ids, sizes and speeds above are expectations from general knowledge. They were **not downloaded or timed** in the build environment (no access to the hosting sites). Confirm each id exists and loads with `python scripts/download_models.py`.

## Known limitations

- **Recognition** is single-label over 101 mostly Western dishes. It will mislabel many regional dishes and cannot split a plate of several foods. The UI says so and offers manual correction.
- **Freshness** only works for categories with a trained model. No generic model is offered because appearance cues differ per food. With none installed every result is "Unable to determine".
- **Hygiene** uses a zero-shot detector never validated on kitchen footage. Only *gloves* and *hair cap* are attempted; hand-washing, surface cleanliness, raw/ready-to-eat separation and cross-contamination report "insufficient evidence: no detector configured". Confidence is capped at 0.6 and every finding needs human review. Absence of a detection in a frame is never treated as a violation; the judge needs at least 5 frames with a person visible.
- **Portions** from a photo are not estimated; defaults are flagged as estimates and users can enter grams.
- **LLM output** can be wrong or invented. Recipes are not kitchen-tested. Ingredient gram weights are model estimates.

## Training a freshness model

1. Obtain a labelled dataset for one food (e.g. fresh/rotten bananas). **Check its licence** and de-duplicate near-identical photos.
2. Lay it out as `data/banana/{fresh,moderate,spoiled}/*.jpg` (two classes are fine).
3. `python scripts/train_freshness.py data/banana --category banana --epochs 8` (needs `requirements-ml.txt`).
4. The script does a seeded, stratified 70/15/15 split, picks the epoch by validation accuracy, and writes **held-out test** accuracy, per-class precision/recall and the confusion matrix to `models/freshness/banana/metrics.json`.
5. Read `metrics.json` before enabling it. Small or web-scraped datasets give optimistic numbers that fail on real photos.

`scripts/train_freshness.py` compiles but **has not been executed** (no dataset or torch in the build environment).

## Evaluation you should run before real use

Top-1/top-5 accuracy of the recogniser on your own dishes; per-class precision/recall for each freshness model on photos taken with your cameras; event-level precision/recall of hygiene findings against human-labelled clips; spot-check nutrition matches against source tables.
