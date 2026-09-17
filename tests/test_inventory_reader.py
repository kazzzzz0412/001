import json

import pytest

from inventory_filler.reader import (
    STICKER_SCHEMA,
    find_images,
    image_block,
    read_image,
    read_stickers,
)


class _Block:
    type = "text"

    def __init__(self, text):
        self.text = text


class _Response:
    def __init__(self, payload, stop_reason="end_turn"):
        self.content = [_Block(json.dumps(payload))]
        self.stop_reason = stop_reason


class _FakeClient:
    """Stands in for anthropic.Anthropic and records the request it was given."""

    def __init__(self, *responses):
        self._responses = list(responses)
        self.calls = []

    @property
    def messages(self):
        return self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self._responses.pop(0)


def _photo(tmp_path, name="sticker.jpg"):
    path = tmp_path / name
    path.write_bytes(b"not really a jpeg, but it only ever gets base64'd")
    return path


def _payload(*stickers):
    return {"stickers": list(stickers)}


def _sticker(no="A-1", purchased_on="R6.3.5", price="￥1,200-", condition="美品", confidence=0.9):
    return {
        "management_no": {"value": no, "confidence": confidence},
        "purchased_on": {"value": purchased_on, "confidence": confidence},
        "price": {"value": price, "confidence": confidence},
        "condition": {"value": condition, "confidence": confidence},
    }


def test_schema_demands_every_field_and_forbids_extras():
    item = STICKER_SCHEMA["properties"]["stickers"]["items"]
    assert item["required"] == ["management_no", "purchased_on", "price", "condition"]
    assert item["additionalProperties"] is False
    assert item["properties"]["price"]["required"] == ["value", "confidence"]


def test_image_block_is_base64_with_the_right_media_type(tmp_path):
    block = image_block(_photo(tmp_path, "s.png"))
    assert block["source"]["media_type"] == "image/png"
    assert block["source"]["type"] == "base64"


def test_image_block_rejects_an_unsupported_format(tmp_path):
    path = tmp_path / "scan.tiff"
    path.write_bytes(b"x")
    with pytest.raises(ValueError, match="対応していない画像形式"):
        image_block(path)


def test_read_image_transcribes_literally(tmp_path):
    client = _FakeClient(_Response(_payload(_sticker())))
    records = read_image(_photo(tmp_path), client=client)

    assert len(records) == 1
    record = records[0]
    # The reader must not normalize - that is records.py's job, and keeping it
    # separate is what makes a misread distinguishable from a mis-conversion.
    assert record.purchased_on.value == "R6.3.5"
    assert record.price.value == "￥1,200-"
    assert record.source_image == "sticker.jpg"
    assert record.management_no.confidence == 0.9


def test_read_image_requests_the_structured_schema(tmp_path):
    client = _FakeClient(_Response(_payload(_sticker())))
    read_image(_photo(tmp_path), client=client, model="claude-opus-5")

    request = client.calls[0]
    assert request["model"] == "claude-opus-5"
    assert request["output_config"]["format"]["schema"] == STICKER_SCHEMA
    assert request["messages"][0]["content"][0]["type"] == "image"


def test_read_image_handles_several_stickers_in_one_photo(tmp_path):
    client = _FakeClient(_Response(_payload(_sticker("A-1"), _sticker("A-2"))))
    records = read_image(_photo(tmp_path), client=client)
    assert [r.management_no.value for r in records] == ["A-1", "A-2"]


def test_read_image_defaults_a_missing_field_to_blank_and_zero(tmp_path):
    client = _FakeClient(_Response({"stickers": [{"management_no": {"value": "A-1"}}]}))
    record = read_image(_photo(tmp_path), client=client)[0]
    assert record.price.value == ""
    assert record.price.confidence == 0.0


def test_read_image_raises_on_a_refusal(tmp_path):
    client = _FakeClient(_Response(_payload(), stop_reason="refusal"))
    with pytest.raises(RuntimeError, match="拒否"):
        read_image(_photo(tmp_path), client=client)


def test_read_image_raises_on_an_empty_response(tmp_path):
    response = _Response(_payload())
    response.content = [_Block("")]
    with pytest.raises(RuntimeError, match="空"):
        read_image(_photo(tmp_path), client=_FakeClient(response))


def test_read_stickers_makes_one_request_per_photo(tmp_path):
    photos = [_photo(tmp_path, "a.jpg"), _photo(tmp_path, "b.jpg")]
    client = _FakeClient(_Response(_payload(_sticker("A-1"))), _Response(_payload(_sticker("A-2"))))

    records = read_stickers(photos, client=client)

    assert len(client.calls) == 2
    assert [r.source_image for r in records] == ["a.jpg", "b.jpg"]


def test_find_images_returns_supported_files_in_a_stable_order(tmp_path):
    for name in ("b.jpg", "a.png", "notes.txt"):
        (tmp_path / name).write_bytes(b"x")
    (tmp_path / "sub").mkdir()

    assert [p.name for p in find_images(tmp_path)] == ["a.png", "b.jpg"]


def test_find_images_accepts_a_single_file(tmp_path):
    photo = _photo(tmp_path)
    assert find_images(photo) == [photo]
