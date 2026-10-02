"""Merge Ingredient rows whose names normalize to the same thing.

Normalization (ADR-0008) only applies to names as they're saved, so rows created
before a normalization rule existed stay split - "onions", "onion (for cooking)"
and "onion" as three ingredients, so pantry matching sees three different things.
Every addition to the synonym map recreates the same problem for existing data.

Idempotent and cheap (one pass over a small lookup table), so it runs on every
API deploy right after migrations - see ADR-0027. Run by hand with:

    python -m app.ingredients.dedup [--dry-run]
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ingredients.normalization import combine_quantities, normalize_ingredient_name
from app.models import Ingredient, RecipeIngredient


@dataclass
class IngredientMerge:
    canonical_name: str
    merged_names: list[str] = field(default_factory=list)
    renamed_from: str | None = None
    links_repointed: int = 0
    links_combined: int = 0


def merge_duplicate_ingredients(session: Session) -> list[IngredientMerge]:
    """Collapse each group of same-normalized-name ingredients into one row,
    named with the canonical spelling. Flushes but does not commit."""
    groups: dict[str, list[Ingredient]] = defaultdict(list)
    for ingredient in session.scalars(select(Ingredient).order_by(Ingredient.id)):
        groups[normalize_ingredient_name(ingredient.name)].append(ingredient)

    merges = []
    for canonical_name, group in groups.items():
        if len(group) == 1 and group[0].name == canonical_name:
            continue

        # Prefer the row already spelled canonically, else the oldest.
        keeper = next((i for i in group if i.name == canonical_name), group[0])
        duplicates = [i for i in group if i is not keeper]
        merge = IngredientMerge(canonical_name=canonical_name)

        if duplicates:
            merge.merged_names = [d.name for d in duplicates]
            group_ids = [i.id for i in group]
            links = session.scalars(
                select(RecipeIngredient)
                .where(RecipeIngredient.ingredient_id.in_(group_ids))
                .order_by(RecipeIngredient.id)
            ).all()

            # A recipe can only link an ingredient once (unique recipe_id +
            # ingredient_id), so a recipe that listed both "onion" and "onions"
            # keeps one link, with both quantities rather than silently losing one.
            # Deletes are flushed before repointing so no UPDATE can collide.
            survivor_by_recipe: dict[int, RecipeIngredient] = {}
            for link in sorted(links, key=lambda l: l.ingredient_id != keeper.id):
                survivor = survivor_by_recipe.get(link.recipe_id)
                if survivor is None:
                    survivor_by_recipe[link.recipe_id] = link
                else:
                    survivor.quantity = combine_quantities(survivor.quantity, link.quantity)
                    session.delete(link)
                    merge.links_combined += 1
            session.flush()

            for link in survivor_by_recipe.values():
                if link.ingredient_id != keeper.id:
                    link.ingredient_id = keeper.id
                    merge.links_repointed += 1
            session.flush()

            for duplicate in duplicates:
                session.delete(duplicate)
            session.flush()

        if keeper.name != canonical_name:
            merge.renamed_from = keeper.name
            keeper.name = canonical_name
            session.flush()

        merges.append(merge)

    return merges


def main() -> None:
    from app.db import SessionLocal

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="report, then roll back")
    args = parser.parse_args()

    with SessionLocal() as session:
        merges = merge_duplicate_ingredients(session)
        for m in merges:
            parts = []
            if m.merged_names:
                parts.append(f"merged {m.merged_names}")
            if m.renamed_from:
                parts.append(f"renamed from {m.renamed_from!r}")
            parts.append(f"{m.links_repointed} links repointed, {m.links_combined} combined")
            print(f"{m.canonical_name!r}: " + "; ".join(parts))
        print(f"{len(merges)} ingredient(s) changed" + (" (dry run)" if args.dry_run else ""))

        if args.dry_run:
            session.rollback()
        else:
            session.commit()


if __name__ == "__main__":
    main()
