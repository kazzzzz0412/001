"""Human-readable names for 34-format tile indices."""

_HONOR_NAMES_JP = ["東", "南", "西", "北", "白", "発", "中"]
_HONOR_NAMES_EN = ["East", "South", "West", "North", "White", "Green", "Red"]


def tile_notation(index: int) -> str:
    """mpsz notation for a 34-index tile, e.g. 0 -> '1m', 33 -> '7z'."""
    if index < 9:
        return f"{index + 1}m"
    if index < 18:
        return f"{index - 9 + 1}p"
    if index < 27:
        return f"{index - 18 + 1}s"
    return f"{index - 27 + 1}z"


def tile_name(index: int, lang: str = "jp") -> str:
    """Friendly display name, e.g. 0 -> '1万' / '1m', 31 -> '白' / 'White'."""
    if index >= 27:
        return _HONOR_NAMES_JP[index - 27] if lang == "jp" else _HONOR_NAMES_EN[index - 27]
    return tile_notation(index)
