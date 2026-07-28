"""
core/lens_workspace.py

Floating Lens workspace.

This module stores the current workspace used by the Floating Lens.

Responsibilities
----------------
- Store the current captured image.
- Store the latest processing result.
- Provide a simple shared state between the Lens Controller
  and the Floating Lens UI.

This class intentionally contains no OCR, Translation,
or UI logic.
"""

from __future__ import annotations

from typing import Any

from PIL import Image

from logger import logger


class LensWorkspace:
    """
    Shared workspace for the Floating Lens.

    The workspace holds the latest captured image together with
    the corresponding OCR/translation result.
    """

    MODULE = "LensWorkspace"

    def __init__(self) -> None:
        """Initialize an empty workspace."""

        self._image: Image.Image | None = None
        self._result: dict[str, Any] | None = None

        logger.info(self.MODULE, "Workspace initialized.")

    # ------------------------------------------------------------------
    # Image
    # ------------------------------------------------------------------

    def set_image(self, image: Image.Image) -> None:
        """
        Store the current captured image.

        Parameters
        ----------
        image : PIL.Image.Image
            Captured image.
        """

        self._image = image

        logger.info(
            self.MODULE,
            f"Image stored ({image.width}x{image.height})."
        )

    def get_image(self) -> Image.Image | None:
        """
        Return the stored image.

        Returns
        -------
        PIL.Image.Image | None
        """

        return self._image

    def has_image(self) -> bool:
        """
        Return True if an image exists.
        """

        return self._image is not None

    # ------------------------------------------------------------------
    # Processing Result
    # ------------------------------------------------------------------

    def set_result(self, result: dict[str, Any]) -> None:
        """
        Store the OCR/translation result.

        Parameters
        ----------
        result : dict
            Result returned from Controller.process_image().
        """

        self._result = result

        logger.info(
            self.MODULE,
            "Processing result stored."
        )

    def get_result(self) -> dict[str, Any] | None:
        """
        Return the latest processing result.

        Returns
        -------
        dict | None
        """

        return self._result

    def has_result(self) -> bool:
        """
        Return True if a processing result exists.
        """

        return self._result is not None

    # ------------------------------------------------------------------
    # Workspace
    # ------------------------------------------------------------------

    def clear(self) -> None:
        """
        Clear the entire workspace.
        """

        self._image = None
        self._result = None

        logger.info(
            self.MODULE,
            "Workspace cleared."
        )