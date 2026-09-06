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

from .files import DEFAULT_SKIPPED_DIRECTORIES
from .model import PathDisplay

CONFIG_VERSION = 1
DEFAULT_THEME = "textual-dark"
DEFAULT_PROMPT_TEMPLATE_DIRECTORY = user_config_path("ghostwriter") / "prompts"
UI_THEMES = (
    "textual-dark",
    "nord",
    "gruvbox",
    "catppuccin-mocha",
    "tokyo-night",
    "rose-pine-moon",
)
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
    provider: str = ""
    model: str = ""

    @property
    def label(self) -> str:
        return f"{self.provider}/{self.model}" if self.provider and self.model else "Pi default"

    @classmethod
    def from_dict(cls, data: object) -> RewriteAgent:
        if not isinstance(data, dict):
            raise TypeError("Each rewrite agent must be an object")
        agent = cls(
            provider=str(data.get("provider", "")).strip(),
            model=str(data.get("model", "")).strip(),
        )
        if bool(agent.provider) != bool(agent.model):
            raise ValueError(
                "Each rewrite agent must set both provider and model, or leave both blank"
            )
        return agent

    def to_dict(self) -> dict[str, str]:
        return {"provider": self.provider, "model": self.model}


@dataclass(frozen=True, slots=True)
class RewriteConfig:
    keep_rpc_warm: bool = False
    agents: tuple[RewriteAgent, ...] = (RewriteAgent("agent-plan", "ark-code-latest"),)
    target_languages: tuple[str, ...] = (
        "English",
        "Chinese (Simplified)",
        "French",
        "German",
        "Japanese",
        "Spanish",
    )
    default_target_language: str = "English"
    instructions: str = ""
    prompt: str = DEFAULT_REWRITE_PROMPT

    @classmethod
    def from_dict(cls, data: object) -> RewriteConfig:
        if not isinstance(data, dict):
            raise TypeError("rewrite must be an object")
        agents_data = data.get(
            "agents", [RewriteAgent("agent-plan", "ark-code-latest").to_dict()]
        )
        languages_data = data.get("targetLanguages", list(cls().target_languages))
        if not isinstance(agents_data, list) or not agents_data:
            raise ValueError("rewrite.agents must be a non-empty array")
        if not isinstance(languages_data, list) or not languages_data:
            raise ValueError("rewrite.targetLanguages must be a non-empty array")

        agents = tuple(RewriteAgent.from_dict(item) for item in agents_data)
        languages = tuple(str(item).strip() for item in languages_data)
        if any(not language for language in languages):
            raise ValueError("Target language names cannot be empty")
        if len({agent.label for agent in agents}) != len(agents):
            raise ValueError("Rewrite provider/model pairs must be unique")
        if len(set(languages)) != len(languages):
            raise ValueError("Target language names must be unique")

        legacy_default = str(data.get("defaultAgent", "")).strip()
        if legacy_default:
            legacy_names = [
                str(item.get("name", "")).strip() if isinstance(item, dict) else ""
                for item in agents_data
            ]
            default_index = next(
                (
                    index
                    for index, agent in enumerate(agents)
                    if legacy_default in {agent.label, legacy_names[index]}
                ),
                0,
            )
            agents = (
                (agents[default_index],)
                + agents[:default_index]
                + agents[default_index + 1 :]
            )

        default_language = str(data.get("defaultTargetLanguage", languages[0])).strip()
        instructions = str(data.get("instructions", ""))
        prompt = str(data.get("prompt", DEFAULT_REWRITE_PROMPT))
        keep_rpc_warm = data.get("keepRpcWarm", False)
        if not isinstance(keep_rpc_warm, bool):
            raise TypeError("rewrite.keepRpcWarm must be true or false")
        if default_language not in languages:
            raise ValueError(
                "rewrite.defaultTargetLanguage must be listed in rewrite.targetLanguages"
            )
        validate_prompt_template(prompt)
        return cls(
            keep_rpc_warm=keep_rpc_warm,
            agents=agents,
            target_languages=languages,
            default_target_language=default_language,
            instructions=instructions,
            prompt=prompt,
        )

    @property
    def default_agent(self) -> RewriteAgent:
        return self.agents[0]

    def agent(self, label: str) -> RewriteAgent:
        return next((agent for agent in self.agents if agent.label == label), self.default_agent)

    def to_dict(self) -> dict[str, Any]:
        return {
            "keepRpcWarm": self.keep_rpc_warm,
            "agents": [agent.to_dict() for agent in self.agents],
            "targetLanguages": list(self.target_languages),
            "defaultTargetLanguage": self.default_target_language,
            "instructions": self.instructions,
            "prompt": self.prompt,
        }


@dataclass(frozen=True, slots=True)
class FileSearchConfig:
    include_hidden: bool = False
    use_global_fzf_options: bool = True
    path_display: PathDisplay = "auto"
    skipped_directories: tuple[str, ...] = DEFAULT_SKIPPED_DIRECTORIES
    ignore_files: tuple[Path, ...] = ()
    fzf_options: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, data: object) -> FileSearchConfig:
        if not isinstance(data, dict):
            raise TypeError("fileSearch must be an object")
        include_hidden = data.get("includeHidden", False)
        use_global_options = data.get("useGlobalFzfOptions", True)
        path_display = data.get("pathDisplay", "auto")
        skipped_data = data.get("skipDirectories", list(DEFAULT_SKIPPED_DIRECTORIES))
        ignore_data = data.get("ignoreFiles", [])
        options_data = data.get("fzfOptions", [])
        if not isinstance(include_hidden, bool):
            raise TypeError("fileSearch.includeHidden must be true or false")
        if not isinstance(use_global_options, bool):
            raise TypeError("fileSearch.useGlobalFzfOptions must be true or false")
        if path_display not in {"auto", "full"}:
            raise ValueError("fileSearch.pathDisplay must be 'auto' or 'full'")
        if not isinstance(skipped_data, list) or not all(
            isinstance(item, str) and item.strip() for item in skipped_data
        ):
            raise TypeError("fileSearch.skipDirectories must be an array of names")
        skipped = tuple(item.strip() for item in skipped_data)
        if any("/" in item or "\\" in item for item in skipped):
            raise ValueError("fileSearch.skipDirectories entries must be directory names")
        if not isinstance(ignore_data, list) or not all(
            isinstance(item, str) and item.strip() for item in ignore_data
        ):
            raise TypeError("fileSearch.ignoreFiles must be an array of paths")
        if not isinstance(options_data, list) or not all(
            isinstance(item, str) and item.strip() and "\0" not in item for item in options_data
        ):
            raise TypeError("fileSearch.fzfOptions must be an array of options")
        if len(set(skipped)) != len(skipped):
            raise ValueError("fileSearch.skipDirectories entries must be unique")
        return cls(
            include_hidden=include_hidden,
            use_global_fzf_options=use_global_options,
            path_display=path_display,
            skipped_directories=skipped,
            ignore_files=tuple(Path(item).expanduser() for item in ignore_data),
            fzf_options=tuple(item.strip() for item in options_data),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "includeHidden": self.include_hidden,
            "useGlobalFzfOptions": self.use_global_fzf_options,
            "pathDisplay": self.path_display,
            "skipDirectories": list(self.skipped_directories),
            "ignoreFiles": [str(path) for path in self.ignore_files],
            "fzfOptions": list(self.fzf_options),
        }


@dataclass(frozen=True, slots=True)
class PromptTemplateConfig:
    directory: Path = DEFAULT_PROMPT_TEMPLATE_DIRECTORY

    @classmethod
    def from_dict(cls, data: object) -> PromptTemplateConfig:
        if not isinstance(data, dict):
            raise TypeError("promptTemplates must be an object")
        directory = data.get("directory", str(DEFAULT_PROMPT_TEMPLATE_DIRECTORY))
        if not isinstance(directory, str) or not directory.strip() or "\0" in directory:
            raise TypeError("promptTemplates.directory must be a non-empty path")
        return cls(directory=Path(directory.strip()).expanduser())

    def to_dict(self) -> dict[str, str]:
        return {"directory": str(self.directory)}


@dataclass(frozen=True, slots=True)
class UIConfig:
    theme: str = DEFAULT_THEME

    @classmethod
    def from_dict(cls, data: object) -> UIConfig:
        if not isinstance(data, dict):
            raise TypeError("ui must be an object")
        theme = data.get("theme", DEFAULT_THEME)
        if not isinstance(theme, str) or theme not in UI_THEMES:
            raise ValueError(f"ui.theme must be one of: {', '.join(UI_THEMES)}")
        return cls(theme=theme)

    def to_dict(self) -> dict[str, str]:
        return {"theme": self.theme}


@dataclass(frozen=True, slots=True)
class GhostwriterConfig:
    version: int = CONFIG_VERSION
    ui: UIConfig = field(default_factory=UIConfig)
    prompt_templates: PromptTemplateConfig = field(default_factory=PromptTemplateConfig)
    file_search: FileSearchConfig = field(default_factory=FileSearchConfig)
    rewrite: RewriteConfig = field(default_factory=RewriteConfig)

    @classmethod
    def from_dict(cls, data: object) -> GhostwriterConfig:
        if not isinstance(data, dict):
            raise TypeError("Config root must be an object")
        version = data.get("version", CONFIG_VERSION)
        if version != CONFIG_VERSION:
            raise ValueError(f"Unsupported Ghostwriter config version: {version!r}")
        return cls(
            version=CONFIG_VERSION,
            ui=UIConfig.from_dict(data.get("ui", {})),
            prompt_templates=PromptTemplateConfig.from_dict(
                data.get("promptTemplates", {})
            ),
            file_search=FileSearchConfig.from_dict(data.get("fileSearch", {})),
            rewrite=RewriteConfig.from_dict(data.get("rewrite", {})),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "ui": self.ui.to_dict(),
            "promptTemplates": self.prompt_templates.to_dict(),
            "fileSearch": self.file_search.to_dict(),
            "rewrite": self.rewrite.to_dict(),
        }


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


def open_desktop_path(path: Path) -> None:
    """Open an existing file or directory with the desktop's default application."""
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


def open_config_file(path: Path) -> None:
    """Open the Ghostwriter config in its associated desktop editor."""
    open_desktop_path(path)


class ConfigStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or user_config_path("ghostwriter") / "config.json"
        self.recovered_path: Path | None = None

    def reload(self) -> GhostwriterConfig:
        """Read current settings without replacing an invalid file."""
        return GhostwriterConfig.from_dict(json.loads(self.path.read_text(encoding="utf-8")))

    def load(self) -> GhostwriterConfig:
        self.recovered_path = None
        default_prompts = self.path.parent / "prompts"
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            needs_prompt_config = isinstance(data, dict) and "promptTemplates" not in data
            if needs_prompt_config:
                data = {
                    **data,
                    "promptTemplates": {"directory": str(default_prompts)},
                }
            config = GhostwriterConfig.from_dict(data)
            if needs_prompt_config:
                self.save(config)
                self._create_prompt_directory(default_prompts)
        except FileNotFoundError:
            config = GhostwriterConfig(
                prompt_templates=PromptTemplateConfig(directory=default_prompts)
            )
            self.save(config)
            self._create_prompt_directory(default_prompts)
        except (TypeError, ValueError, json.JSONDecodeError):
            broken = self.path.with_suffix(f".broken-{os.getpid()}.json")
            try:
                self.path.replace(broken)
                self.recovered_path = broken
            except OSError:
                pass
            config = GhostwriterConfig(
                prompt_templates=PromptTemplateConfig(directory=default_prompts)
            )
            self.save(config)
            self._create_prompt_directory(default_prompts)
        return config

    @staticmethod
    def _create_prompt_directory(path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True, mode=0o700)

    def save(self, config: GhostwriterConfig) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        temporary = self.path.with_suffix(f".tmp-{os.getpid()}")
        temporary.write_text(
            json.dumps(config.to_dict(), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        os.chmod(temporary, 0o600)
        temporary.replace(self.path)
