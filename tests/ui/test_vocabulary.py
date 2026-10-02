from typing import get_args

from app.parsing.recipe_parser import Cuisine, MealType
from app.ui.vocabulary import CUISINES, MEAL_TYPES


# The UI keeps its own copy of these lists on purpose (ADR-0009) - this is what
# stops that copy silently drifting from what the API actually accepts.
def test_ui_cuisines_match_backend():
    assert CUISINES == list(get_args(Cuisine))


def test_ui_meal_types_match_backend():
    assert MEAL_TYPES == list(get_args(MealType))

