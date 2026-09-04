from __future__ import annotations

import asyncio
import json
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .model import Draft

DEFAULT_RUNTIME_DIR = Path.home() / ".pi" / "agent" / "run" / "ghostwriter"
MAX_DRAFT_BYTES = 4 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class PiTarget:
    pid: int
    session_id: str
    cwd: Path
    socket_path: Path
    provider: str = ""
    model_id: str = ""
    thinking_level: str = ""
    session_name: str | None = None
    started_at: str = ""

    @property
    def selection_id(self) -> str:
        return str(self.socket_path)

    @property
    def model_name(self) -> str:
        if self.provider and self.model_id:
            return f"{self.provider}/{self.model_id}"
        return self.model_id or self.provider or "Unknown model"

    @property
    def label(self) -> str:
        project = self.cwd.name or str(self.cwd)
        identity = self.session_name if self.session_name and self.session_name != project else project
        return f"{identity} · {self.model_id or 'unknown model'} · {self.session_id[:6]}"

    @property
    def summary(self) -> str:
        project = self.cwd.name or str(self.cwd)
        identity = self.session_name if self.session_name and self.session_name != project else project
        try:
            directory = "~/" + self.cwd.resolve().relative_to(Path.home().resolve()).as_posix()
        except ValueError:
            directory = str(self.cwd)
        thinking = f":{self.thinking_level}" if self.thinking_level else ""
        return f"{identity} · {self.model_name}{thinking} · {self.session_id[:6]} · {directory}"

    @property
    def details(self) -> str:
        try:
            directory = "~/" + self.cwd.resolve().relative_to(Path.home().resolve()).as_posix()
        except ValueError:
            directory = str(self.cwd)
        session = self.session_name or self.session_id[:12]
        thinking = f" · {self.thinking_level}" if self.thinking_level else ""
        return (
            f"Session    {session}\n"
            f"Directory  {directory}\n"
            f"Model      {self.model_name}{thinking}\n"
            f"Process    PID {self.pid}"
        )


def _display_path(path: Path, cwd: Path) -> str:
    resolved = path.expanduser().resolve()
    try:
        return resolved.relative_to(cwd.expanduser().resolve()).as_posix()
    except ValueError:
        return resolved.as_posix()


def format_file_reference(path: Path, cwd: Path) -> str:
    value = _display_path(path, cwd)
    if '"' in value or "\n" in value or "\r" in value:
        raise ValueError(f"Pi file references cannot safely represent this path: {value!r}")
    return f'@"{value}"' if any(character.isspace() for character in value) else f"@{value}"


def serialize_draft(draft: Draft, cwd: Path) -> str:
    text = draft.text.rstrip()
    orphaned_references: list[str] = []
    for attachment in draft.attachments:
        reference = format_file_reference(attachment.source, cwd)
        if attachment.editor_token in text:
            text = text.replace(attachment.editor_token, reference)
        else:
            orphaned_references.append(reference)

    if not orphaned_references:
        return text

    attachment_block = "Referenced attachments:\n" + "\n".join(
        f"- {reference}" for reference in orphaned_references
    )
    return f"{text}\n\n{attachment_block}" if text else attachment_block


class PiBridgeClient:
    def __init__(self, runtime_dir: Path = DEFAULT_RUNTIME_DIR) -> None:
        self.runtime_dir = runtime_dir

    @staticmethod
    def _process_is_alive(pid: int) -> bool:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True

    def discover_targets(self) -> list[PiTarget]:
        targets: list[PiTarget] = []
        try:
            registry_files = list(self.runtime_dir.glob("*.json"))
        except OSError:
            return []

        socket_directory = Path("/tmp") / f"ghostwriter-{os.getuid()}"
        for registry in registry_files:
            stale_socket: Path | None = None
            try:
                data = json.loads(registry.read_text(encoding="utf-8"))
                if not isinstance(data, dict):
                    raise TypeError("Registry entry must be an object")
                pid = int(data["pid"])
                socket_path = Path(str(data["socketPath"]))
                stale_socket = socket_path
                if not self._process_is_alive(pid) or not socket_path.exists():
                    raise ProcessLookupError
                targets.append(
                    PiTarget(
                        pid=pid,
                        session_id=str(data["sessionId"]),
                        session_name=(str(data["sessionName"]) if data.get("sessionName") else None),
                        cwd=Path(str(data["cwd"])),
                        socket_path=socket_path,
                        provider=str(data.get("modelProvider", "")),
                        model_id=str(data.get("modelId", "")),
                        thinking_level=str(data.get("thinkingLevel", "")),
                        started_at=str(data.get("startedAt", "")),
                    )
                )
            except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError, ProcessLookupError):
                try:
                    registry.unlink()
                except OSError:
                    pass
                try:
                    if (
                        stale_socket is not None
                        and stale_socket.parent == socket_directory
                        and stale_socket.name.startswith("pi-")
                        and stat.S_ISSOCK(stale_socket.stat().st_mode)
                    ):
                        stale_socket.unlink()
                except OSError:
                    pass

        return sorted(targets, key=lambda target: target.started_at, reverse=True)

    @staticmethod
    def serialize(draft: Draft, target: PiTarget) -> str:
        return serialize_draft(draft, target.cwd)

    async def inject(
        self,
        target: PiTarget,
        *,
        text: str,
        draft_id: str,
        revision: int,
    ) -> dict[str, Any]:
        message = {
            "version": 1,
            "target": {"sessionId": target.session_id, "cwd": str(target.cwd)},
            "draftId": draft_id,
            "revision": revision,
            "text": text,
        }
        payload = json.dumps(message, ensure_ascii=False).encode("utf-8") + b"\n"
        if len(payload) > MAX_DRAFT_BYTES:
            raise ValueError(f"Serialized draft exceeds {MAX_DRAFT_BYTES // (1024 * 1024)} MiB")

        async def exchange() -> dict[str, Any]:
            reader, writer = await asyncio.open_unix_connection(target.socket_path)
            try:
                writer.write(payload)
                await writer.drain()
                response_line = await reader.readline()
                if not response_line:
                    raise ConnectionError("Pi bridge closed without acknowledging the draft")
                response = json.loads(response_line)
                if not isinstance(response, dict):
                    raise ConnectionError("Pi bridge returned an invalid response")
                if response.get("ok") is not True:
                    raise ConnectionError(str(response.get("error") or "Pi bridge rejected the draft"))
                return response
            finally:
                writer.close()
                await writer.wait_closed()

        return await asyncio.wait_for(exchange(), timeout=3.0)
