from app.ingredients.normalization import normalize_ingredient_name


def test_lowercases_and_strips_whitespace():
    assert normalize_ingredient_name("  Rice  ") == "rice"


def test_strips_parenthetical_prep_notes():
    assert normalize_ingredient_name("onion (for cooking)") == "onion"
    assert normalize_ingredient_name("onion (for blender)") == "onion"


def test_parenthetical_and_plural_variants_converge():
    # the exact real-world bug: three different-looking ingredients that
    # should all be the same pantry item
    assert (
        normalize_ingredient_name("onions")
        == normalize_ingredient_name("onion (for cooking)")
        == normalize_ingredient_name("onion (for blender)")
        == "onion"
    )


def test_known_synonyms_map_to_one_canonical_name():
    assert normalize_ingredient_name("scallion") == "green onion"
    assert normalize_ingredient_name("scallions") == "green onion"
    assert normalize_ingredient_name("spring onions") == "green onion"


def test_synonym_lookup_applies_after_paren_stripping():
    assert normalize_ingredient_name("Scallions (chopped)") == "green onion"


def test_unknown_ingredient_is_left_unchanged_besides_casing():
    assert normalize_ingredient_name("Rice") == "rice"
    assert normalize_ingredient_name("Soy Sauce") == "soy sauce"


def test_collapses_internal_whitespace_left_by_removed_parens():
    assert normalize_ingredient_name("onion  (for cooking)  extra") == "onion extra"
