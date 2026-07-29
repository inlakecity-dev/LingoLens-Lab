"""
translation_map.py

Stores translated text mapped to desktop coordinates.

The Translation Map is the central data structure used by LingoLens.
It is independent of OCR, translation, and the user interface.
"""


class TranslationMap:
    """
    Stores translation entries associated with desktop coordinates.

    Each entry has the following structure:

    {
        "bounds": (x, y, width, height),
        "original": "Original OCR text",
        "translation": "Translated text"
    }
    """

    def __init__(self):
        """Initialize an empty translation map."""
        self._entries = []

    def clear(self):
        """Remove all translation entries."""
        self._entries.clear()

    def add_entry(self, bounds, original, translation):
        """
        Add a new translation entry.

        Parameters
        ----------
        bounds : tuple
            Desktop coordinates in the form
            (x, y, width, height)

        original : str
            Original OCR text.

        translation : str
            Translated text.
        """
        self._entries.append(
            {
                "bounds": bounds,
                "original": original,
                "translation": translation,
            }
        )

    def get_entries(self):
        """
        Return all translation entries.

        Returns
        -------
        list
            List of translation entries.
        """
        return self._entries.copy()

    def get_translation_at(self, x, y):
        """
        Return the translation located at the given desktop coordinate.

        Parameters
        ----------
        x : int
            Desktop X coordinate.

        y : int
            Desktop Y coordinate.

        Returns
        -------
        dict | None
            Matching translation entry or None if no entry exists.
        """
        for entry in self._entries:
            left, top, width, height = entry["bounds"]

            if (
                left <= x <= left + width
                and top <= y <= top + height
            ):
                return entry

        return None