"""
core/lens_controller.py

Floating Lens controller.

Coordinates the Floating Lens workflow.

Responsibilities
----------------
- Capture a snapshot.
- Store the captured image in the workspace.
- Process the image using the shared Controller.
- Store the processing result.
- Provide access to the workspace.

This controller contains no OCR, Translation,
History or UI logic.
"""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

from core.lens_capture import LensCapture
from core.lens_workspace import LensWorkspace

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
            Shared application controller used to process images.
        """

        self.controller = controller

        self.capture_service = LensCapture()
        self.workspace = LensWorkspace()

        logger.info(
            self.MODULE,
            "Lens controller initialized."
        )

    # ------------------------------------------------------------------
    # Workspace
    # ------------------------------------------------------------------

    def get_workspace(self) -> LensWorkspace:
        """
        Return the current workspace.
        """

        return self.workspace

    def clear_workspace(self) -> None:
        """
        Clear the current workspace.
        """

        self.workspace.clear()

        logger.info(
            self.MODULE,
            "Workspace cleared."
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
        Capture a screen region and process it.

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
            Processing result returned by Controller.process_image().
        """

        logger.info(
            self.MODULE,
            "Starting snapshot capture."
        )

        image = self.capture_service.capture(
            left,
            top,
            width,
            height,
        )

        self.workspace.set_image(image)

        result = self.controller.process_image(image)

        self.workspace.set_result(result)

        logger.info(
            self.MODULE,
            "Snapshot processing completed."
        )

        return result