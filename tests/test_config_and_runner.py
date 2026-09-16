from mahjong_advisor.config import CaptureRegion, VisionConfig


def test_vision_config_roundtrip(tmp_path):
    path = tmp_path / "config.json"
    config = VisionConfig(
        hand_region=CaptureRegion(left=10, top=20, width=300, height=50),
        tile_count=14,
        templates_dir="my_templates",
        match_threshold=0.6,
    )
    config.save(path)

    loaded = VisionConfig.load(path)
    assert loaded.hand_region == config.hand_region
    assert loaded.tile_count == 14
    assert loaded.templates_dir == "my_templates"
    assert loaded.match_threshold == 0.6


def test_vision_config_load_missing_file_returns_defaults(tmp_path):
    config = VisionConfig.load(tmp_path / "does_not_exist.json")
    assert config.hand_region is None
    assert config.tile_count == 14


# Screen-read behaviour, including the uncalibrated error paths, is covered in
# tests/test_vision_table.py against the read_table pipeline.
