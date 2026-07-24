# ADR 0011: Recipe chat uses tool-use over the existing match engine, not free-text LLM reasoning

Status: Accepted

## Context

Phase 1.4 adds conversational search: "I have chicken, rice, broccoli - what should I make?" Three
approaches were considered for how the LLM gets from that sentence to an answer grounded in the
user's actual saved recipes:

1. **Dump the whole recipe collection into the system prompt** and let the model reason over it in
   free text. Simplest to wire up, but reintroduces exactly the failure mode ADR-0008 fixed for
   ingredient matching: the model doing fuzzy, unauditable comparison instead of calling the same
   deterministic `normalize_ingredient_name()` / `match_recipes()` logic every other code path uses.
   Nothing stops it from citing a match ratio it invented or a recipe title it misremembered from a
   long context.
2. **NL-to-structured extraction**, mirroring `recipe_parser.py`: one model call turns "I have
   chicken, rice, broccoli" into a `pantry: list[str]`, then run it through the existing `/match`
   deterministically and hand the structured result back as the reply, possibly with a second call
   to phrase it conversationally. Keeps matching deterministic, but is a fixed one-shot intent -
   doesn't extend to follow-ups ("what if I don't have broccoli?", "give me something with less
   cook time") without hand-rolling intent-detection for every new phrasing.
3. **Tool use**: give Claude a `match_pantry` tool that wraps the existing, already-tested
   `match_recipes()` engine against the current user's actual saved recipes. Claude extracts
   ingredients from the conversation, calls the tool to get real match data, and writes the
   response - grounded in whatever the tool actually returned, not the model's own recall.

## Decision

Tool use, via the Anthropic SDK's tool runner (`client.beta.messages.tool_runner`, `app/chat/
recipe_chat.py`). One tool, `match_pantry(pantry: list[str])`, queries the current user's `Recipe`
rows and calls the same `match_recipes()` function `/match` uses - same normalization, same ranking,
same "zero-ingredient recipes rank last" tie-break as ADR-0008 established. The system prompt tells
Claude to call the tool rather than recall recipes from its own context, and to cite the tool's
match ratios and missing-ingredient lists rather than inventing its own.

The API (`POST /chat`) is stateless, matching every other endpoint (ADR-0004's thin-HTTP-client UI):
it takes `message` + an opaque `history` list and returns `reply` + the updated `history` for the
caller to replay on the next turn. `history` isn't modeled field-by-field in the API schema - it's
Anthropic's message/content-block wire format, round-tripped as `list[dict]`, not reinterpreted by
FastAPI or the UI.

## Consequences

- Gain: the chat's answers are grounded in the same deterministic matching engine as `/match` -
  a recipe the tool didn't return can't appear in the reply, and a cited match ratio is always the
  real one, not a plausible-sounding guess over a long context.
- Gain: extends to follow-up turns for free. Because it's a real conversation with tool access
  rather than a single fixed intent, "what if I don't have broccoli?" or "what's the fastest one?"
  work by Claude calling `match_pantry` again (or just answering from the already-returned tool
  result) - no new intent-parsing code needed.
- Cost: pulls in the `tool_runner` beta surface (`client.beta.messages.*`) rather than the plain
  `messages.create()` used elsewhere in the codebase (`recipe_parser.py`) - a wider API surface to
  track through Anthropic SDK upgrades.
- Cost: no persisted chat history - conversations live in the Streamlit session only and are lost on
  page reload, same "wait until it hurts" call as everywhere else in Phase 1. If cross-session
  history becomes wanted, it's an additive DB table, not a redesign of this flow.
- Revisit if: the single `match_pantry` tool stops being enough (e.g. "recommend something Korean I
  haven't made in a while" needs filtering by cuisine/history, not just pantry matching) - the
  tool-use shape scales to more tools without changing the chat loop, so extending it should mean
  adding tools, not rearchitecting.
