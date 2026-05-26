from pathlib import Path

import pytest
from pydantic import ValidationError

from app.config import Config, load_config, threshold_for_asset


def test_threshold_for_unknown_asset_uses_default():
    config = load_config("config.yaml")
    assert threshold_for_asset(config, "UNKNOWN") == 0.65


def test_threshold_for_broad_index_asset():
    config = load_config("config.yaml")
    assert threshold_for_asset(config, "000510") == 0.60


def test_threshold_for_high_volatility_c_class_asset():
    config = load_config("config.yaml")
    assert threshold_for_asset(config, "008282") == 0.70


def test_non_paper_mode_is_rejected(tmp_path: Path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
app:
  name: test
  mode: live
  database_path: data/test.sqlite
  paper_log_path: data/log.jsonl
""",
        encoding="utf-8",
    )
    with pytest.raises(ValidationError):
        load_config(config_path)


def test_config_forbids_extra_top_level_keys():
    raw = {
        "app": {"name": "test", "mode": "paper"},
        "unexpected": True,
    }
    with pytest.raises(ValidationError):
        Config.model_validate(raw)
