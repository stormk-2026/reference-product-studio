"""Editable, bounded copy for the promotional carousel tool."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ContentModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ContentBrief(ContentModel):
    kind: Literal["app", "product"] = "app"
    name: str = Field(min_length=1, max_length=48)
    audience: str = Field(default="", max_length=100)
    facts: str = Field(min_length=1, max_length=1800)
    experience: str = Field(default="", max_length=600)
    page_count: int = Field(default=3, ge=3, le=6)
    style: Literal["clean", "bold", "warm"] = "clean"
    accent: str = Field(default="#2563eb", pattern=r"^#[0-9a-fA-F]{6}$")


class ContentPage(ContentModel):
    label: str = Field(min_length=1, max_length=16)
    title: str = Field(min_length=1, max_length=36)
    body: str = Field(default="", max_length=160)
    image_index: int = Field(default=0, ge=0, le=5)


class ContentDeck(ContentModel):
    pages: list[ContentPage] = Field(min_length=3, max_length=6)
    post_title: str = Field(min_length=1, max_length=40)
    post_body: str = Field(min_length=1, max_length=1800)
    review_notes: str = Field(default="", max_length=800)
