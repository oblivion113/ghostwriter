from __future__ import annotations

import unicodedata

from textual._wrap import compute_wrap_offsets
from textual.document._wrapped_document import WrappedDocument


def _is_wide_character(character: str) -> bool:
    return not character.isspace() and unicodedata.east_asian_width(character) in {"W", "F"}


def natural_wrap_offsets(text: str, width: int, tab_size: int) -> list[int]:
    """Wrap prose at spaces and between wide characters without changing its text."""
    if not width or len(text) < 2:
        return compute_wrap_offsets(text, width, tab_size)

    virtual: list[str] = []
    boundary_to_source = [0]
    previous = text[0]
    virtual.append(previous)
    boundary_to_source.append(1)
    for source_index, character in enumerate(text[1:], 1):
        if (
            not previous.isspace()
            and not character.isspace()
            and (_is_wide_character(previous) or _is_wide_character(character))
        ):
            # File Separator is regex whitespace with zero terminal-cell width. It exposes
            # a line-break opportunity to Textual without affecting measured width.
            virtual.append("\x1c")
            boundary_to_source.append(source_index)
        virtual.append(character)
        boundary_to_source.append(source_index + 1)
        previous = character

    if len(virtual) == len(text):
        return compute_wrap_offsets(text, width, tab_size)

    source_offsets: list[int] = []
    for offset in compute_wrap_offsets("".join(virtual), width, tab_size):
        source_offset = boundary_to_source[offset]
        if 0 < source_offset < len(text) and (
            not source_offsets or source_offsets[-1] != source_offset
        ):
            source_offsets.append(source_offset)
    return source_offsets


class NaturalWrappedDocument(WrappedDocument):
    """Textual's incremental wrapped document with East Asian break opportunities."""

    def _update_offsets(self, first_line: int, last_line: int) -> None:
        if not self.document.lines:
            return
        first_line = max(0, first_line)
        last_line = min(last_line, self.document.line_count - 1)
        for line_index in range(first_line, last_line + 1):
            offsets = natural_wrap_offsets(
                self.document.get_line(line_index),
                self._width,
                self._tab_width,
            )
            previous_height = len(self._wrap_offsets[line_index]) + 1
            next_height = len(offsets) + 1
            if offsets == self._wrap_offsets[line_index]:
                continue

            first_offset = self._line_index_to_offsets[line_index][0]
            self._wrap_offsets[line_index] = offsets
            self._offset_to_line_info[first_offset : first_offset + previous_height] = [
                (line_index, section) for section in range(next_height)
            ]
            self._line_index_to_offsets[line_index] = list(
                range(first_offset, first_offset + next_height)
            )

            shift = next_height - previous_height
            if shift:
                for following_line in range(line_index + 1, self.document.line_count):
                    self._line_index_to_offsets[following_line] = [
                        offset + shift
                        for offset in self._line_index_to_offsets[following_line]
                    ]

    def wrap(self, width: int, tab_width: int | None = None) -> None:
        super().wrap(width, tab_width)
        self._update_offsets(0, self.document.line_count - 1)

    def wrap_range(
        self,
        start: tuple[int, int],
        old_end: tuple[int, int],
        new_end: tuple[int, int],
    ) -> None:
        super().wrap_range(start, old_end, new_end)
        self._update_offsets(min(start[0], new_end[0]), max(start[0], new_end[0]))
