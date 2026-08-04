"""
core/controller_lens.py

Floating Lens controller service.

Coordinates TranslationMap interactions for the
Floating Lens workflow.

Responsibilities
----------------
- Update the TranslationMap.
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

    def update_translation_map(
        self,
        captured_region,
        result,
    ):
        """
        Update the TranslationMap using the latest
        processed snapshot.
        """

        if result["status"] != "success":
            return
            
        print("\n----- TranslationMap Update -----")
        print("Original OCR:")
        print(result["original"])
        print()
        print("Translation:")
        print(result["translation"])
        print("---------------------------------\n")

        self.controller.translation_map.update_region(
            captured_region.bounds,
            result["original"],
            result["translation"],
        )

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