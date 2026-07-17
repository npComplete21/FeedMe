from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from app.parsing import recipe_parser
from app.parsing.recipe_parser import ParsedIngredient, ParsedRecipe, RecipeParseError, parse_recipe

CAPTION = (
    "Weeknight fried rice! You'll need 2 cups cooked rice, 2 eggs, 1/2 cup "
    "frozen peas and carrots, and soy sauce. Scramble the eggs, add the rice "
    "and veggies, stir in soy sauce, done in 10 minutes."
)


def _mock_client(*, stop_reason: str, parsed_output=None) -> MagicMock:
    client = MagicMock()
    client.messages.parse.return_value = MagicMock(
        stop_reason=stop_reason, parsed_output=parsed_output
    )
    return client


def test_parse_recipe_returns_structured_output():
    expected = ParsedRecipe(
        title="Weeknight Fried Rice",
        ingredients=[
            ParsedIngredient(name="rice", quantity="2 cups", raw_text="2 cups cooked rice"),
            ParsedIngredient(name="eggs", quantity="2", raw_text="2 eggs"),
        ],
        steps=["Scramble the eggs", "Add rice and veggies", "Stir in soy sauce"],
    )
    client = _mock_client(stop_reason="end_turn", parsed_output=expected)

    result = parse_recipe(CAPTION, client=client)

    assert result == expected


def test_parse_recipe_calls_model_with_expected_shape():
    client = _mock_client(
        stop_reason="end_turn",
        parsed_output=ParsedRecipe(title="X", ingredients=[], steps=[]),
    )

    parse_recipe(CAPTION, client=client)

    _, kwargs = client.messages.parse.call_args
    assert kwargs["model"] == recipe_parser.MODEL
    assert kwargs["output_format"] is ParsedRecipe
    assert kwargs["messages"] == [{"role": "user", "content": CAPTION}]


def test_parsed_recipe_accepts_tags():
    recipe = ParsedRecipe(
        title="Bibimbap",
        ingredients=[],
        steps=[],
        cuisine="korean",
        meal_type="dinner",
        cook_time_minutes=25,
    )

    assert recipe.cuisine == "korean"
    assert recipe.meal_type == "dinner"
    assert recipe.cook_time_minutes == 25


def test_parsed_recipe_rejects_cuisine_outside_the_allowed_set():
    with pytest.raises(ValidationError):
        ParsedRecipe(title="X", ingredients=[], steps=[], cuisine="klingon")


def test_parsed_recipe_rejects_meal_type_outside_the_allowed_set():
    with pytest.raises(ValidationError):
        ParsedRecipe(title="X", ingredients=[], steps=[], meal_type="elevenses")


def test_parse_recipe_raises_on_refusal():
    client = _mock_client(stop_reason="refusal", parsed_output=None)

    with pytest.raises(RecipeParseError):
        parse_recipe(CAPTION, client=client)


@pytest.mark.integration
def test_parse_recipe_against_real_api():
    result = parse_recipe(CAPTION)

    assert result.title
    assert result.steps
    assert any("rice" in ing.name.lower() for ing in result.ingredients)
