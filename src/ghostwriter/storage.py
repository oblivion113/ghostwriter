from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path

from PIL import Image, UnidentifiedImageError
from platformdirs import user_cache_path, user_state_path

from .model import Draft

_IMAGE_EXTENSIONS = {
    "BMP": ".bmp",
    "GIF": ".gif",
    "JPEG": ".jpg",
    "PNG": ".png",
    "WEBP": ".webp",
}


class DraftStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or user_state_path("ghostwriter") / "draft.json"

    def load(self) -> Draft:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise TypeError("Draft root must be an object")
            return Draft.from_dict(data)
        except FileNotFoundError:
            return Draft()
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            broken = self.path.with_suffix(f".broken-{os.getpid()}.json")
            try:
                self.path.replace(broken)
            except OSError:
                pass
            return Draft()

    def save(self, draft: Draft) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        temporary = self.path.with_suffix(f".tmp-{os.getpid()}")
        temporary.write_text(
            json.dumps(draft.to_dict(), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        os.chmod(temporary, 0o600)
        temporary.replace(self.path)


class ImageCache:
    def __init__(self, directory: Path | None = None) -> None:
        self.directory = directory or user_cache_path("ghostwriter") / "images"

    @staticmethod
    def _digest(source: Path) -> str:
        digest = hashlib.sha256()
        with source.open("rb") as image_file:
            while chunk := image_file.read(1024 * 1024):
                digest.update(chunk)
        return digest.hexdigest()

    def stage(self, source: Path) -> Path:
        source = source.expanduser().resolve(strict=True)
        if not source.is_file():
            raise ValueError(f"Not a file: {source}")

        try:
            with Image.open(source) as image:
                image_format = image.format
                image.verify()
        except (UnidentifiedImageError, OSError) as error:
            raise ValueError(f"Unsupported or invalid image: {source}") from error

        extension = _IMAGE_EXTENSIONS.get(image_format or "")
        if extension is None:
            raise ValueError(f"Unsupported image format: {image_format or 'unknown'}")

        digest = self._digest(source)
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        destination = self.directory / f"{digest}{extension}"
        if not destination.exists():
            temporary = destination.with_suffix(f"{extension}.tmp-{os.getpid()}")
            shutil.copyfile(source, temporary)
            os.chmod(temporary, 0o600)
            temporary.replace(destination)
        return destination
