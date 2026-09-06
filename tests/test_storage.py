from pathlib import Path

from ghostwriter.model import Attachment, Draft, refresh_attachment_editor_paths
from ghostwriter.storage import DraftStore, clear_legacy_image_cache


def test_draft_store_round_trip(tmp_path: Path) -> None:
    store = DraftStore(tmp_path / "state" / "draft.json")
    draft = Draft(
        text="hello",
        attachments=[Attachment("file", "/tmp/source", editor_path="/tmp/source")],
        revision=4,
    )

    store.save(draft)
    restored = store.load()

    assert restored.to_dict() == draft.to_dict()


def test_version_one_draft_migrates_verbose_attachment_marker() -> None:
    attachment = Attachment(
        "file",
        "/tmp/context.md",
        id="abcdef1234567890",
    )
    restored = Draft.from_dict(
        {
            "version": 1,
            "text": f"Review {attachment.legacy_editor_token}",
            "attachments": [attachment.to_dict()],
        }
    )

    assert restored.text == "Review @context.md"
    assert restored.attachments[0].editor_token == "@context.md"


def test_attachment_editor_paths_follow_root_and_display_mode(tmp_path: Path) -> None:
    project = tmp_path / "project"
    inside = Attachment("file", str(project / "inside.md"))
    outside = Attachment("file", str(tmp_path / "outside.md"))
    attachments = [inside, outside]

    text, changed = refresh_attachment_editor_paths(
        "Review @inside.md and @outside.md",
        attachments,
        project,
        "auto",
    )

    assert changed
    assert text == f"Review @inside.md and @{tmp_path.as_posix()}/outside.md"

    text, changed = refresh_attachment_editor_paths(text, attachments, project, "full")

    assert changed
    assert text == (
        f"Review @{project.as_posix()}/inside.md and @{tmp_path.as_posix()}/outside.md"
    )


def test_legacy_image_cache_is_removed(tmp_path: Path) -> None:
    cache = tmp_path / "images"
    cache.mkdir()
    (cache / "large-image.png").write_bytes(b"cached")

    clear_legacy_image_cache(cache)

    assert not cache.exists()


def test_version_three_folder_attachment_gains_directory_kind_and_slash(
    tmp_path: Path,
) -> None:
    directory = tmp_path / "notes"
    directory.mkdir()

    restored = Draft.from_dict(
        {
            "version": 3,
            "text": "Review @notes",
            "attachments": [
                {
                    "kind": "file",
                    "source_path": str(directory),
                    "id": "abcdef1234567890",
                }
            ],
        }
    )

    assert restored.text == "Review @notes/"
    assert restored.attachments[0].kind == "directory"
    assert restored.attachments[0].display_name == "notes/"


def test_version_two_draft_discards_staged_attachment_path() -> None:
    restored = Draft.from_dict(
        {
            "version": 2,
            "attachments": [
                {
                    "kind": "image",
                    "source_path": "/private/source.png",
                    "injected_path": "/cache/hash.png",
                    "id": "abcdef1234567890",
                }
            ],
        }
    )

    assert restored.to_dict()["version"] == 5
    assert restored.attachments[0].source == Path("/private/source.png")
    assert "injected_path" not in restored.attachments[0].to_dict()
