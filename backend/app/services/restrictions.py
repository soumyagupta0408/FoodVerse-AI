from app.db.models import User
from app.services import safety


def resolve(user: User, *, allergies=(), excluded=(), diet: str | None = None, use_profile: bool = True) -> dict:
    """Merge profile and request restrictions into one deterministic rule set."""
    al, ex, dt = list(allergies), list(excluded), diet
    if use_profile and user.profile:
        al += list(user.profile.allergies or [])
        ex += list(user.profile.excluded_ingredients or [])
        dt = dt or user.profile.diet_pattern
    terms = safety.terms_for(al, ex, dt)
    return {"terms": terms, "reasons": sorted(terms), "allergies": sorted(set(al)), "excluded": sorted(set(ex)), "diet": dt}


def prompt_text(rules: dict) -> str:
    if not rules["reasons"]:
        return "No dietary restrictions."
    return "Strict restrictions (must not appear anywhere, not even as a garnish or optional item): " + "; ".join(rules["reasons"])
