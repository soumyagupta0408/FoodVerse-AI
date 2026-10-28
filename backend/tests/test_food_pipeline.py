import io

from app.core.config import get_settings
from app.ml import registry
from tests.conftest import FakeFreshRegistry, FakeRecognizer, make_image


def upload(client, auth, path, data, name="x.png", **form):
    return client.post(path, headers=auth, files={"file": (name, io.BytesIO(data), "application/octet-stream")}, data=form)


def test_recognition_without_model_is_503_not_fake(client, auth, png):
    r = upload(client, auth, "/api/v1/food/recognize", png)
    assert r.status_code == 503 and r.json()["error"]["code"] == "model_unavailable"


def test_recognition_and_correction(client, auth, png):
    registry.set_override("recognizer", FakeRecognizer())
    r = upload(client, auth, "/api/v1/food/recognize", png)
    assert r.status_code == 201
    body = r.json()
    assert body["result"]["top"]["label"] == "pizza" and len(body["result"]["predictions"]) == 3
    assert body["model_name"] == "fake-food-model" and body["result"]["multi_item_supported"] is False
    got = client.get(f"/api/v1/food/recognize/{body['id']}", headers=auth)
    assert got.json()["id"] == body["id"]
    fixed = client.patch(f"/api/v1/food/recognize/{body['id']}/correction", headers=auth, json={"food_name": "hamburger"})
    assert fixed.json()["corrected"] == {"food_name": "hamburger"}


def test_low_confidence_adds_note(client, auth, png):
    from app.ml.base import Prediction

    registry.set_override("recognizer", FakeRecognizer([Prediction("pizza", 0.2)]))
    notes = upload(client, auth, "/api/v1/food/recognize", png).json()["result"]["notes"]
    assert any("Low confidence" in n for n in notes)


def test_image_validation(client, auth):
    registry.set_override("recognizer", FakeRecognizer())
    assert upload(client, auth, "/api/v1/food/recognize", b"not an image").status_code == 422
    assert upload(client, auth, "/api/v1/food/recognize", b"").status_code == 422
    assert upload(client, auth, "/api/v1/food/recognize", make_image("PNG")[:200]).status_code == 422  # truncated
    gif = io.BytesIO()
    from PIL import Image

    Image.new("RGB", (10, 10)).save(gif, format="GIF")
    assert upload(client, auth, "/api/v1/food/recognize", gif.getvalue()).status_code == 422  # unsupported format


def test_upload_size_limit(client, auth, png, monkeypatch):
    registry.set_override("recognizer", FakeRecognizer())
    monkeypatch.setattr(get_settings(), "max_image_mb", 0)
    assert upload(client, auth, "/api/v1/food/recognize", png).status_code == 413


def test_user_isolation(client, auth, auth_b, png):
    registry.set_override("recognizer", FakeRecognizer())
    a = upload(client, auth, "/api/v1/food/recognize", png).json()
    assert client.get(f"/api/v1/food/recognize/{a['id']}", headers=auth_b).status_code == 404
    assert client.get(f"/api/v1/media/{a['media_id']}", headers=auth_b).status_code == 404
    assert client.patch(f"/api/v1/food/recognize/{a['id']}/correction", headers=auth_b, json={"food_name": "x"}).status_code == 404
    assert client.post("/api/v1/nutrition/analyze", headers=auth_b, json={"recognition_id": a["id"]}).status_code == 404
    assert client.get(f"/api/v1/media/{a['media_id']}", headers=auth).status_code == 200


def test_filename_cannot_escape_storage(client, auth, png):
    registry.set_override("recognizer", FakeRecognizer())
    r = upload(client, auth, "/api/v1/food/recognize", png, name="../../etc/passwd.png")
    assert r.status_code == 201
    media = client.get(f"/api/v1/media/{r.json()['media_id']}", headers=auth)
    assert media.status_code == 200 and media.headers["content-type"] == "image/png"


# ---- nutrition ----
def test_nutrition_scales_per_100g(client, auth):
    r = client.post("/api/v1/nutrition/analyze", headers=auth, json={"food_name": "banana", "grams": 200})
    res = r.json()["result"]
    assert r.status_code == 201 and res["matched"]
    assert res["nutrients"]["kcal"] == 178.0 and res["nutrients"]["carbs_g"] == 45.6
    assert res["portion"] == {"grams": 200.0, "basis": "user", "estimated": False, "serving_description": None}
    assert 0 <= res["health_score"]["score"] <= 100 and res["health_score"]["criteria"]


def test_nutrition_default_serving_is_flagged_estimated(client, auth):
    res = client.post("/api/v1/nutrition/analyze", headers=auth, json={"food_name": "banana"}).json()["result"]
    assert res["portion"]["estimated"] is True and res["portion"]["grams"] == 118.0
    assert any("estimate" in n.lower() for n in res["notes"])


def test_unknown_nutrients_are_none_not_zero(client, auth):
    res = client.post("/api/v1/nutrition/analyze", headers=auth, json={"food_name": "fried rice", "grams": 100}).json()["result"]
    assert res["nutrients"]["fiber_g"] is None and res["nutrients"]["sugar_g"] is None
    assert set(res["unknown_nutrients"]) == {"fiber_g", "sugar_g"}
    assert "fibre" in res["health_score"]["skipped"]
    boiled = client.post("/api/v1/nutrition/analyze", headers=auth, json={"food_name": "boiled egg", "grams": 100}).json()["result"]
    assert boiled["nutrients"]["fiber_g"] == 0.0  # a recorded zero stays zero


def test_nutrition_no_match_estimates_nothing(client, auth):
    res = client.post("/api/v1/nutrition/analyze", headers=auth, json={"food_name": "zzqx unknown dish"}).json()["result"]
    assert res["matched"] is False and "nutrients" not in res


def test_nutrition_from_recognition_uses_correction(client, auth, png):
    registry.set_override("recognizer", FakeRecognizer())
    rec = upload(client, auth, "/api/v1/food/recognize", png).json()
    client.patch(f"/api/v1/food/recognize/{rec['id']}/correction", headers=auth, json={"food_name": "banana"})
    n = client.post("/api/v1/nutrition/analyze", headers=auth, json={"recognition_id": rec["id"], "grams": 100}).json()
    assert n["result"]["food"]["name"] == "banana" and n["parent_id"] == rec["id"]
    assert client.get(f"/api/v1/nutrition/{n['id']}", headers=auth).status_code == 200


def test_nutrition_validation(client, auth):
    assert client.post("/api/v1/nutrition/analyze", headers=auth, json={}).status_code == 422
    assert client.post("/api/v1/nutrition/analyze", headers=auth, json={"food_name": "banana", "grams": -5}).status_code == 422


# ---- freshness ----
def test_freshness_unsupported_category(client, auth, png):
    registry.set_override("freshness", FakeFreshRegistry())
    res = upload(client, auth, "/api/v1/freshness/analyze", png, food_category="paneer").json()["result"]
    assert res["state"] == "unable_to_determine" and "No freshness model" in res["reason"] and res["safety_note"]


def test_freshness_no_models_installed(client, auth, png):
    registry.set_override("freshness", FakeFreshRegistry("none"))
    res = upload(client, auth, "/api/v1/freshness/analyze", png, food_category="banana").json()["result"]
    assert res["state"] == "unable_to_determine" and "No freshness models are installed" in res["reason"]


def test_freshness_classification_and_display_names(client, auth, png):
    for probs, expected in [({"fresh": 0.9, "moderate": 0.07, "spoiled": 0.03}, "Fresh"),
                            ({"fresh": 0.1, "moderate": 0.8, "spoiled": 0.1}, "Moderately Fresh"),
                            ({"fresh": 0.05, "moderate": 0.05, "spoiled": 0.9}, "Spoiled")]:
        registry.set_override("freshness", FakeFreshRegistry(probs))
        res = upload(client, auth, "/api/v1/freshness/analyze", png, food_category="Banana").json()["result"]
        assert res["display"] == expected and res["safety_note"] and res["recommendation"]


def test_freshness_low_confidence_is_not_forced(client, auth, png):
    registry.set_override("freshness", FakeFreshRegistry({"fresh": 0.4, "moderate": 0.35, "spoiled": 0.25}))
    res = upload(client, auth, "/api/v1/freshness/analyze", png, food_category="banana").json()["result"]
    assert res["state"] == "unable_to_determine" and res["confidence"] is None


def test_freshness_poor_quality_image(client, auth):
    registry.set_override("freshness", FakeFreshRegistry())
    dark = make_image(noisy=False)
    res = upload(client, auth, "/api/v1/freshness/analyze", dark, food_category="banana").json()["result"]
    assert res["state"] == "unable_to_determine" and "quality" in res["reason"]


def test_freshness_requires_category(client, auth, png):
    registry.set_override("freshness", FakeFreshRegistry())
    res = upload(client, auth, "/api/v1/freshness/analyze", png).json()["result"]
    assert res["state"] == "unable_to_determine" and "category" in res["reason"].lower()
