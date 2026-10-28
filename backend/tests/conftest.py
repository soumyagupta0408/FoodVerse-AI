import io
import os
import tempfile

_tmp = tempfile.mkdtemp(prefix="foodverse-test-")
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["MEDIA_ROOT"] = f"{_tmp}/media"
os.environ["SECRET_KEY"] = "test-secret-key-for-tests-only-0123456789"
os.environ["NUTRITION_SEED_DEMO"] = "true"

import numpy as np  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image  # noqa: E402

from app.core import ratelimit  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import get_engine, get_sessionmaker  # noqa: E402
from app.llm import ollama as llm_mod  # noqa: E402
from app.main import app  # noqa: E402
from app.ml import registry  # noqa: E402
from app.ml.base import Prediction  # noqa: E402


@pytest.fixture(autouse=True)
def _fresh_db():
    engine = get_engine()
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    from app.services.nutrition import seed_demo

    with get_sessionmaker()() as db:
        seed_demo(db)
        db.commit()
    ratelimit.reset()
    registry.clear_overrides()
    llm_mod.set_llm_override(None)
    yield


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def make_image(fmt="PNG", size=(256, 256), noisy=True) -> bytes:
    rng = np.random.default_rng(1)
    arr = rng.integers(60, 200, (size[1], size[0], 3), dtype=np.uint8) if noisy else np.full((size[1], size[0], 3), 128, np.uint8)
    buf = io.BytesIO()
    Image.fromarray(arr).save(buf, format=fmt)
    return buf.getvalue()


@pytest.fixture
def png():
    return make_image()


def register(client, email="a@example.com", password="correct-horse-battery"):
    r = client.post("/api/v1/auth/register", json={"email": email, "password": password})
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
def auth(client):
    return register(client)


@pytest.fixture
def auth_b(client):
    return register(client, "b@example.com")


class FakeRecognizer:
    name, version = "fake-food-model", "test"

    def __init__(self, preds=None):
        self.preds = preds or [Prediction("pizza", 0.8), Prediction("hamburger", 0.1), Prediction("french_fries", 0.05)]

    def predict(self, image, top_k=5):
        return self.preds[:top_k]


class FakeFreshClassifier:
    category, name, version = "banana", "fake-fresh", "test"
    labels = ["fresh", "moderate", "spoiled"]

    def __init__(self, probs):
        self.probs = probs

    def predict_proba(self, image):
        return self.probs


class FakeFreshRegistry:
    def __init__(self, probs=None):
        self.clf = FakeFreshClassifier(probs or {"fresh": 0.9, "moderate": 0.07, "spoiled": 0.03}) if probs != "none" else None

    def categories(self):
        return ["banana"] if self.clf else []

    def get(self, c):
        return self.clf if (self.clf and c == "banana") else None


class FakeLLM:
    """Scriptable LLM. `handler(schema_title, user_prompt, call_index) -> dict` produces the JSON answer."""

    name = "fake-llm"

    def __init__(self, handler):
        self.handler, self.calls = handler, []

    def chat(self, system, user):
        self.calls.append(("chat", user))
        return "ok"

    def generate_json(self, system, user, schema):
        self.calls.append((schema.get("title"), user))
        return self.handler(schema.get("title"), user, len(self.calls) - 1)


def recipe_json(title="Veg stir fry", ingredients=None, steps=None, servings=2):
    return {
        "title": title, "description": "Quick.", "servings": servings, "prep_minutes": 10, "cook_minutes": 15,
        "ingredients": ingredients or [{"name": "banana", "quantity": 2, "unit": "pcs", "grams": 200}, {"name": "mystery herb", "quantity": 1, "unit": "bunch", "grams": 20}],
        "steps": steps or ["Chop everything.", "Cook until done."], "substitutions": [], "tips": [], "food_safety": ["Wash hands."],
    }


def meal_json(title="Oats bowl", meal_type="breakfast", names=("banana",)):
    return {"meal_type": meal_type, "title": title, "description": "", "rationale": "Simple.", "prep_minutes": 5,
            "ingredients": [{"name": n, "grams": 100} for n in names]}
