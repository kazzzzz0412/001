"""Fill a spreadsheet inventory sheet from photos of handwritten stickers.

    python main.py inventory --init-config
    python main.py inventory --images ./photos --target book:在庫表.xlsx
    python main.py inventory --images ./photos --target sheet:<ID> --apply

The pipeline is four separable steps: `reader` transcribes photos literally,
`records` normalizes the transcription, `planner` decides which cells to write,
and `targets` writes them. Only the first step needs the network.
"""

from __future__ import annotations

__all__ = ["cli", "config", "planner", "reader", "records", "targets"]
