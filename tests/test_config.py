from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from ghostwriter.config import DEFAULT_REWRITE_PROMPT, ConfigStore, open_config_file


def test_config_store_creates_editable_defaults(tmp_path: Path) -> None:
    path = tmp_path / "config.json"

    config = ConfigStore(path).load()

    assert path.is_file()
    assert config.rewrite.keep_rpc_warm
    assert config.rewrite.default_agent == "Pi default"
    assert "{text}" in config.rewrite.prompt


def test_config_loads_agents_languages_and_custom_prompt(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "rewrite": {
                    "keepRpcWarm": False,
                    "agents": [
                        {
                            "name": "Fast",
                            "provider": "anthropic",
                            "model": "claude-haiku",
                        }
                    ],
                    "targetLanguages": ["English", "French"],
                    "defaultAgent": "Fast",
                    "defaultTargetLanguage": "French",
                    "prompt": "Write in {target_language}.\n\n{text}",
                },
            }
        ),
        encoding="utf-8",
    )

    config = ConfigStore(path).load()

    assert not config.rewrite.keep_rpc_warm
    assert config.rewrite.agent("Fast").model == "claude-haiku"
    assert config.rewrite.default_target_language == "French"


def test_config_reload_reports_invalid_edits_without_replacing_them(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    invalid = '{"version": 1, "rewrite": '
    path.write_text(invalid, encoding="utf-8")

    with pytest.raises(ValueError):
        ConfigStore(path).reload()

    assert path.read_text(encoding="utf-8") == invalid


def test_open_config_uses_detached_desktop_opener(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "config.json"
    path.write_text("{}", encoding="utf-8")
    opener = tmp_path / "xdg-open"
    opener.touch()
    popen = Mock()
    monkeypatch.setattr("ghostwriter.config.sys.platform", "linux")
    monkeypatch.setattr("ghostwriter.config.shutil.which", lambda _name: str(opener))
    monkeypatch.setattr("ghostwriter.config.subprocess.Popen", popen)

    open_config_file(path)

    args, kwargs = popen.call_args
    assert args[0] == [str(opener), str(path)]
    assert kwargs["start_new_session"] is True


def test_invalid_config_is_quarantined_and_replaced(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "rewrite": {
                    "agents": [{"name": "Broken", "provider": "anthropic"}],
                    "targetLanguages": ["English"],
                    "prompt": "missing text placeholder",
                },
            }
        ),
        encoding="utf-8",
    )

    store = ConfigStore(path)
    config = store.load()

    assert config.rewrite.prompt == DEFAULT_REWRITE_PROMPT
    assert store.recovered_path in list(tmp_path.glob("config.broken-*.json"))
