from __future__ import annotations

import asyncio
import json
import os
import stat
from pathlib import Path
from typing import Any

from ghostwriter.model import Draft
from ghostwriter.serializer import serialize_draft

from .base import InjectionRequest, InjectionTarget

DEFAULT_RUNTIME_DIR = Path.home() / ".pi" / "agent" / "run" / "ghostwriter"
MAX_DRAFT_BYTES = 4 * 1024 * 1024


class PiAdapter:
    id = "pi"
    display_name = "Pi"

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

    def discover_targets(self) -> list[InjectionTarget]:
        targets: list[tuple[str, InjectionTarget]] = []
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
                cwd = Path(str(data["cwd"]))
                session_name = str(data["sessionName"]) if data.get("sessionName") else None
                suffix = f" · {session_name}" if session_name else ""
                target = InjectionTarget(
                    adapter_id=self.id,
                    target_id=str(socket_path),
                    label=f"Pi · {cwd.name or cwd} · pid {pid}{suffix}",
                    cwd=cwd,
                    metadata={
                        "pid": pid,
                        "sessionId": str(data["sessionId"]),
                        "socketPath": str(socket_path),
                    },
                )
                targets.append((str(data.get("startedAt", "")), target))
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

        return [target for _, target in sorted(targets, key=lambda item: item[0], reverse=True)]

    def serialize(self, draft: Draft, target: InjectionTarget) -> str:
        return serialize_draft(draft, target.cwd)

    async def inject(
        self,
        target: InjectionTarget,
        request: InjectionRequest,
    ) -> dict[str, Any]:
        socket_path = Path(str(target.metadata["socketPath"]))
        message = {
            "version": 1,
            "target": {
                "sessionId": target.metadata["sessionId"],
                "cwd": str(target.cwd),
            },
            "draftId": request.draft_id,
            "revision": request.revision,
            "text": request.text,
        }
        payload = json.dumps(message, ensure_ascii=False).encode("utf-8") + b"\n"
        if len(payload) > MAX_DRAFT_BYTES:
            raise ValueError(f"Serialized draft exceeds {MAX_DRAFT_BYTES // (1024 * 1024)} MiB")

        async def exchange() -> dict[str, Any]:
            reader, writer = await asyncio.open_unix_connection(socket_path)
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
