from unittest.mock import MagicMock

import anthropic
import pytest
from anthropic.types.beta import BetaMessage, BetaToolUseBlock, BetaUsage
from anthropic.types.beta.parsed_beta_message import ParsedBetaTextBlock

from app.chat.recipe_chat import RecipeChatError, chat_about_recipes
from app.models import Ingredient, Recipe, RecipeIngredient


def _make_recipe(db_session, user_id, title, ingredients):
    recipe = Recipe(
        user_id=user_id,
        source_url="https://youtube.com/watch?v=abc",
        source_platform="youtube",
        title=title,
        steps=["step"],
    )
    db_session.add(recipe)
    db_session.flush()
    for name in ingredients:
        ingredient = Ingredient(name=name)
        db_session.add(ingredient)
        db_session.flush()
        db_session.add(RecipeIngredient(recipe_id=recipe.id, ingredient_id=ingredient.id))
    db_session.flush()
    return recipe


def _usage() -> BetaUsage:
    return BetaUsage(input_tokens=1, output_tokens=1)


def _tool_use_message(pantry: list[str]) -> BetaMessage:
    return BetaMessage(
        id="msg_1",
        type="message",
        role="assistant",
        model="claude-opus-4-8",
        content=[
            BetaToolUseBlock(type="tool_use", id="tu_1", name="match_pantry", input={"pantry": pantry})
        ],
        stop_reason="tool_use",
        stop_sequence=None,
        usage=_usage(),
    )


def _text_message(text: str, *, stop_reason: str = "end_turn") -> BetaMessage:
    # client.beta.messages.tool_runner() calls .parse() under the hood, so real
    # responses carry ParsedBetaTextBlock (with its extra `parsed_output` field),
    # not the plain BetaTextBlock - mirror that here or a bug in stripping that
    # field before replaying history won't be caught.
    return BetaMessage(
        id="msg_2",
        type="message",
        role="assistant",
        model="claude-opus-4-8",
        content=[ParsedBetaTextBlock(type="text", text=text, citations=None, parsed_output=None)],
        stop_reason=stop_reason,
        stop_sequence=None,
        usage=_usage(),
    )


def _mock_client(*responses: BetaMessage) -> anthropic.Anthropic:
    # A real client with only `.parse()` swapped out - the tool runner's own
    # loop logic (client.beta.messages.tool_runner) must run for real, so a
    # fully-mocked client would just return a MagicMock instead of iterating.
    client = anthropic.Anthropic(api_key="test-key")
    client.beta.messages.parse = MagicMock(side_effect=responses)
    return client


def test_chat_calls_match_pantry_tool_and_returns_final_reply(db_session):
    from app.api.deps import get_current_user_id

    user_id = get_current_user_id(db_session)
    _make_recipe(db_session, user_id, "Fried Rice", ["rice", "eggs"])
    _make_recipe(db_session, user_id, "Durian Pie", ["durian"])

    client = _mock_client(
        _tool_use_message(["rice", "eggs"]),
        _text_message("You can make Fried Rice - you have everything you need."),
    )

    result = chat_about_recipes(
        db_session, user_id, "I have rice and eggs, what can I make?", client=client
    )

    assert result.reply == "You can make Fried Rice - you have everything you need."
    assert client.beta.messages.parse.call_count == 2

    # tool actually ran against the DB rather than being hallucinated
    tool_result_message = result.messages[-2]
    assert tool_result_message["role"] == "user"
    tool_result_content = tool_result_message["content"][0]["content"]
    assert "Fried Rice" in tool_result_content
    assert "100%" in tool_result_content
    assert "Durian Pie" in tool_result_content


def test_chat_with_no_recipes_reports_that_to_the_model(db_session):
    from app.api.deps import get_current_user_id

    user_id = get_current_user_id(db_session)

    client = _mock_client(
        _tool_use_message(["rice"]),
        _text_message("You don't have any saved recipes yet."),
    )

    result = chat_about_recipes(db_session, user_id, "I have rice, what can I make?", client=client)

    assert "don't have any saved recipes" in result.reply


def test_chat_skips_tool_call_when_not_needed(db_session):
    from app.api.deps import get_current_user_id

    user_id = get_current_user_id(db_session)

    client = _mock_client(_text_message("Sure, what ingredients do you have on hand?"))

    result = chat_about_recipes(db_session, user_id, "What can I cook tonight?", client=client)

    assert result.reply == "Sure, what ingredients do you have on hand?"
    assert client.beta.messages.parse.call_count == 1


def test_chat_raises_on_refusal(db_session):
    from app.api.deps import get_current_user_id

    user_id = get_current_user_id(db_session)
    client = _mock_client(_text_message("", stop_reason="refusal"))

    with pytest.raises(RecipeChatError):
        chat_about_recipes(db_session, user_id, "anything", client=client)


def test_chat_passes_prior_history_to_the_model(db_session):
    from app.api.deps import get_current_user_id

    user_id = get_current_user_id(db_session)
    client = _mock_client(_text_message("Got it, noted you like spicy food."))

    history = [
        {"role": "user", "content": "I love spicy food."},
        {"role": "assistant", "content": [{"type": "text", "text": "Noted!"}]},
    ]

    result = chat_about_recipes(
        db_session, user_id, "Remember that for next time.", history=history, client=client
    )

    _, kwargs = client.beta.messages.parse.call_args
    sent_messages = kwargs["messages"]
    assert sent_messages[0] == history[0]
    assert sent_messages[1] == history[1]
    assert sent_messages[2] == {"role": "user", "content": "Remember that for next time."}
    # returned history includes this turn, ready to be replayed on the next call
    assert result.messages[-1]["content"][0]["text"] == "Got it, noted you like spicy food."


def test_chat_history_omits_parsed_output_so_it_replays_cleanly(db_session):
    # Regression test: tool_runner's .parse() call returns ParsedBetaTextBlock,
    # whose extra `parsed_output` field the API rejects ("Extra inputs are not
    # permitted") if echoed back verbatim as a later turn's message content.
    from app.api.deps import get_current_user_id

    user_id = get_current_user_id(db_session)
    client = _mock_client(_text_message("Sure thing."))

    result = chat_about_recipes(db_session, user_id, "hello", client=client)

    assistant_message = result.messages[-1]
    for block in assistant_message["content"]:
        assert "parsed_output" not in block


@pytest.mark.integration
def test_chat_against_real_api(db_session):
    from app.api.deps import get_current_user_id

    user_id = get_current_user_id(db_session)
    _make_recipe(db_session, user_id, "Fried Rice", ["rice", "eggs"])

    result = chat_about_recipes(db_session, user_id, "I have rice and eggs, what can I make?")

    assert "Fried Rice" in result.reply
