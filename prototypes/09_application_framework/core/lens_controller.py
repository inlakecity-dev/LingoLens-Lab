"""
core/lens_controller.py

Floating Lens controller.

Coordinates the Floating Lens backend.

## Responsibilities

- Coordinate the Floating Lens backend.
- Provide translated data for the Floating Lens.
- Query the TranslationMap using the current Lens viewport.
- Support the transition from snapshot-based translation
  to TranslationMap-based rendering.

This controller does NOT:

- Perform desktop capture.
- Perform OCR.
- Perform translation.
- Update the TranslationMap.
- Render the UI.
"""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from controller import Controller

from logger import logger


class LensController:
    """
    Coordinates the Floating Lens backend workflow.
    """

    MODULE = "LensController"

    def __init__(
        self,
        controller: Controller,
    ) -> None:
        """
        Parameters
        ----------
        controller : Controller
            Shared application Controller.
        """

        self.controller = controller

        self.running = False

        logger.info(
            self.MODULE,
            "Lens controller initialized."
        )

    # --------------------------------------------------
    # Lifecycle
    # --------------------------------------------------

    def start(self) -> None:
        """
        Start the Floating Lens backend.
        """

        if self.running:
            return

        self.running = True

        logger.info(
            self.MODULE,
            "Lens backend started."
        )

    def stop(self) -> None:
        """
        Stop the Floating Lens backend.
        """

        if not self.running:
            return

        self.running = False

        logger.info(
            self.MODULE,
            "Lens backend stopped."
        )

    # --------------------------------------------------
    # Workspace Capture
    # --------------------------------------------------

    def capture_workspace(
        self,
        left: int,
        top: int,
        width: int,
        height: int,
    ) -> dict[str, Any]:
        """
        Capture and process a workspace region.

        This method is retained as a development/testing
        workflow for populating the TranslationMap.

        The Floating Lens itself should use
        get_visible_translations() to obtain translated
        content rather than translating whenever the Lens
        moves.
        """

        logger.info(
            self.MODULE,
            "Capturing workspace."
        )

        snapshot = self.capture_snapshot(
            left,
            top,
            width,
            height,
        )

        self.controller.lens_controller.update_translation_map(
            snapshot["captured_region"],
            snapshot["result"],
        )

        return snapshot

    # --------------------------------------------------
    # Translation Map
    # --------------------------------------------------

    def get_visible_translations(
        self,
        bounds: tuple[int, int, int, int],
    ) -> list[Any]:
        """
        Return TranslationMap entries that intersect the
        Floating Lens viewport.

        Parameters
        ----------
        bounds : tuple[int, int, int, int]
            Floating Lens viewport in absolute Windows
            desktop coordinates.

            Format:
                (left, top, width, height)

        Returns
        -------
        list
            TranslationMap entries whose desktop bounds
            intersect the Floating Lens viewport.

        Notes
        -----
        Moving the Lens does NOT trigger capture,
        OCR or translation.

        The Floating Lens is only a viewport over the
        existing TranslationMap.
        """

        if not self.running:
            return []

        if len(bounds) != 4:
            raise ValueError(
                "Lens bounds must contain "
                "(left, top, width, height)."
            )

        left, top, width, height = bounds

        if width <= 0 or height <= 0:
            logger.info(
                self.MODULE,
                "Floating Lens query skipped because "
                f"viewport bounds are invalid: {bounds}"
            )

            return []

        right = left + width
        bottom = top + height

        translation_map = getattr(
            self.controller,
            "translation_map",
            None,
        )

        if translation_map is None:
            logger.warning(
                self.MODULE,
                "Floating Lens query failed because "
                "TranslationMap is unavailable."
            )

            return []

        entries = translation_map.get_entries()

        visible_entries = []

        for entry in entries:

            entry_left, entry_top, entry_width, entry_height = (
                entry.bounds
            )

            entry_right = (
                entry_left
                + entry_width
            )

            entry_bottom = (
                entry_top
                + entry_height
            )

            intersects = not (
                entry_right < left
                or entry_left > right
                or entry_bottom < top
                or entry_top > bottom
            )

            if intersects:
                visible_entries.append(entry)

        logger.info(
            self.MODULE,
            "Floating Lens Map Query: "
            f"bounds={bounds}, "
            f"map_entries={len(entries)}, "
            f"visible_entries={len(visible_entries)}"
        )

        return visible_entries

    # --------------------------------------------------
    # Snapshot
    # --------------------------------------------------

    def capture_snapshot(
        self,
        left: int,
        top: int,
        width: int,
        height: int,
    ) -> dict[str, Any]:
        """
        Request a workspace snapshot from the shared
        image processing pipeline.

        Returns
        -------
        dict
            {
                "captured_region": CapturedRegion,
                "result": dict
            }
        """

        logger.info(
            self.MODULE,
            "Starting snapshot capture."
        )

        return self.controller.image_pipeline.capture_snapshot(
            left,
            top,
            width,
            height,
        )