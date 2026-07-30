"""
translation_map.py

Stores translated text mapped to desktop coordinates.

The Translation Map is the central data structure used by LingoLens.
It is independent of OCR, translation, and the user interface.
"""

from dataclasses import dataclass


@dataclass(slots=True)
class TranslationEntry:
    """
    Represents one translated region on the Windows desktop.
    """

    bounds: tuple[int, int, int, int]
    original: str
    translation: str


class TranslationMap:
    """
    Stores translation entries associated with desktop coordinates.
    """

    def __init__(self):
        """Initialize an empty translation map."""
        self._entries: list[TranslationEntry] = []

    def clear(self):
        """Remove all translation entries."""
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
                bounds=bounds,
                original=original,
                translation=translation,
            )
        )

    def get_entries(self):
        """
        Return all translation entries.
        """

        return self._entries.copy()

    def get_translation_at(
        self,
        x,
        y,
    ):
        """
        Return the translation located at the given desktop coordinate.
        """

        for entry in self._entries:

            left, top, width, height = entry.bounds

            if (
                left <= x <= left + width
                and top <= y <= top + height
            ):
                return entry

        return None