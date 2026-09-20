from studio.domain.models import RECIPE_FIELDS, Recipe


def back_label(has_back: bool) -> str:
    return "背面观察候选（仍需核验）" if has_back else "设计假设（未提供背面图）"


def compile_recipe(recipe: Recipe) -> str:
    lines = ["Scene Recipe：摄影信息仅为视觉估计，不是原始拍摄数据。"]
    for key, element in recipe.elements.items():
        if key not in RECIPE_FIELDS:
            raise ValueError("未知配方字段")
        if element.action == "ignore":
            continue
        value = element.override if element.action == "modify" else element.value
        lines.append(f"{RECIPE_FIELDS[key]}: {value or 'unknown'}")
    lines.extend([f"必须保留商品特征: {recipe.preserve}", f"禁止带入: {recipe.exclude}"])
    return "\n".join(lines)


def require_capabilities(
    mode: str, capabilities: set[str], mask: bool = False, strategy="reference_recipe"
):
    required = {"understand"} if mode in {"A", "C_analyze", "CHECK"} else {"generate"}
    if mode in {"B2", "C1", "C2"}:
        required = {"edit"}
    if mode == "C1" or (mode == "C2" and strategy == "reference_recipe"):
        required.add("multi_image")
    if mask and mode != "B1":
        required.add("mask")
    missing = required - capabilities
    if missing:
        raise ValueError("当前供应商不支持：" + ", ".join(sorted(missing)))


def recovery_state(phase: str) -> str:
    return "interrupted" if phase == "claimed" else "outcome_unknown"
