"""Load a nutrition table (per 100 g) into the database. Works for USDA exports, IFCT, or any CSV you prepare.

CSV columns: name, kcal, protein_g, carbs_g, fat_g, fiber_g, sugar_g, serving_g, serving_description
Empty cells mean UNKNOWN and are stored as NULL (never as zero).

Usage: python scripts/load_nutrition.py data.csv --source "USDA FoodData Central SR Legacy 2018" [--verified] [--replace]
"""
import argparse
import csv
import sys
from decimal import Decimal, InvalidOperation

from sqlalchemy import delete

from app.db.models import NutritionFood
from app.db.session import get_sessionmaker
from app.services.safety import normalize

FIELDS = ("kcal", "protein_g", "carbs_g", "fat_g", "fiber_g", "sugar_g")


def _num(v):
    v = (v or "").strip()
    if v == "":
        return None
    try:
        d = Decimal(v)
    except InvalidOperation:
        raise ValueError(f"not a number: {v!r}")
    if d < 0:
        raise ValueError(f"negative value: {v!r}")
    return d


def load(db, rows, source: str, verified: bool) -> int:
    n = 0
    for i, row in enumerate(rows, start=2):
        name = (row.get("name") or "").strip()
        if not name:
            raise ValueError(f"row {i}: missing name")
        try:
            vals = {f: _num(row.get(f)) for f in FIELDS}
            serving = _num(row.get("serving_g"))
        except ValueError as exc:
            raise ValueError(f"row {i}: {exc}") from exc
        db.add(NutritionFood(source=source, name=name, name_norm=normalize(name), verified=verified, default_serving_g=serving,
                             serving_description=(row.get("serving_description") or "").strip() or None, **vals))
        n += 1
    db.flush()
    return n


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("csv_path")
    ap.add_argument("--source", required=True)
    ap.add_argument("--verified", action="store_true")
    ap.add_argument("--replace", action="store_true", help="delete existing rows from this source first")
    a = ap.parse_args()
    with open(a.csv_path, newline="", encoding="utf-8-sig") as fh, get_sessionmaker()() as db:
        if a.replace:
            db.execute(delete(NutritionFood).where(NutritionFood.source == a.source))
        count = load(db, csv.DictReader(fh), a.source, a.verified)
        db.commit()
    print(f"Loaded {count} foods from {a.csv_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
