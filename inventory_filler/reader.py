"""Read handwritten inventory stickers with Claude's vision support.

The model is asked to transcribe *literally* - "R6.3.5" stays "R6.3.5" - and to
score how legible each value was. Interpretation happens in `records.py`, so a
misreading and a mis-normalization stay separately diagnosable, and the whole
normalization layer stays testable without spending a token.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path

from .records import FIELD_NAMES, FieldValue, StickerRecord

DEFAULT_MODEL = "claude-opus-5"

MEDIA_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
}

SYSTEM_PROMPT = """\
あなたは中古品の在庫管理を手伝う転記専門家です。写真に写っているのは手書きの在庫表ステッカーで、
管理番号・仕入日・価格・商品の状態が記入されています。

重要なルール:
- 書いてある文字列を**そのまま**転記してください。形式の統一や換算は行わないこと。
  例: "R6.3.5" は "R6.3.5" のまま。"￥1,200-" は "￥1,200-" のまま。
- 読めない項目や空欄は空文字列 "" を返し、confidence を 0 にしてください。推測で埋めないこと。
- confidence は 0.0-1.0 で、その文字をどれだけ確実に読めたかを表します。
  完全に明瞭 = 1.0、1文字でも迷ったら 0.7 以下、推測が入ったら 0.5 以下。
  数字の 1/7、0/6、3/8 のような混同しやすいペアは特に厳しく見積もってください。
- 1枚の写真にステッカーが複数写っている場合は、それぞれを別の要素として返してください。
"""

USER_PROMPT = "この写真に写っている在庫表ステッカーを転記してください。"


def _field_schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "value": {"type": "string", "description": "書いてある通りの文字列"},
            "confidence": {"type": "number", "description": "0.0-1.0"},
        },
        "required": ["value", "confidence"],
        "additionalProperties": False,
    }


STICKER_SCHEMA = {
    "type": "object",
    "properties": {
        "stickers": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {name: _field_schema() for name in FIELD_NAMES},
                "required": list(FIELD_NAMES),
                "additionalProperties": False,
            },
        }
    },
    "required": ["stickers"],
    "additionalProperties": False,
}


def image_block(path: Path) -> dict:
    """Build the image content block for one photo."""
    path = Path(path)
    media_type = MEDIA_TYPES.get(path.suffix.lower())
    if media_type is None:
        raise ValueError(
            f"対応していない画像形式です: {path.name} "
            f"(対応: {', '.join(sorted(MEDIA_TYPES))})"
        )
    data = base64.standard_b64encode(path.read_bytes()).decode("ascii")
    return {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": data}}


def _records_from_payload(payload: dict, source: str) -> list[StickerRecord]:
    records = []
    for sticker in payload.get("stickers") or []:
        values = {}
        for name in FIELD_NAMES:
            raw = sticker.get(name) or {}
            text = str(raw.get("value", ""))
            values[name] = FieldValue(
                value=text,
                confidence=float(raw.get("confidence", 0.0) or 0.0),
                raw=text,
            )
        records.append(StickerRecord(source_image=source, **values))
    return records


def read_image(path: Path, *, client, model: str = DEFAULT_MODEL) -> list[StickerRecord]:
    """Transcribe every sticker visible in one photo."""
    response = client.messages.create(
        model=model,
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": [image_block(path), {"type": "text", "text": USER_PROMPT}],
            }
        ],
        output_config={"format": {"type": "json_schema", "schema": STICKER_SCHEMA}},
    )

    if getattr(response, "stop_reason", None) == "refusal":
        raise RuntimeError(f"モデルが読み取りを拒否しました: {Path(path).name}")

    text = next((b.text for b in response.content if b.type == "text"), "")
    if not text.strip():
        raise RuntimeError(f"読み取り結果が空でした: {Path(path).name}")

    return _records_from_payload(json.loads(text), Path(path).name)


def find_images(directory: Path) -> list[Path]:
    """Every supported image directly under `directory`, in a stable order."""
    directory = Path(directory)
    if directory.is_file():
        return [directory]
    return sorted(
        p for p in directory.iterdir() if p.is_file() and p.suffix.lower() in MEDIA_TYPES
    )


def read_stickers(
    paths: list[Path], *, client=None, model: str = DEFAULT_MODEL
) -> list[StickerRecord]:
    """Transcribe a batch of photos, one request per photo.

    One request per photo keeps a failed or refused read isolated to the photo
    that caused it, and keeps every record attributable to a file you can go
    back and look at.
    """
    if client is None:
        import anthropic  # imported lazily: the planner and tests never need it

        client = anthropic.Anthropic()

    records: list[StickerRecord] = []
    for path in paths:
        records.extend(read_image(Path(path), client=client, model=model))
    return records
