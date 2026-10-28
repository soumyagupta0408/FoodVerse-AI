"""The eight representative user journeys from the spec, run through the HTTP API against a real database.

Models and the LLM are stand-ins (no weights/Ollama in CI), so these prove the wiring, data flow, persistence
and isolation: not model accuracy.
"""
import io

from app.llm import ollama as llm_mod
from app.ml import registry
from app.worker import run_once
from tests.conftest import FakeLLM, FakeRecognizer, FakeFreshRegistry, make_image, meal_json, recipe_json, register
from tests.test_hygiene import FakeDetector, make_video


def test_full_user_journeys(client):
    a = register(client, "alice@example.com")
    b = register(client, "bob@example.com")
    registry.set_override("recognizer", FakeRecognizer())
    registry.set_override("freshness", FakeFreshRegistry())
    registry.set_override("hygiene", FakeDetector())
    client.patch("/api/v1/users/me/profile", headers=a, json={"allergies": ["peanut"], "diet_pattern": "vegetarian"})

    def llm(title, user, i):
        if title == "RecipeData":
            return recipe_json("Banana oats", [{"name": "banana", "grams": 120}, {"name": "oats", "grams": 40}])
        if title == "DayData":
            return {"meals": [meal_json("Fruit bowl", "breakfast", ("banana",)), meal_json("Rice plate", "lunch", ("white rice cooked",)), meal_json("Egg rice", "dinner", ("boiled egg", "white rice cooked"))]}
        return meal_json("Safe meal", "lunch", ("apple",))

    llm_mod.set_llm_override(FakeLLM(llm))

    # 1. image -> recognition
    rec = client.post("/api/v1/food/recognize", headers=a, files={"file": ("lunch.png", io.BytesIO(make_image()), "image/png")}).json()
    assert rec["result"]["top"]["label"] == "pizza"
    # 2. recognition -> nutrition (user corrects the label first)
    client.patch(f"/api/v1/food/recognize/{rec['id']}/correction", headers=a, json={"food_name": "banana"})
    nut = client.post("/api/v1/nutrition/analyze", headers=a, json={"recognition_id": rec["id"], "grams": 150}).json()
    assert nut["result"]["nutrients"]["kcal"] == 133.5 and nut["parent_id"] == rec["id"]
    # 3. freshness
    fr = client.post("/api/v1/freshness/analyze", headers=a, files={"file": ("b.png", io.BytesIO(make_image()), "image/png")}, data={"food_category": "banana"}).json()
    assert fr["result"]["display"] == "Fresh" and "microbiologically safe" in fr["result"]["safety_note"]
    # 4. kitchen video -> job -> worker -> report with evidence
    job = client.post("/api/v1/hygiene/analyze", headers=a, files={"file": ("k.avi", io.BytesIO(make_video()), "video/x-msvideo")}).json()
    assert job["status"] == "queued" and run_once()
    done = client.get(f"/api/v1/hygiene/jobs/{job['id']}", headers=a).json()
    report = client.get(f"/api/v1/hygiene/reports/{done['report_id']}", headers=a).json()
    assert done["status"] == "completed" and any(f["evidence_media_id"] for f in report["findings"])
    # 5. recipe from ingredients (vegetarian + peanut-free from the profile)
    recipe = client.post("/api/v1/recipes/generate", headers=a, json={"ingredients": ["banana", "oats"], "save": True}).json()
    assert recipe["meta"]["restriction_check"]["applied"] == ["allergy: peanut", "diet: vegetarian"]
    # 6. meal plan with explicit preferences, then shopping list
    plan = client.post("/api/v1/meal-plans/generate", headers=a, json={"days": 2, "diet_pattern": "vegetarian"}).json()
    plan = client.get(f"/api/v1/meal-plans/{plan['id']}", headers=a).json()
    assert plan["status"] == "ready" and len(plan["plan"]["days"]) == 2
    assert client.post(f"/api/v1/meal-plans/{plan['id']}/shopping-list", headers=a).json()["items"]
    # 7. history + dashboard reflect exactly what was stored
    hist = client.get("/api/v1/history", headers=a).json()
    assert {i["kind"] for i in hist["items"]} == {"recognition", "nutrition", "freshness", "hygiene", "recipe", "meal_plan"}
    dash = client.get("/api/v1/dashboard/summary", headers=a).json()
    assert dash["counts"]["recognition"] == 1 and dash["counts"]["hygiene_jobs"] == 1 and dash["counts"]["saved_recipes"] == 1
    assert dash["alerts"]  # the hygiene finding is awaiting human review
    # 8. Bob can see none of it
    assert client.get("/api/v1/history", headers=b).json()["total"] == 0
    assert client.get("/api/v1/dashboard/summary", headers=b).json()["counts"]["recognition"] == 0
    for url in (f"/api/v1/food/recognize/{rec['id']}", f"/api/v1/nutrition/{nut['id']}", f"/api/v1/freshness/{fr['id']}", f"/api/v1/hygiene/jobs/{job['id']}",
                f"/api/v1/hygiene/reports/{done['report_id']}", f"/api/v1/recipes/{recipe['id']}", f"/api/v1/meal-plans/{plan['id']}", f"/api/v1/media/{rec['media_id']}",
                f"/api/v1/exports/analysis/{rec['id']}"):
        assert client.get(url, headers=b).status_code == 404, url
    assert client.get(f"/api/v1/food/recognize/{rec['id']}").status_code == 401  # and no token means no access at all
