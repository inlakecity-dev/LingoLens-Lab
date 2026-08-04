"""
core/lens_controller.py

Floating Lens controller.

Coordinates the Floating Lens backend.

Responsibilities
----------------
- Coordinate the Floating Lens backend.
- Provide translated data for the Floating Lens.
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
            Shared application controller.
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
        Capture and process the current workspace region.

        The processed snapshot is immediately used to
        update the TranslationMap.

        During the transition period the snapshot is
        still returned to the caller.
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
    ):
        """
        Return every translated desktop region visible
        inside the supplied Floating Lens viewport.

        This is the future primary API used by the
        Floating Lens once Live Translation continuously
        maintains the TranslationMap.
        """

        return self.controller.lens_controller.get_visible_translations(
            bounds
        )

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