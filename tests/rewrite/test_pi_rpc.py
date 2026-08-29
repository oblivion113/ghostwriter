from __future__ import annotations

from pathlib import Path

import pytest

from ghostwriter.rewrite import PiRpcSession

FAKE_PI = r'''#!/usr/bin/env python3
import json
import sys

last_text = None
for line in sys.stdin:
    request = json.loads(line)
    request_id = request["id"]
    command = request["type"]
    if command == "get_state":
        response = {"id": request_id, "type": "response", "command": command, "success": True, "data": {}}
        print(json.dumps(response), flush=True)
    elif command == "prompt":
        last_text = "Rewritten __GW_TEST_ATTACHMENT_0000__ text"
        print(json.dumps({"id": request_id, "type": "response", "command": command, "success": True}), flush=True)
        print(json.dumps({"type": "message_end", "message": {"role": "assistant", "stopReason": "stop"}}), flush=True)
        print(json.dumps({"type": "agent_settled"}), flush=True)
    elif command == "get_last_assistant_text":
        response = {"id": request_id, "type": "response", "command": command, "success": True, "data": {"text": last_text}}
        print(json.dumps(response), flush=True)
'''


@pytest.mark.asyncio
async def test_rpc_session_reuses_process_and_deletes_cached_session(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executable = tmp_path / "fake-pi"
    executable.write_text(FAKE_PI, encoding="utf-8")
    executable.chmod(0o755)
    monkeypatch.setattr("ghostwriter.rewrite.pi_rpc.shutil.which", lambda _name: str(executable))

    session_root = tmp_path / "sessions"
    session = PiRpcSession(session_dir=session_root)
    result = await session.prompt("rewrite this")
    created_session = session.session_dir

    assert result == "Rewritten __GW_TEST_ATTACHMENT_0000__ text"
    assert created_session.is_dir()

    await session.close()

    assert not created_session.exists()
    assert session_root.is_dir()
