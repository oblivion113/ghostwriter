from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import pytest

from ghostwriter.model import Attachment, Draft
from ghostwriter.pi import PiBridgeClient, PiTarget, format_file_reference, serialize_draft


def test_file_references_are_relative_and_quote_spaces(tmp_path: Path) -> None:
    plain = tmp_path / "src" / "main.py"
    spaced = tmp_path / "notes" / "design brief.md"
    directory = tmp_path / "reference notes"
    directory.mkdir()

    assert format_file_reference(plain, tmp_path) == "@src/main.py"
    assert format_file_reference(spaced, tmp_path) == '@"notes/design brief.md"'
    assert format_file_reference(directory, tmp_path) == '@"reference notes/"'


def test_serialize_draft_uses_original_paths_for_files_and_images(tmp_path: Path) -> None:
    source = tmp_path / "source.py"
    image = tmp_path / "image.png"
    draft = Draft(
        text="Review these.",
        attachments=[
            Attachment("file", str(source)),
            Attachment("image", str(image)),
        ],
    )

    assert serialize_draft(draft, tmp_path) == (
        "Review these.\n\nReferenced attachments:\n"
        "- @source.py\n"
        "- @image.png"
    )


def test_skill_invocation_is_preserved_during_serialization(tmp_path: Path) -> None:
    text = "Explain this, then use /skill:teaching for the example."

    assert serialize_draft(Draft(text=text), tmp_path) == text


def test_inline_attachment_token_is_replaced_in_place(tmp_path: Path) -> None:
    source = tmp_path / "context.md"
    attachment = Attachment("file", str(source), id="inline123456789")
    draft = Draft(text=f"Before {attachment.editor_token} after", attachments=[attachment])

    assert serialize_draft(draft, tmp_path) == "Before @context.md after"


def test_file_reference_rejects_unrepresentable_path(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="cannot safely represent"):
        format_file_reference(tmp_path / 'bad"name.txt', tmp_path)


def test_target_label_and_details_identify_session(tmp_path: Path) -> None:
    target = PiTarget(
        pid=43210,
        session_id="abcdef1234567890",
        session_name="Refactor",
        cwd=tmp_path / "ghostwriter",
        socket_path=tmp_path / "pi.sock",
        provider="openai-codex",
        model_id="gpt-5.6-sol",
        thinking_level="high",
    )

    assert target.label == "Refactor · gpt-5.6-sol · abcdef"
    assert "Refactor" in target.summary
    assert "openai-codex/gpt-5.6-sol:high" in target.summary
    assert "Directory" in target.details
    assert "openai-codex/gpt-5.6-sol · high" in target.details
    assert "PID 43210" in target.details


@pytest.mark.asyncio
async def test_pi_bridge_discovers_and_injects(tmp_path: Path) -> None:
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
        "sessionName": "Test session",
        "cwd": str(tmp_path),
        "socketPath": str(socket_path),
        "modelProvider": "anthropic",
        "modelId": "claude-sonnet",
        "thinkingLevel": "high",
        "skills": [
            {"name": "blueprint", "description": "Analyze standout codebases"},
            {"name": "teaching", "description": "Explain concepts"},
        ],
        "startedAt": "2026-01-01T00:00:00Z",
    }
    (tmp_path / "pi.json").write_text(json.dumps(registry), encoding="utf-8")

    try:
        client = PiBridgeClient(runtime_dir=tmp_path)
        targets = client.discover_targets()
        assert len(targets) == 1
        assert targets[0].model_name == "anthropic/claude-sonnet"
        assert [skill.token for skill in targets[0].skills] == [
            "/skill:blueprint",
            "/skill:teaching",
        ]
        assert targets[0].skills[0].description == "Analyze standout codebases"

        response = await client.inject(
            targets[0],
            text="draft",
            draft_id="draft-1",
            revision=2,
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


def test_pi_bridge_removes_stale_registry(tmp_path: Path) -> None:
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

    assert PiBridgeClient(runtime_dir=tmp_path).discover_targets() == []
    assert not registry_path.exists()
