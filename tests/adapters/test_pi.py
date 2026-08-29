from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import pytest

from ghostwriter.adapters import InjectionRequest, PiAdapter


@pytest.mark.asyncio
async def test_pi_adapter_discovers_and_injects(tmp_path: Path) -> None:
    socket_path = Path("/tmp") / f"ghostwriter-test-{os.getpid()}.sock"
    socket_path.unlink(missing_ok=True)
    received: list[dict[str, object]] = []

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        received.append(json.loads(await reader.readline()))
        writer.write(b'{"ok":true,"sha256":"abc123"}\n')
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    server = await asyncio.start_unix_server(handle, path=socket_path)
    registry = {
        "version": 1,
        "pid": os.getpid(),
        "sessionId": "session-1",
        "cwd": str(tmp_path),
        "socketPath": str(socket_path),
        "startedAt": "2026-01-01T00:00:00Z",
    }
    (tmp_path / "pi.json").write_text(json.dumps(registry), encoding="utf-8")

    try:
        adapter = PiAdapter(runtime_dir=tmp_path)
        targets = adapter.discover_targets()
        assert len(targets) == 1

        response = await adapter.inject(
            targets[0],
            InjectionRequest(text="draft", draft_id="draft-1", revision=2),
        )

        assert response["ok"] is True
        assert received[0]["text"] == "draft"
        assert received[0]["target"] == {
            "sessionId": "session-1",
            "cwd": str(tmp_path),
        }
    finally:
        server.close()
        await server.wait_closed()
        socket_path.unlink(missing_ok=True)


def test_pi_adapter_removes_stale_registry(tmp_path: Path) -> None:
    registry_path = tmp_path / "stale.json"
    registry_path.write_text(
        json.dumps(
            {
                "pid": 999_999_999,
                "sessionId": "gone",
                "cwd": str(tmp_path),
                "socketPath": str(tmp_path / "gone.sock"),
            }
        ),
        encoding="utf-8",
    )

    assert PiAdapter(runtime_dir=tmp_path).discover_targets() == []
    assert not registry_path.exists()
