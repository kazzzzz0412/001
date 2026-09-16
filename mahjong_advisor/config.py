"""Persisted configuration for the (experimental) screen-vision mode."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

DEFAULT_CONFIG_PATH = Path.home() / ".mahjong_advisor" / "config.json"


@dataclass
class CaptureRegion:
    left: int
    top: int
    width: int
    height: int

    def as_mss_region(self) -> dict:
        return {"left": self.left, "top": self.top, "width": self.width, "height": self.height}


@dataclass
class GridRegion(CaptureRegion):
    """A discard pile: a grid of tiles filled left-to-right, top-to-bottom."""

    columns: int = 6
    rows: int = 3


@dataclass
class VisionConfig:
    hand_region: CaptureRegion | None = None
    tile_count: int = 14
    discard_regions: dict[int, GridRegion] = field(default_factory=dict)
    """Discard piles keyed by player index: 1=下家, 2=対面, 3=上家."""
    templates_dir: str = "templates"
    match_threshold: float = 0.55

    @classmethod
    def load(cls, path: Path = DEFAULT_CONFIG_PATH) -> VisionConfig:
        if not path.exists():
            return cls()
        data = json.loads(path.read_text(encoding="utf-8"))
        region = data.get("hand_region")
        piles = data.get("discard_regions") or {}
        return cls(
            hand_region=CaptureRegion(**region) if region else None,
            tile_count=data.get("tile_count", 14),
            # JSON object keys are strings; player indices are ints.
            discard_regions={int(player): GridRegion(**grid) for player, grid in piles.items()},
            templates_dir=data.get("templates_dir", "templates"),
            match_threshold=data.get("match_threshold", 0.55),
        )

    def save(self, path: Path = DEFAULT_CONFIG_PATH) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "hand_region": asdict(self.hand_region) if self.hand_region else None,
            "tile_count": self.tile_count,
            "discard_regions": {
                str(player): asdict(grid) for player, grid in sorted(self.discard_regions.items())
            },
            "templates_dir": self.templates_dir,
            "match_threshold": self.match_threshold,
        }
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
