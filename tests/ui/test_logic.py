from app.ui.logic import (
    cuisine_counts,
    cuisine_label,
    detect_platform,
    ingredients_to_text,
    normalize_url,
    parse_ingredients_text,
    parse_pantry,
    recipe_tags,
    search_recipes,
)


def test_detect_platform_youtube_variants():
    assert detect_platform("https://www.youtube.com/shorts/abc") == "youtube"
    assert detect_platform("https://youtu.be/abc") == "youtube"
    assert detect_platform("https://m.youtube.com/watch?v=1") == "youtube"


def test_detect_platform_instagram():
    assert detect_platform("https://www.instagram.com/reel/x/") == "instagram"
    assert detect_platform("https://instagram.com/p/x/") == "instagram"


def test_detect_platform_lookalike_host_is_website():
    assert detect_platform("https://notyoutube.com/x") == "website"
    assert detect_platform("https://youtube.com.evil.io/x") == "website"


def test_detect_platform_other_site_is_website():
    assert detect_platform("https://www.seriouseats.com/pasta") == "website"


def test_normalize_url_adds_scheme_and_trims():
    assert normalize_url("  youtu.be/abc ") == "https://youtu.be/abc"


def test_normalize_url_keeps_existing_scheme():
    assert normalize_url("http://example.com/r") == "http://example.com/r"


def test_normalize_url_rejects_non_links():
    for raw in ["", "   ", "chicken curry", "hello"]:
        assert normalize_url(raw) is None


def test_normalize_url_rejects_schemes_other_than_http_and_https():
    for raw in ["ftp://a.com", "file://x.y/z", "javascript://a.b/%0Aalert(1)", "mailto://a.com"]:
        assert normalize_url(raw) is None


def test_normalize_url_scheme_check_is_case_insensitive():
    assert normalize_url("HTTPS://Example.com/r") == "HTTPS://Example.com/r"


RECIPES = [
    {"title": "Chicken Curry", "ingredients": [{"name": "Chicken"}, {"name": "Coconut milk"}]},
    {"title": "Pasta", "ingredients": [{"name": "Spaghetti"}, {"name": "Garlic"}]},
    {"title": "Garlic Bread", "ingredients": [{"name": "Baguette"}]},
]


def test_search_matches_title_and_ingredient_case_insensitively():
    assert [r["title"] for r in search_recipes(RECIPES, "CURRY")] == ["Chicken Curry"]
    assert [r["title"] for r in search_recipes(RECIPES, "garlic")] == ["Pasta", "Garlic Bread"]


def test_search_blank_query_returns_everything_in_order():
    assert search_recipes(RECIPES, "") == RECIPES
    assert search_recipes(RECIPES, "   ") == RECIPES


def test_search_no_match_returns_empty():
    assert search_recipes(RECIPES, "zzz") == []


def test_cuisine_counts_skips_missing_cuisine():
    recipes = [
        {"cuisine": "italian"},
        {"cuisine": "italian"},
        {"cuisine": "thai"},
        {"cuisine": None},
        {},
    ]
    assert cuisine_counts(recipes) == {"italian": 2, "thai": 1}


def test_cuisine_label():
    assert cuisine_label("middle_eastern") == "Middle Eastern"
    assert cuisine_label("thai") == "Thai"


def test_recipe_tags_order_and_omissions():
    full = {"cuisine": "middle_eastern", "meal_type": "dinner", "cook_time_minutes": 30, "rating": 4}
    assert recipe_tags(full) == ["Middle Eastern", "Dinner", "30 min", "★★★★"]
    assert recipe_tags({"cuisine": None, "meal_type": "lunch", "cook_time_minutes": None}) == ["Lunch"]
    assert recipe_tags({}) == []


def test_parse_ingredients_roundtrip():
    ingredients = [
        {"name": "flour", "quantity": "2 cups"},
        {"name": "salt", "quantity": None},
    ]
    text = ingredients_to_text(ingredients)
    assert text == "flour, 2 cups\nsalt"
    assert parse_ingredients_text(text) == ingredients


def test_parse_ingredients_skips_blank_lines_and_empty_quantity():
    assert parse_ingredients_text("\n a, \n\n b , 1 tsp\n") == [
        {"name": "a", "quantity": None},
        {"name": "b", "quantity": "1 tsp"},
    ]


def test_parse_pantry_drops_blanks():
    assert parse_pantry(" rice, , eggs ,garlic,") == ["rice", "eggs", "garlic"]
    assert parse_pantry("") == []
