"""Deterministic allergy / exclusion / diet checks. Never delegated to the LLM.

Limits (documented to users): matching works on ingredient *names*. It cannot see allergens
hidden inside a compound product (a sauce, a stock cube) unless the name says so.
"""
import re
from collections.abc import Iterable

ALLERGEN_GROUPS: dict[str, list[str]] = {
    "peanut": ["peanut", "groundnut", "arachis"],
    "tree nut": ["almond", "cashew", "walnut", "pecan", "pistachio", "hazelnut", "macadamia", "brazil nut", "pine nut", "chestnut", "tree nut", "marzipan", "praline", "nut"],
    "milk": ["milk", "butter", "buttermilk", "cheese", "cream", "yogurt", "yoghurt", "curd", "ghee", "paneer", "whey", "casein", "custard", "ice cream", "dairy", "mozzarella", "parmesan", "cheddar", "ricotta", "khoa", "khoya"],
    "egg": ["egg", "eggs", "mayonnaise", "mayo", "meringue", "albumen"],
    "soy": ["soy", "soya", "soybean", "tofu", "tempeh", "edamame", "miso", "soy sauce", "tamari"],
    "wheat": ["wheat", "flour", "bread", "pasta", "spaghetti", "noodle", "semolina", "suji", "rava", "couscous", "bulgur", "seitan", "atta", "maida", "breadcrumb", "tortilla", "cracker", "barley", "rye"],
    "gluten": ["wheat", "flour", "bread", "pasta", "spaghetti", "noodle", "semolina", "suji", "rava", "couscous", "bulgur", "seitan", "atta", "maida", "breadcrumb", "barley", "rye", "malt", "gluten"],
    "fish": ["fish", "salmon", "tuna", "cod", "haddock", "anchovy", "sardine", "mackerel", "trout", "tilapia", "pomfret", "hilsa", "fish sauce"],
    "shellfish": ["shrimp", "prawn", "crab", "lobster", "clam", "mussel", "oyster", "scallop", "squid", "shellfish", "crayfish"],
    "sesame": ["sesame", "tahini", "til", "gingelly"],
}

MEAT = ["chicken", "beef", "pork", "lamb", "mutton", "turkey", "duck", "bacon", "ham", "sausage", "salami", "goat", "veal", "meat", "mince", "steak", "gelatin", "lard", "pepperoni", "prosciutto"]
FISH_SEAFOOD = ALLERGEN_GROUPS["fish"] + ALLERGEN_GROUPS["shellfish"]
ANIMAL_OTHER = ["egg", "eggs", "honey", "milk", "butter", "cheese", "cream", "yogurt", "yoghurt", "curd", "ghee", "paneer", "whey", "casein", "mayonnaise"]

DIET_GROUPS: dict[str, list[str]] = {
    "vegetarian": MEAT + FISH_SEAFOOD,
    "pescatarian": MEAT,
    "vegan": MEAT + FISH_SEAFOOD + ANIMAL_OTHER,
}


def normalize(text: str) -> str:
    text = re.sub(r"[^a-z0-9\s'-]", " ", text.lower())
    return re.sub(r"\s+", " ", text).strip()


def _pattern(term: str) -> re.Pattern:
    return re.compile(rf"\b{re.escape(term)}(?:s|es)?\b")


def terms_for(allergies: Iterable[str] = (), excluded: Iterable[str] = (), diet: str | None = None) -> dict[str, list[str]]:
    """Return {reason: [terms]} for every active restriction."""
    out: dict[str, list[str]] = {}
    for a in allergies:
        key = normalize(a)
        if key in ALLERGEN_GROUPS:
            out[f"allergy: {key}"] = ALLERGEN_GROUPS[key]
        elif key:
            out[f"allergy: {key}"] = [key]  # unknown allergen: match the literal word, never silently ignore
    for e in excluded:
        key = normalize(e)
        if key:
            out[f"excluded: {key}"] = ALLERGEN_GROUPS.get(key, [key])
    if diet and diet in DIET_GROUPS:
        out[f"diet: {diet}"] = DIET_GROUPS[diet]
    return out


DAIRY_WORDS = {"milk", "butter", "cream", "cheese", "yogurt", "yoghurt", "curd", "ice cream"}
# "coconut milk", "oat milk", "peanut butter", "cocoa butter" are not dairy; other checks (e.g. peanut) still see the full name.
_PLANT_DAIRY = re.compile(r"\b(?:coconut|oat|rice|soy|soya|almond|cashew|hemp|pea|plant[- ]based|vegan|cocoa|cacao|peanut|shea|nut|hazelnut)\s+(?:milk|butter|cream|cheese|yogurt|yoghurt|curd|ice cream)s?\b")


def find_violations(ingredient_names: Iterable[str], restrictions: dict[str, list[str]]) -> list[dict]:
    """List every (ingredient, reason, matched term) conflict. Empty list means no conflict was detected."""
    violations = []
    for name in ingredient_names:
        norm = normalize(name)
        dairy_norm = _PLANT_DAIRY.sub(" ", norm)
        for reason, terms in restrictions.items():
            for term in terms:
                haystack = dairy_norm if term in DAIRY_WORDS else norm
                if _pattern(term).search(haystack):
                    violations.append({"ingredient": name, "reason": reason, "matched_term": term})
                    break
    return violations


ALLERGEN_CAVEAT = (
    "Checked against ingredient names only. Hidden allergens in packaged or compound ingredients "
    "(sauces, stock, spice blends) cannot be detected: read product labels before cooking."
)
