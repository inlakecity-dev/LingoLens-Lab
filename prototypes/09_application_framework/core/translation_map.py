"""
translation_map.py

Stores translated text mapped to desktop coordinates.

The Translation Map is the central data structure used by
LingoLens.

It represents the currently translated Windows desktop and
acts as the single source of truth for every translated
desktop region.

The map is intentionally independent from OCR, Translation,
Desktop Observation and the Floating Lens.
"""

from dataclasses import dataclass
from itertools import count


# --------------------------------------------------
# Runtime Entry ID Generator
# --------------------------------------------------

_entry_id = count(1)


# --------------------------------------------------
# Translation Entry
# --------------------------------------------------

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


# --------------------------------------------------
# Translation Map
# --------------------------------------------------

class TranslationMap:
    """
    Represents the translated Windows desktop.

    Responsibilities
    ----------------
    - Store translated desktop regions.
    - Remove outdated regions.
    - Return visible regions.
    - Store desktop metadata.

    This class does NOT:
    - Capture the desktop.
    - Perform OCR.
    - Perform Translation.
    - Observe desktop changes.
    """

    def __init__(self):
        """
        Initialize an empty TranslationMap.
        """

        #
        # Desktop metadata
        #

        # Entire virtual desktop bounds.
        self._desktop_bounds = (0, 0, 0, 0)

        # Physical monitor layout.
        self._monitors = []

        # Has this desktop model been initialized?
        self._initialized = False

        # Incremented whenever the desktop is rebuilt.
        self._generation = 0

        #
        # Translation entries
        #

        self._entries: list[TranslationEntry] = []

    # --------------------------------------------------
    # Desktop Metadata
    # --------------------------------------------------

    def set_desktop_bounds(
        self,
        bounds,
    ):
        """
        Store the virtual desktop bounds.
        """

        self._desktop_bounds = bounds

    def get_desktop_bounds(self):
        """
        Return the virtual desktop bounds.
        """

        return self._desktop_bounds

    def set_monitors(
        self,
        monitors,
    ):
        """
        Store monitor layout information.
        """

        self._monitors = list(monitors)

    def get_monitors(self):
        """
        Return monitor layout.
        """

        return self._monitors.copy()

    def mark_initialized(self):
        """
        Mark the TranslationMap as initialized.
        """

        self._initialized = True

    def reset(self):
        """
        Reset the TranslationMap.

        Used when constructing a completely new
        desktop model.
        """

        self.clear()

        self._initialized = False

        self._generation = 0

    def is_initialized(self):
        """
        Return whether the desktop model has been
        initialized.
        """

        return self._initialized

    def next_generation(self):
        """
        Advance to the next desktop generation.

        A future full desktop rebuild increments
        this value.
        """

        self._generation += 1

        return self._generation

    def get_generation(self):
        """
        Return the current desktop generation.
        """

        return self._generation

    # --------------------------------------------------
    # Translation Entries
    # --------------------------------------------------

    def clear(self):
        """
        Remove every translation entry.
        """

        self._entries.clear()

    def add_entry(
        self,
        bounds,
        original,
        translation,
    ):
        """
        Add a translated desktop region.
        """

        self._entries.append(
            TranslationEntry(
                id=next(_entry_id),
                bounds=bounds,
                original=original,
                translation=translation,
            )
        )

    def update_region(
        self,
        bounds,
        original,
        translation,
    ):
        """
        Replace every translated entry intersecting
        the supplied desktop region.
        """

        self.remove_entries_in_region(bounds)

        self.add_entry(
            bounds,
            original,
            translation,
        )

    def remove_entries_in_region(
        self,
        bounds,
    ):
        """
        Remove every translated region intersecting
        the supplied desktop region.
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
        Return every translated desktop region
        intersecting the supplied viewport.
        """

        left, top, width, height = bounds

        right = left + width
        bottom = top + height

        visible = []

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
                visible.append(entry)

        return visible

    def entry_count(self):
        """
        Return the number of translated regions.
        """

        return len(self._entries)