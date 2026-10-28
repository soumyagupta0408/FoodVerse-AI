from app.llm import ollama as llm_mod
from tests.conftest import FakeLLM, meal_json


def day_handler(violating_lunch=False):
    def h(title, user, i):
        if title == "DayData":
            meals = [meal_json("Oats", "breakfast", ("banana",)),
                     meal_json("Peanut noodles" if violating_lunch else "Rice bowl", "lunch", ("peanut butter",) if violating_lunch else ("white rice cooked",)),
                     meal_json("Chicken plate", "dinner", ("chicken breast cooked", "white rice cooked"))]
            return {"meals": meals}
        mt = "lunch" if "ONE lunch" in user else "dinner" if "ONE dinner" in user else "breakfast"
        return meal_json(f"Safe {mt} {i}", mt, ("apple",))
    return h


def create(client, auth, **body):
    r = client.post("/api/v1/meal-plans/generate", headers=auth, json=body)
    assert r.status_code == 202, r.text
    return client.get(f"/api/v1/meal-plans/{r.json()['id']}", headers=auth).json()


def test_generates_validated_plan(client, auth):
    llm_mod.set_llm_override(FakeLLM(day_handler()))
    plan = create(client, auth, days=1)
    assert plan["status"] == "ready"
    meals = plan["plan"]["days"][0]["meals"]
    assert [m["meal_type"] for m in meals] == ["breakfast", "lunch", "dinner"]
    assert meals[0]["nutrition_estimate"]["totals"]["kcal"] == 89.0 and meals[0]["origin"] == "ai_generated"
    assert plan["plan"]["days"][0]["daily_nutrition"]["complete"] is True


def test_violating_meal_is_replaced_not_shown(client, auth):
    llm = FakeLLM(day_handler(violating_lunch=True))
    llm_mod.set_llm_override(llm)
    plan = create(client, auth, days=1, allergies=["peanut"])
    assert plan["status"] == "ready"
    titles = [m["title"] for m in plan["plan"]["days"][0]["meals"]]
    assert "Peanut noodles" not in titles and any(t.startswith("Safe lunch") for t in titles)


def test_unfixable_violation_fails_plan_instead_of_returning_it(client, auth):
    def always_bad(title, user, i):
        return {"meals": [meal_json("Prawn curry", "breakfast", ("prawns",))]} if title == "DayData" else meal_json("Prawn curry", "x", ("prawns",))
    llm_mod.set_llm_override(FakeLLM(always_bad))
    plan = create(client, auth, days=1, meals=["breakfast"], allergies=["shellfish"])
    assert plan["status"] == "failed" and "restrictions" in plan["error"] and plan["plan"] == {}


def test_llm_down_marks_failed_not_stuck(client, auth):
    plan = create(client, auth, days=1)  # no LLM override -> Ollama unreachable
    assert plan["status"] == "failed" and "Ollama" in plan["error"]


def test_diet_pattern_enforced(client, auth):
    llm_mod.set_llm_override(FakeLLM(day_handler()))
    plan = create(client, auth, days=1, diet_pattern="vegetarian")
    assert plan["status"] == "ready"
    names = [i["name"] for m in plan["plan"]["days"][0]["meals"] for i in m["ingredients"]]
    assert not any("chicken" in n for n in names)


def test_multi_day_avoids_repeats_and_shopping_list_aggregates(client, auth):
    llm_mod.set_llm_override(FakeLLM(day_handler()))
    plan = create(client, auth, days=2, servings=2, available_ingredients=["banana"])
    assert plan["status"] == "ready" and len(plan["plan"]["days"]) == 2
    sl = client.post(f"/api/v1/meal-plans/{plan['id']}/shopping-list", headers=auth).json()["items"]
    rice = next(i for i in sl if i["name"] == "white rice cooked")
    assert rice["total_grams"] == 100 * 2 * 4 and len(rice["used_in"]) == 4  # 2 meals x 2 days, 2 servings, 100 g
    assert next(i for i in sl if i["name"] == "banana")["have_at_home"] is True
    assert client.get(f"/api/v1/meal-plans/{plan['id']}", headers=auth).json()["shopping_list"]


def test_replace_slot_and_feedback(client, auth):
    llm = FakeLLM(day_handler())
    llm_mod.set_llm_override(llm)
    plan = create(client, auth, days=1)
    client.post(f"/api/v1/meal-plans/{plan['id']}/shopping-list", headers=auth)
    r = client.patch(f"/api/v1/meal-plans/{plan['id']}", headers=auth, json={"replace": {"day": 1, "meal_type": "dinner", "instruction": "lighter"}})
    assert r.status_code == 200
    body = r.json()
    assert body["plan"]["days"][0]["meals"][2]["title"].startswith("Safe dinner") and body["shopping_list"] is None
    fb = client.patch(f"/api/v1/meal-plans/{plan['id']}", headers=auth, json={"feedback": {"day": 1, "meal_type": "lunch", "rating": 4}})
    assert fb.json()["feedback"][0]["rating"] == 4
    assert client.patch(f"/api/v1/meal-plans/{plan['id']}", headers=auth, json={"replace": {"day": 3, "meal_type": "dinner"}}).status_code == 404
    assert client.patch(f"/api/v1/meal-plans/{plan['id']}", headers=auth, json={}).status_code == 422


def test_request_validation_and_isolation(client, auth, auth_b):
    assert client.post("/api/v1/meal-plans/generate", headers=auth, json={"days": 8}).status_code == 422
    assert client.post("/api/v1/meal-plans/generate", headers=auth, json={"meals": ["brunch"]}).status_code == 422
    llm_mod.set_llm_override(FakeLLM(day_handler()))
    plan = create(client, auth, days=1)
    assert client.get(f"/api/v1/meal-plans/{plan['id']}", headers=auth_b).status_code == 404
    assert client.post(f"/api/v1/meal-plans/{plan['id']}/shopping-list", headers=auth_b).status_code == 404
    assert client.get("/api/v1/meal-plans", headers=auth_b).json()["total"] == 0
