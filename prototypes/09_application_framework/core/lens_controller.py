"""
core/lens_controller.py

Floating Lens controller.

Coordinates the Floating Lens workflow.

Responsibilities
----------------
- Request workspace snapshots from the Controller.
- Return the captured region and processing result.

This controller contains no capture, OCR, Translation,
History or UI logic.
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

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Workspace Capture
    # ------------------------------------------------------------------

    def capture_workspace(
        self,
        left: int,
        top: int,
        width: int,
        height: int,
    ) -> dict[str, Any]:
        """
        Capture and process the current workspace region.

        Parameters
        ----------
        left : int
            Left screen coordinate.

        top : int
            Top screen coordinate.

        width : int
            Capture width.

        height : int
            Capture height.

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
            "Capturing workspace."
        )

        return self.capture_snapshot(
            left,
            top,
            width,
            height,
        )

    # ------------------------------------------------------------------
    # Snapshot
    # ------------------------------------------------------------------

    def capture_snapshot(
        self,
        left: int,
        top: int,
        width: int,
        height: int,
    ) -> dict[str, Any]:
        """
        Request a workspace snapshot from the Controller.

        Parameters
        ----------
        left : int
            Left screen coordinate.

        top : int
            Top screen coordinate.

        width : int
            Capture width.

        height : int
            Capture height.

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

        snapshot = self.controller.image_pipeline.capture_snapshot(
            left,
            top,
            width,
            height,
        )

        return snapshot
        
