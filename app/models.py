from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db import Base

_TIMESTAMP = DateTime(timezone=True)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String, unique=True)
    created_at: Mapped[datetime] = mapped_column(_TIMESTAMP, server_default=func.now())

    recipes: Mapped[list["Recipe"]] = relationship(back_populates="user")


class RawSource(Base):
    """Staging area for ingested content before LLM parsing (0.5) turns it into
    a structured Recipe (0.6). Populated either by the YouTube pipeline or by a
    manually pasted caption (the Instagram path)."""

    __tablename__ = "raw_sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    source_url: Mapped[str] = mapped_column(String)
    source_platform: Mapped[str] = mapped_column(String)
    raw_text: Mapped[str] = mapped_column(Text)
    title: Mapped[str | None] = mapped_column(String, nullable=True)
    thumbnail_url: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(_TIMESTAMP, server_default=func.now())

    user: Mapped["User"] = relationship()


class Recipe(Base):
    __tablename__ = "recipes"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    raw_source_id: Mapped[int | None] = mapped_column(
        ForeignKey("raw_sources.id"), nullable=True
    )
    source_url: Mapped[str] = mapped_column(String)
    source_platform: Mapped[str] = mapped_column(String)
    title: Mapped[str] = mapped_column(String)
    steps: Mapped[list[str]] = mapped_column(JSONB, default=list)
    raw_source_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(_TIMESTAMP, server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="recipes")
    raw_source: Mapped["RawSource | None"] = relationship()
    ingredients: Mapped[list["RecipeIngredient"]] = relationship(
        back_populates="recipe", cascade="all, delete-orphan"
    )


class Ingredient(Base):
    __tablename__ = "ingredients"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True)


class RecipeIngredient(Base):
    __tablename__ = "recipe_ingredients"
    __table_args__ = (UniqueConstraint("recipe_id", "ingredient_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    recipe_id: Mapped[int] = mapped_column(ForeignKey("recipes.id"), nullable=False)
    ingredient_id: Mapped[int] = mapped_column(ForeignKey("ingredients.id"), nullable=False)
    quantity: Mapped[str | None] = mapped_column(String, nullable=True)
    raw_text: Mapped[str | None] = mapped_column(String, nullable=True)

    recipe: Mapped["Recipe"] = relationship(back_populates="ingredients")
    ingredient: Mapped["Ingredient"] = relationship()
