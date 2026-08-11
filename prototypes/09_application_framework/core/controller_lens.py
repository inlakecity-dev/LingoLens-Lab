"""
core/controller_lens.py

Floating Lens controller service.

Coordinates TranslationMap interactions for the
Floating Lens workflow.

## Responsibilities

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
        Update the TranslationMap using positional
        translation entries produced by the image pipeline.

        Each translated OCR block is stored using its
        own desktop coordinates.

        The Floating Lens therefore does not depend on
        one large snapshot entry.
        """

        if result["status"] != "success":
            return

        entries = result.get(
            "entries",
            [],
        )

        print(
            "\n----- TranslationMap Update -----"
        )

        print(
            "Processed Regions: "
            f"{len(entries)}"
        )

        # --------------------------------------------------
        # Remove previous translations belonging to the
        # captured workspace.
        #
        # The new positional entries will replace them.
        # --------------------------------------------------

        self.controller.translation_map.remove_entries_in_region(
            captured_region.bounds
        )

        # --------------------------------------------------
        # Add every positional translation independently.
        # --------------------------------------------------

        for index, entry in enumerate(
            entries,
            start=1,
        ):

            bounds = entry["bounds"]
            original = entry["original"]
            translation = entry["translation"]

            self.controller.translation_map.add_entry(
                bounds,
                original,
                translation,
            )

            print(
                f"[{index:03d}] "
                f"Bounds={bounds}"
            )

            print(
                f"       Original   : "
                f"{original[:100]}"
            )

            print(
                f"       Translation: "
                f"{translation[:100]}"
            )

        print(
            "---------------------------------\n"
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
        Return every translated desktop region
        intersecting the supplied Floating Lens viewport.

        This method performs no capture,
        OCR or translation.
        """

        translation_map = (
            self.controller.translation_map
        )

        all_entries = (
            translation_map.get_entries()
        )

        visible_entries = (
            translation_map.get_entries_in_region(
                bounds
            )
        )

        print(
            "\n----- Floating Lens Map Query -----"
        )

        print(
            "Lens Bounds : "
            f"{bounds[0]}, "
            f"{bounds[1]}, "
            f"{bounds[2]}, "
            f"{bounds[3]}"
        )

        print(
            "Map Entries : "
            f"{len(all_entries)}"
        )

        print(
            "Visible     : "
            f"{len(visible_entries)}"
        )

        for entry in visible_entries:

            print(
                "Entry       : "
                f"ID={entry.id} "
                f"Bounds={entry.bounds}"
            )

        print(
            "------------------------------------"
        )

        return visible_entries