import pytest
from pydantic import ValidationError

from studio.domain.models import Evidence, Recipe, RecipeElement, Request
from studio.domain.rules import back_label, compile_recipe, recovery_state, require_capabilities


def test_unseen_back_is_hypothesis():
    assert back_label(False) == "设计假设（未提供背面图）"
    assert "还原" not in back_label(False)


def test_evidence_never_accepts_fake_probability():
    with pytest.raises(ValidationError):
        Evidence(value="cotton", status="certain", confidence=0.99)


def test_recipe_user_overrides_and_ignored_fields():
    recipe = Recipe(
        elements={
            "background": RecipeElement(value="red", action="modify", override="blue"),
            "props": RecipeElement(value="brand logo", action="ignore"),
            "light_direction": RecipeElement(value=None),
        },
        preserve="buttons",
        exclude="text",
    )
    prompt = compile_recipe(recipe)
    assert "blue" in prompt and "red" not in prompt and "brand logo" not in prompt
    assert "unknown" in prompt and "buttons" in prompt and "text" in prompt


def test_capabilities_cannot_silently_degrade():
    with pytest.raises(ValueError, match="multi_image"):
        require_capabilities("C1", {"edit"})
    with pytest.raises(ValueError, match="mask"):
        require_capabilities("B2", {"edit"}, mask=True)


@pytest.mark.parametrize(
    "phase,expected",
    [
        ("claimed", "interrupted"),
        ("dispatching", "outcome_unknown"),
        ("received", "outcome_unknown"),
    ],
)
def test_crash_never_assumes_success(phase, expected):
    assert recovery_state(phase) == expected


def test_input_limits_and_explicit_modes():
    with pytest.raises(ValidationError):
        Request(mode="B1", product_ids=["x"], scale=2)
    with pytest.raises(ValidationError):
        Request(mode="made-up", product_ids=["x"])
