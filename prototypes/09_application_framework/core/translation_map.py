"""
translation_map.py

Translation Map

The Translation Map is the central data model used by LingoLens.

It represents the translated state of the current Windows
Virtual Desktop.

Responsibilities
----------------
- Store translated desktop regions.
- Update desktop regions.
- Remove outdated regions.
- Return translated regions visible inside a desktop area.

This class does NOT:
- Perform OCR
- Perform Translation
- Detect Desktop changes
- Manage History
- Manage Cache
- Render the UI
"""

from dataclasses import dataclass
from itertools import count


# ------------------------------------------------------------------
# Runtime ID Generator
# ------------------------------------------------------------------

_entry_id = count(1)


# ------------------------------------------------------------------
# Translation Entry
# ------------------------------------------------------------------

@dataclass(slots=True)
class TranslationEntry:
    """
    Represents one translated desktop region.
    """

    id: int

    # (left, top, width, height)
    bounds: tuple[int, int, int, int]

    original: str

    translation: str


# ------------------------------------------------------------------
# Translation Map
# ------------------------------------------------------------------

class TranslationMap:
    """
    Represents the translated state of the current
    Windows Virtual Desktop.

    The Translation Map is the application's
    Single Source of Truth for translated desktop
    regions.
    """

    def __init__(self):
        """
        Initialize an empty Translation Map.
        """

        self._entries: list[TranslationEntry] = []

    # --------------------------------------------------
    # Map Management
    # --------------------------------------------------

    def clear(self):
        """
        Remove every translated desktop region.
        """

        self._entries.clear()

    def is_empty(self):
        """
        Return True if the Translation Map contains
        no translated regions.
        """

        return len(self._entries) == 0

    def entry_count(self):
        """
        Return the number of translated regions.
        """

        return len(self._entries)

    # --------------------------------------------------
    # Desktop Updates
    # --------------------------------------------------

    def update_region(
        self,
        bounds,
        original,
        translation,
    ):
        """
        Update one desktop region.

        Any previous translated regions intersecting
        the supplied bounds are removed before the
        new translated region is inserted.
        """

        self._remove_entries_in_region(bounds)

        self._add_entry(
            bounds,
            original,
            translation,
        )

    # --------------------------------------------------
    # Internal Update Helpers
    # --------------------------------------------------

    def _add_entry(
        self,
        bounds,
        original,
        translation,
    ):
        """
        Insert one translated desktop region.
        """

        self._entries.append(
            TranslationEntry(
                id=next(_entry_id),
                bounds=bounds,
                original=original,
                translation=translation,
            )
        )

    def _remove_entries_in_region(
        self,
        bounds,
    ):
        """
        Remove every translated region intersecting
        the supplied desktop bounds.
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

    # --------------------------------------------------
    # Queries
    # --------------------------------------------------

    def get_entries(self):
        """
        Return every translated desktop region.
        """

        return self._entries.copy()

    def get_entries_in_region(
        self,
        bounds,
    ):
        """
        Return every translated region intersecting
        the supplied desktop region.
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