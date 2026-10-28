import csv
import io

import pytest

from app.db.models import NutritionFood
from app.db.session import get_sessionmaker
from scripts.load_nutrition import load


def rows(text):
    return list(csv.DictReader(io.StringIO(text)))


def test_loader_keeps_blank_as_null_and_rejects_bad_rows():
    good = rows("name,kcal,protein_g,carbs_g,fat_g,fiber_g,sugar_g,serving_g,serving_description\nroti,297,9.8,56,3.7,,,40,1 roti\n")
    with get_sessionmaker()() as db:
        assert load(db, good, "test-src", True) == 1
        f = db.query(NutritionFood).filter_by(source="test-src").one()
        assert float(f.kcal) == 297 and f.fiber_g is None and f.sugar_g is None and f.verified
        with pytest.raises(ValueError, match="row 2"):
            load(db, rows("name,kcal\nbad,abc\n"), "x", False)
        with pytest.raises(ValueError, match="negative"):
            load(db, rows("name,kcal\nneg,-5\n"), "x", False)
        with pytest.raises(ValueError, match="missing name"):
            load(db, rows("name,kcal\n,5\n"), "x", False)
