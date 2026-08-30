from __future__ import annotations

import json
import os
import shutil
import string
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from platformdirs import user_config_path

CONFIG_VERSION = 1
DEFAULT_REWRITE_PROMPT = """Transform the draft under these requirements:
{instructions}
- Return the entire transformed draft and nothing else.
- Do not inspect, describe, or alter attachments.
- Preserve every __GW_*_ATTACHMENT_####__ token byte-for-byte, exactly once, near the same semantic context.

DRAFT START
{text}
DRAFT END"""
_ALLOWED_PROMPT_FIELDS = {"instructions", "source_language", "target_language", "text"}


@dataclass(frozen=True, slots=True)
class RewriteAgent:
    name: str
    provider: str = ""
    model: str = ""

    @classmethod
    def from_dict(cls, data: object) -> RewriteAgent:
        if not isinstance(data, dict):
            raise TypeError("Each rewrite agent must be an object")
        agent = cls(
            name=str(data.get("name", "")).strip(),
            provider=str(data.get("provider", "")).strip(),
            model=str(data.get("model", "")).strip(),
        )
        if not agent.name:
            raise ValueError("Each rewrite agent needs a name")
        if bool(agent.provider) != bool(agent.model):
            raise ValueError(f"Rewrite agent {agent.name!r} must set both provider and model")
        return agent

    def to_dict(self) -> dict[str, str]:
        return {"name": self.name, "provider": self.provider, "model": self.model}


@dataclass(frozen=True, slots=True)
class RewriteConfig:
    keep_rpc_warm: bool = True
    agents: tuple[RewriteAgent, ...] = (RewriteAgent("Pi default"),)
    target_languages: tuple[str, ...] = (
        "English",
        "Chinese (Simplified)",
        "French",
        "German",
        "Japanese",
        "Spanish",
    )
    default_agent: str = "Pi default"
    default_target_language: str = "English"
    prompt: str = DEFAULT_REWRITE_PROMPT

    @classmethod
    def from_dict(cls, data: object) -> RewriteConfig:
        if not isinstance(data, dict):
            raise TypeError("rewrite must be an object")
        agents_data = data.get("agents", [RewriteAgent("Pi default").to_dict()])
        languages_data = data.get("targetLanguages", list(cls().target_languages))
        if not isinstance(agents_data, list) or not agents_data:
            raise ValueError("rewrite.agents must be a non-empty array")
        if not isinstance(languages_data, list) or not languages_data:
            raise ValueError("rewrite.targetLanguages must be a non-empty array")

        agents = tuple(RewriteAgent.from_dict(item) for item in agents_data)
        languages = tuple(str(item).strip() for item in languages_data)
        if any(not language for language in languages):
            raise ValueError("Target language names cannot be empty")
        if len({agent.name for agent in agents}) != len(agents):
            raise ValueError("Rewrite agent names must be unique")
        if len(set(languages)) != len(languages):
            raise ValueError("Target language names must be unique")

        default_agent = str(data.get("defaultAgent", agents[0].name)).strip()
        default_language = str(data.get("defaultTargetLanguage", languages[0])).strip()
        prompt = str(data.get("prompt", DEFAULT_REWRITE_PROMPT))
        keep_rpc_warm = data.get("keepRpcWarm", True)
        if not isinstance(keep_rpc_warm, bool):
            raise TypeError("rewrite.keepRpcWarm must be true or false")
        if default_agent not in {agent.name for agent in agents}:
            raise ValueError("rewrite.defaultAgent must name an entry in rewrite.agents")
        if default_language not in languages:
            raise ValueError(
                "rewrite.defaultTargetLanguage must be listed in rewrite.targetLanguages"
            )
        validate_prompt_template(prompt)
        return cls(
            keep_rpc_warm=keep_rpc_warm,
            agents=agents,
            target_languages=languages,
            default_agent=default_agent,
            default_target_language=default_language,
            prompt=prompt,
        )

    def agent(self, name: str) -> RewriteAgent:
        return next((agent for agent in self.agents if agent.name == name), self.agents[0])

    def to_dict(self) -> dict[str, Any]:
        return {
            "keepRpcWarm": self.keep_rpc_warm,
            "agents": [agent.to_dict() for agent in self.agents],
            "targetLanguages": list(self.target_languages),
            "defaultAgent": self.default_agent,
            "defaultTargetLanguage": self.default_target_language,
            "prompt": self.prompt,
        }


@dataclass(frozen=True, slots=True)
class GhostwriterConfig:
    version: int = CONFIG_VERSION
    rewrite: RewriteConfig = field(default_factory=RewriteConfig)

    @classmethod
    def from_dict(cls, data: object) -> GhostwriterConfig:
        if not isinstance(data, dict):
            raise TypeError("Config root must be an object")
        version = data.get("version", CONFIG_VERSION)
        if version != CONFIG_VERSION:
            raise ValueError(f"Unsupported Ghostwriter config version: {version!r}")
        return cls(version=CONFIG_VERSION, rewrite=RewriteConfig.from_dict(data.get("rewrite", {})))

    def to_dict(self) -> dict[str, Any]:
        return {"version": self.version, "rewrite": self.rewrite.to_dict()}


def validate_prompt_template(template: str) -> None:
    if not template.strip():
        raise ValueError("rewrite.prompt cannot be empty")
    fields: set[str] = set()
    try:
        for _, field_name, _, _ in string.Formatter().parse(template):
            if field_name is not None:
                fields.add(field_name)
    except ValueError as error:
        raise ValueError(f"Invalid rewrite.prompt: {error}") from error
    unknown = fields - _ALLOWED_PROMPT_FIELDS
    if unknown:
        raise ValueError(f"Unknown rewrite.prompt placeholder: {min(unknown)}")
    if "text" not in fields:
        raise ValueError("rewrite.prompt must contain the {text} placeholder")


def open_config_file(path: Path) -> None:
    """Open a config file with the desktop's default associated editor."""
    path = path.expanduser().resolve(strict=True)
    if sys.platform == "win32":
        startfile = getattr(os, "startfile", None)
        if startfile is None:
            raise OSError("The Windows file opener is unavailable")
        startfile(path)
        return

    opener = "/usr/bin/open" if sys.platform == "darwin" else shutil.which("xdg-open")
    if opener is None or not Path(opener).is_file():
        raise OSError("No desktop file opener is available")
    # Detach the GUI editor from Textual's terminal streams.
    subprocess.Popen(
        [opener, str(path)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


class ConfigStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or user_config_path("ghostwriter") / "config.json"
        self.recovered_path: Path | None = None

    def reload(self) -> GhostwriterConfig:
        """Read current settings without replacing an invalid file."""
        return GhostwriterConfig.from_dict(json.loads(self.path.read_text(encoding="utf-8")))

    def load(self) -> GhostwriterConfig:
        self.recovered_path = None
        try:
            config = self.reload()
        except FileNotFoundError:
            config = GhostwriterConfig()
            self.save(config)
        except (TypeError, ValueError, json.JSONDecodeError):
            broken = self.path.with_suffix(f".broken-{os.getpid()}.json")
            try:
                self.path.replace(broken)
                self.recovered_path = broken
            except OSError:
                pass
            config = GhostwriterConfig()
            self.save(config)
        return config

    def save(self, config: GhostwriterConfig) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        temporary = self.path.with_suffix(f".tmp-{os.getpid()}")
        temporary.write_text(
            json.dumps(config.to_dict(), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        os.chmod(temporary, 0o600)
        temporary.replace(self.path)
