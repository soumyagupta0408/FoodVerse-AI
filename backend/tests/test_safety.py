from app.services import safety


def bad(names, **kw):
    return safety.find_violations(names, safety.terms_for(**kw))


def test_peanut_allergy_catches_derivatives():
    hits = bad(["Peanut butter", "groundnut oil", "roasted peanuts", "rice"], allergies=["Peanut"])
    assert {h["ingredient"] for h in hits} == {"Peanut butter", "groundnut oil", "roasted peanuts"}


def test_word_boundaries_avoid_false_positives():
    assert bad(["nutmeg", "butternut squash", "coconut"], allergies=["tree nut"]) == []
    assert bad(["almond flour"], allergies=["tree nut"])


def test_plant_milks_are_not_dairy_but_peanut_butter_still_peanut():
    assert bad(["coconut milk", "oat milk", "cocoa butter"], allergies=["milk"]) == []
    assert bad(["peanut butter"], allergies=["milk"]) == []
    assert bad(["peanut butter"], allergies=["peanut"])
    assert bad(["butter", "whole milk", "Paneer cubes"], allergies=["milk"])


def test_vegan_and_vegetarian_diets():
    assert bad(["chicken stock", "honey", "tofu"], diet="vegan")
    assert {h["ingredient"] for h in bad(["chicken", "cheese", "salmon"], diet="vegetarian")} == {"chicken", "salmon"}
    assert bad(["salmon"], diet="pescatarian") == [] and bad(["bacon"], diet="pescatarian")


def test_unknown_allergen_matches_literally_never_ignored():
    assert bad(["fresh kiwi slices"], allergies=["kiwi"])


def test_gluten_and_wheat():
    assert bad(["whole wheat bread", "spaghetti"], allergies=["gluten"])
    assert bad(["rice noodles"], allergies=["gluten"])  # conservative: 'noodle' is flagged, user must check the label


def test_excluded_ingredients():
    assert bad(["Mushrooms"], excluded=["mushroom"])
