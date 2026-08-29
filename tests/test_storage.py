from pathlib import Path

from PIL import Image

from ghostwriter.model import Attachment, Draft
from ghostwriter.storage import DraftStore, ImageCache


def test_draft_store_round_trip(tmp_path: Path) -> None:
    store = DraftStore(tmp_path / "state" / "draft.json")
    draft = Draft(
        text="hello",
        attachments=[Attachment("file", "/tmp/source", "/tmp/source")],
        revision=4,
    )

    store.save(draft)
    restored = store.load()

    assert restored.to_dict() == draft.to_dict()


def test_image_cache_is_content_addressed(tmp_path: Path) -> None:
    source = tmp_path / "source.png"
    Image.new("RGB", (3, 2), "#7aa2f7").save(source)
    cache = ImageCache(tmp_path / "cache")

    first = cache.stage(source)
    second = cache.stage(source)

    assert first == second
    assert first.suffix == ".png"
    assert first.read_bytes() == source.read_bytes()
