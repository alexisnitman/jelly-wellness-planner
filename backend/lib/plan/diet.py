"""Heuristic diet and allergy cross-check for recipes (CLAUDE.md rule 5: respect stated diets and allergies).

The user's profile notes are free text, so this is deliberately conservative: any allergen or diet word that
appears in the notes is treated as something to AVOID, and any recipe ingredient matching it is a conflict.
It can reject too much (e.g. "I love peanut butter" would block peanuts) but it should not miss an obvious
conflict. It is a safety net on top of the model following the instructions, not a medical check.
"""

from __future__ import annotations

import re

ALLERGEN_WORDS: dict[str, list[str]] = {
    "peanut": ["peanut", "groundnut"],
    "tree nut": ["almond", "walnut", "cashew", "pecan", "pistachio", "hazelnut", "macadamia", "pine nut", "pesto", "nut butter", "nutella"],
    "milk": ["milk", "cheese", "butter", "cream", "yogurt", "yoghurt", "ghee", "whey", "parmesan", "mozzarella", "feta", "ricotta", "cheddar", "paneer", "kefir"],
    "egg": ["egg", "mayo", "mayonnaise", "aioli", "meringue"],
    "wheat": ["wheat", "flour", "bread", "pasta", "noodle", "couscous", "breadcrumb", "tortilla", "pita", "bulgur", "seitan", "barley", "rye", "spaghetti"],
    "soy": ["soy", "tofu", "edamame", "miso", "tamari", "tempeh"],
    "fish": ["salmon", "tuna", "cod", "anchovy", "anchovies", "sardine", "tilapia", "halibut", "trout", "fish sauce", "mackerel"],
    "shellfish": ["shrimp", "prawn", "crab", "lobster", "scallop", "clam", "mussel", "oyster", "crawfish", "squid", "calamari"],
    "sesame": ["sesame", "tahini"],
}
MEAT = ["beef", "pork", "bacon", "ham", "sausage", "chicken", "turkey", "lamb", "duck", "veal", "steak", "salami", "pepperoni", "meatball", "ground meat", "mince", "prosciutto", "gelatin", "lard"]
FISH_SHELLFISH = ALLERGEN_WORDS["fish"] + ALLERGEN_WORDS["shellfish"]
ANIMAL_PRODUCTS = ALLERGEN_WORDS["milk"] + ALLERGEN_WORDS["egg"] + ["honey"]

# notes wording -> (label, words to avoid)
TRIGGERS: list[tuple[str, str, list[str]]] = [
    (r"\bpeanut", "peanut", ALLERGEN_WORDS["peanut"]),
    (r"\b(tree[- ]?nut|nut allerg|nuts?\b|almond|walnut|cashew|pecan|pistachio|hazelnut)", "tree nuts", ALLERGEN_WORDS["tree nut"] + ALLERGEN_WORDS["peanut"]),
    (r"\b(milk|dairy|lactose)", "dairy", ALLERGEN_WORDS["milk"]),
    (r"\begg", "egg", ALLERGEN_WORDS["egg"]),
    (r"\b(wheat|gluten|celiac|coeliac)", "wheat/gluten", ALLERGEN_WORDS["wheat"]),
    (r"\bsoy", "soy", ALLERGEN_WORDS["soy"]),
    (r"\bshellfish", "shellfish", ALLERGEN_WORDS["shellfish"]),
    (r"\b(fish allerg|allergic to fish|no fish|fish[- ]free)", "fish", ALLERGEN_WORDS["fish"]),
    (r"\bsesame", "sesame", ALLERGEN_WORDS["sesame"]),
    (r"\bvegan", "vegan diet", MEAT + FISH_SHELLFISH + ANIMAL_PRODUCTS),
    (r"\bvegetarian", "vegetarian diet", MEAT + FISH_SHELLFISH),
    (r"\bpescatarian", "pescatarian diet", MEAT),
    (r"\b(no|avoid|without)\s+pork|\bpork[- ]free|\bhalal|\bkosher", "pork", ["pork", "bacon", "ham", "lard", "prosciutto", "gelatin"]),
    (r"\b(no|avoid|without)\s+beef", "beef", ["beef", "steak", "veal"]),
]


def avoid_list(notes: str) -> list[tuple[str, list[str]]]:
    low = (notes or "").lower()
    out: list[tuple[str, list[str]]] = []
    for pattern, label, words in TRIGGERS:
        if re.search(pattern, low) and label not in [o[0] for o in out]:
            out.append((label, words))
    return out


def recipe_conflicts(ingredients: list[str], notes: str) -> list[str]:
    """Human-readable conflicts between a recipe's ingredients and the user's diet/allergy notes."""
    text = " ".join(ingredients).lower()
    found: list[str] = []
    for label, words in avoid_list(notes):
        # whole words (plural allowed) so "minced garlic" is not mince and "a bunch of cilantro" is not a bun
        hit = next((w for w in words if re.search(rf"\b{re.escape(w)}(?:s|es)?\b", text)), None)
        if hit:
            found.append(f"'{hit}' conflicts with your {label} note")
    return found
