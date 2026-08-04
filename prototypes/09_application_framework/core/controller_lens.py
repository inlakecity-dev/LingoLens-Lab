"""
core/controller_lens.py

Floating Lens controller service.

Coordinates every TranslationMap interaction for the
Floating Lens workflow.

Responsibilities
----------------
- Update the TranslationMap.
- Remove outdated translations.
- Return visible translations for the Floating Lens.

This service does NOT:
- Capture the desktop.
- Perform OCR.
- Perform Translation.
- Manage Live Mode.
"""

from __future__ import annotations

from logger import logger


class ControllerLens:
    """
    Coordinates TranslationMap access for the
    Floating Lens workflow.
    """

    MODULE = "ControllerLens"

    def __init__(self, controller):
        """
        Parameters
        ----------
        controller
            Shared application controller.
        """

        self.controller = controller

        logger.info(
            self.MODULE,
            "Controller lens service initialized."
        )

    # --------------------------------------------------
    # Translation Map
    # --------------------------------------------------

    def add_translation(
        self,
        bounds,
        original,
        translation,
    ):
        """
        Add a translated region to the TranslationMap.
        """

        self.controller.translation_map.add_entry(
            bounds,
            original,
            translation,
        )

    def remove_translations(
        self,
        bounds,
    ):
        """
        Remove outdated translations from the
        supplied desktop region.
        """

        remove_method = getattr(
            self.controller.translation_map,
            "remove_entries_in_region",
            None,
        )

        if callable(remove_method):
            remove_method(bounds)

    # --------------------------------------------------
    # Floating Lens
    # --------------------------------------------------

    def on_lens_moved(
        self,
        bounds,
    ):
        """
        Called whenever the Floating Lens moves.

        Returns every translation visible inside
        the supplied desktop region.
        """

        return self.get_visible_translations(
            bounds
        )

    def get_visible_translations(
        self,
        bounds,
    ):
        """
        Return every translation visible inside
        the supplied desktop region.
        """

        return self.controller.translation_map.get_entries_in_region(
            bounds
        )

    # --------------------------------------------------
    # Convenience Helpers
    # --------------------------------------------------

    def update_translation_map(
        self,
        captured_region,
        result,
    ):
        """
        Update the TranslationMap using the
        latest processed snapshot.
        """

        if result["status"] != "success":
            return

        self.add_translation(
            captured_region.bounds,
            result["original"],
            result["translation"],
        )