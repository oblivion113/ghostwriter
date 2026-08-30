from __future__ import annotations

from pathlib import Path

import pytest

from ghostwriter.rewrite import PiRpcSession

FAKE_PI = r'''#!/usr/bin/env python3
import json
import sys
from pathlib import Path

last_text = None
for line in sys.stdin:
    request = json.loads(line)
    with Path("commands.log").open("a", encoding="utf-8") as log:
        log.write(request["type"] + "\n")
    request_id = request["id"]
    command = request["type"]
    if command == "get_state":
        model = {"provider": "openai", "id": "default-model"}
        response = {"id": request_id, "type": "response", "command": command, "success": True, "data": {"model": model}}
        print(json.dumps(response), flush=True)
    elif command in {"new_session", "set_model"}:
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


@pytest.mark.asyncio
async def test_rpc_process_stays_warm_but_each_workflow_gets_a_fresh_session(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executable = tmp_path / "fake-pi"
    executable.write_text(FAKE_PI, encoding="utf-8")
    executable.chmod(0o755)
    monkeypatch.setattr("ghostwriter.rewrite.pi_rpc.shutil.which", lambda _name: str(executable))

    session = PiRpcSession(session_dir=tmp_path / "sessions")
    await session.start()
    process = session.process
    await session.prepare(provider="anthropic", model="claude-haiku")
    await session.prompt("first")
    await session.prepare(provider="openai", model="gpt-test")
    await session.prompt("second")

    commands = (session.session_dir / "commands.log").read_text(encoding="utf-8").splitlines()
    assert session.process is process
    assert commands.count("get_state") == 1
    assert commands.count("new_session") == 1
    assert commands.count("set_model") == 2
    assert commands.count("prompt") == 2

    session_dir = session.session_dir
    await session.close()
    assert not session_dir.exists()
