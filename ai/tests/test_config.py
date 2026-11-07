"""config.yaml at the repo root must load, and typos must be rejected."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from firewatch.config import Config, load_config

ROOT = Path(__file__).resolve().parents[1]


def test_repo_config_loads():
    cfg = load_config(ROOT / "config.yaml")
    assert cfg.root == ROOT
    assert cfg.detector.classes == ["fire", "smoke"]
    assert cfg.resolve(cfg.output.dir) == ROOT / "runs"


def test_unknown_key_rejected():
    with pytest.raises(ValidationError):
        Config(detector={"conf_treshold": 0.3})


def test_set_overrides_parse_yaml_values():
    overrides = ["voting.k_enter=3", "detector.conf_by_class={smoke: 0.2}",
                 "camera.context=NGOAI"]
    cfg = load_config(ROOT / "config.yaml", overrides=overrides)
    assert cfg.voting.k_enter == 3
    assert cfg.detector.conf_by_class == {"smoke": 0.2}
    assert cfg.camera.context == "NGOAI"
    with pytest.raises(ValueError):
        load_config(ROOT / "config.yaml", overrides=["voting.k_enter"])
    with pytest.raises(ValidationError):
        load_config(ROOT / "config.yaml", overrides=["voting.k_entr=3"])


def test_defaults_match_master_spec():
    cfg = Config()
    assert cfg.heartbeat.interval_s == 1.0
    assert (cfg.voting.window_m, cfg.voting.k_enter, cfg.voting.k_exit) == (10, 6, 2)
    assert cfg.vlm.timeout_s == 10 and cfg.vlm.retries == 1


def test_heldout_skip_is_a_profile_field():
    cfg = Config(datasets={"p": {"heldout_skip": ["dfire_test"]}})
    assert cfg.with_profile("p").finetune.heldout_skip == ["dfire_test"]
    assert Config().finetune.heldout_skip == []


def test_v2_base_keeps_dfire_as_published():
    cfg = load_config(ROOT / "config.yaml").with_profile("v2_base")
    by = {s.name: s for s in cfg.finetune.sources}
    assert by["dfire_train"].keep_near_dups is True
    assert by["fasdd_cv"].keep_near_dups is False
    assert cfg.finetune.heldout_skip == ["dfire_test"]
