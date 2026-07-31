"""
translation_map.py

Stores translated text mapped to desktop coordinates.

The Translation Map is the central data structure used by LingoLens.
It represents only the currently active desktop and is independent
of OCR, translation, caching, and the user interface.
"""

from dataclasses import dataclass
from itertools import count


# Simple runtime ID generator.
_entry_id = count(1)


@dataclass(slots=True)
class TranslationEntry:
    """
    Represents one translated region on the Windows desktop.
    """

    id: int
    bounds: tuple[int, int, int, int]
    original: str
    translation: str


class TranslationMap:
    """
    Stores translation entries associated with desktop coordinates.

    This class is intentionally lightweight.

    Responsibilities:
        - Store active translation entries.
        - Remove entries inside a changed region.
        - Return entries inside a requested region.

    It does NOT:
        - Perform OCR
        - Perform translation
        - Detect desktop changes
        - Manage cache
    """

    def __init__(self):
        """Initialize an empty translation map."""
        self._entries: list[TranslationEntry] = []

    def clear(self):
        """
        Remove all translation entries.

        Used when an entirely new desktop becomes active.
        """
        self._entries.clear()

    def add_entry(
        self,
        bounds,
        original,
        translation,
    ):
        """
        Add a translation entry.
        """

        self._entries.append(
            TranslationEntry(
                id=next(_entry_id),
                bounds=bounds,
                original=original,
                translation=translation,
            )
        )

    def remove_entries_in_region(
        self,
        bounds,
    ):
        """
        Remove every entry intersecting the specified desktop region.
        """

        left, top, width, height = bounds
        right = left + width
        bottom = top + height

        remaining = []

        for entry in self._entries:

            e_left, e_top, e_width, e_height = entry.bounds
            e_right = e_left + e_width
            e_bottom = e_top + e_height

            intersects = not (
                e_right < left
                or e_left > right
                or e_bottom < top
                or e_top > bottom
            )

            if not intersects:
                remaining.append(entry)

        self._entries = remaining

    def get_entries(self):
        """
        Return all translation entries.
        """

        return self._entries.copy()

    def get_entries_in_region(
        self,
        bounds,
    ):
        """
        Return all entries intersecting the specified desktop region.
        """

        left, top, width, height = bounds
        right = left + width
        bottom = top + height

        visible_entries = []

        for entry in self._entries:

            e_left, e_top, e_width, e_height = entry.bounds
            e_right = e_left + e_width
            e_bottom = e_top + e_height

            intersects = not (
                e_right < left
                or e_left > right
                or e_bottom < top
                or e_top > bottom
            )

            if intersects:
                visible_entries.append(entry)

        return visible_entries