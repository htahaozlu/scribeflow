"""Layered config precedence + coercion (docs/ai/05 §1)."""

from __future__ import annotations

from pathlib import Path

import pytest

from yazit.config import ConfigError, YazitConfig, load_config


def test_defaults() -> None:
    cfg = load_config({}, env={})
    assert cfg == YazitConfig()
    # Dirs are None when unset — the runtime target fills the defaults.
    assert cfg.output_dir is None
    assert cfg.workspace_dir is None
    assert cfg.language == "tr"
    assert cfg.chunk_minutes == 20
    assert cfg.formats == ("txt",)


def test_precedence_cli_over_env_over_file(tmp_path: Path) -> None:
    toml = tmp_path / "yazit.toml"
    toml.write_text(
        "\n".join(
            [
                "[backend]",
                'model = "from-file"',
                'want = "quality"',
                "[transcribe]",
                "chunk_minutes = 30",
                'language = "en"',
            ]
        ),
        encoding="utf-8",
    )
    env = {"YAZIT_MODEL": "from-env", "YAZIT_CHUNK_MINUTES": "15"}
    cli = {"model": "from-cli"}

    cfg = load_config(cli, config_path=toml, env=env)
    assert cfg.model == "from-cli"  # cli wins
    assert cfg.chunk_minutes == 15  # env wins over file
    assert cfg.want == "quality"  # file wins over default
    assert cfg.language == "en"  # file


def test_env_type_coercion() -> None:
    env = {
        "YAZIT_CHUNK_MINUTES": "10",
        "YAZIT_BEAM_SIZE": "3",
        "YAZIT_VAD_FILTER": "false",
        "YAZIT_OUTPUT_DIR": "/tmp/out",
    }
    cfg = load_config({}, env=env)
    assert cfg.chunk_minutes == 10
    assert cfg.beam_size == 3
    assert cfg.vad_filter is False
    assert cfg.output_dir == Path("/tmp/out")


def test_formats_from_comma_string() -> None:
    cfg = load_config({"formats": "txt,srt,vtt"}, env={})
    assert cfg.formats == ("txt", "srt", "vtt")


def test_unknown_keys_ignored() -> None:
    cfg = load_config({"bogus": "x", "model": "m"}, env={})
    assert cfg.model == "m"
    assert not hasattr(cfg, "bogus")


def test_bad_env_int_raises_config_error() -> None:
    with pytest.raises(ConfigError):
        load_config({}, env={"YAZIT_CHUNK_MINUTES": "abc"})


def test_malformed_toml_raises_config_error(tmp_path: Path) -> None:
    toml = tmp_path / "yazit.toml"
    toml.write_text("this is = = not valid", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config({}, config_path=toml, env={})


def test_non_positive_chunk_minutes_raises(tmp_path: Path) -> None:
    with pytest.raises(ConfigError):
        load_config({"chunk_minutes": 0}, env={})


def test_unknown_format_raises_config_error() -> None:
    with pytest.raises(ConfigError):
        load_config({"formats": "txt,flac"}, env={})


def test_toml_type_confusion_is_tolerated(tmp_path: Path) -> None:
    # `output` as a string (not a table) must not crash — it is ignored.
    toml = tmp_path / "yazit.toml"
    toml.write_text('output = "oops"\n[backend]\nmodel = "m"\n', encoding="utf-8")
    cfg = load_config({}, config_path=toml, env={})
    assert cfg.model == "m"
    assert cfg.output_dir == YazitConfig().output_dir
