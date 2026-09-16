import pytest

from mahjong_advisor.config import CaptureRegion, VisionConfig
from mahjong_advisor.vision.runner import analyze_screen_once


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


def test_analyze_screen_once_without_calibration_raises():
    config = VisionConfig(hand_region=None)
    with pytest.raises(RuntimeError, match="キャリブレーション未実施"):
        analyze_screen_once(config)


def test_analyze_screen_once_without_templates_raises(tmp_path):
    config = VisionConfig(
        hand_region=CaptureRegion(left=0, top=0, width=100, height=50),
        templates_dir=str(tmp_path / "empty_templates"),
    )
    with pytest.raises(RuntimeError, match="テンプレートが空"):
        analyze_screen_once(config)
