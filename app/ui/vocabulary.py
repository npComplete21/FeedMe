"""Allowed cuisine/meal-type values, as the UI offers them.

A copy of Cuisine/MealType in app/parsing/recipe_parser.py, not an import: the
UI is a pure HTTP client of the API (ADR-0004), and importing backend code here
would drag anthropic/sqlalchemy into the UI image (ADR-0012). Kept in its own
side-effect-free module so tests/ui/test_vocabulary.py can compare the two and
fail CI the moment they drift (ADR-0009).
"""

CUISINES = [
    "italian", "mexican", "chinese", "japanese", "korean", "indian", "thai",
    "vietnamese", "american", "mediterranean", "french", "middle_eastern", "other",
]
MEAL_TYPES = ["breakfast", "lunch", "dinner", "snack", "dessert", "drink", "appetizer"]
