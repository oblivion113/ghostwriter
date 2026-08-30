from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from ghostwriter.config import (
    DEFAULT_REWRITE_PROMPT,
    ConfigStore,
    GhostwriterConfig,
    open_config_file,
)


def test_config_store_creates_editable_defaults(tmp_path: Path) -> None:
    path = tmp_path / "config.json"

    config = ConfigStore(path).load()

    assert path.is_file()
    assert config.file_search.include_hidden is False
    assert config.file_search.use_global_fzf_options
    assert "node_modules" in config.file_search.skipped_directories
    assert "fileSearch" in path.read_text(encoding="utf-8")
    assert config.rewrite.keep_rpc_warm
    assert config.rewrite.default_agent.provider == "agent-plan"
    assert config.rewrite.default_agent.model == "ark-code-latest"
    assert config.rewrite.instructions == ""
    assert "name" not in path.read_text(encoding="utf-8")
    assert "{text}" in config.rewrite.prompt


def test_config_loads_agents_languages_and_custom_prompt(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "fileSearch": {
                    "includeHidden": True,
                    "useGlobalFzfOptions": False,
                    "skipDirectories": ["node_modules", "__pycache__"],
                    "ignoreFiles": ["~/.config/search/ignore"],
                    "fzfOptions": ["--exact"],
                },
                "rewrite": {
                    "keepRpcWarm": False,
                    "agents": [
                        {
                            "provider": "anthropic",
                            "model": "claude-haiku",
                        }
                    ],
                    "targetLanguages": ["English", "French"],
                    "defaultTargetLanguage": "French",
                    "instructions": "Use a direct tone.",
                    "prompt": "Write in {target_language}.\n{instructions}\n{text}",
                },
            }
        ),
        encoding="utf-8",
    )

    config = ConfigStore(path).load()

    assert config.file_search.include_hidden
    assert not config.file_search.use_global_fzf_options
    assert config.file_search.fzf_options == ("--exact",)
    assert config.file_search.ignore_files[0].is_absolute()
    assert not config.rewrite.keep_rpc_warm
    assert config.rewrite.default_agent.label == "anthropic/claude-haiku"
    assert config.rewrite.default_target_language == "French"
    assert config.rewrite.instructions == "Use a direct tone."


def test_legacy_named_default_agent_is_migrated_to_first_provider_model() -> None:
    config = GhostwriterConfig.from_dict(
        {
            "version": 1,
            "rewrite": {
                "agents": [
                    {"name": "Fast", "provider": "anthropic", "model": "haiku"},
                    {"name": "Plan", "provider": "agent-plan", "model": "ark-code-latest"},
                ],
                "defaultAgent": "Plan",
                "targetLanguages": ["English"],
            },
        }
    )

    assert config.rewrite.default_agent.label == "agent-plan/ark-code-latest"
    serialized = config.to_dict()["rewrite"]
    assert "defaultAgent" not in serialized
    assert all("name" not in agent for agent in serialized["agents"])


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
                    "agents": [{"provider": "anthropic"}],
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
