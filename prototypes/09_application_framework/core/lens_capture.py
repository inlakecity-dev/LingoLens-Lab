"""
core/lens_capture.py

Floating Lens screen capture service.

This module is responsible only for capturing the screen content
beneath the Floating Lens.

Responsibilities
----------------
- Capture a rectangular screen region.
- Return a PIL.Image object.
- Remain independent of UI, OCR and Translation.

This service is intended for the Floating Lens workflow and should
not replace the application's existing capture.py module.
"""

from __future__ import annotations

from PIL import Image, ImageGrab

from logger import logger


class LensCapture:
    """
    Service responsible for capturing the screen beneath the
    Floating Lens.
    """

    MODULE = "LensCapture"

    def capture(
        self,
        left: int,
        top: int,
        width: int,
        height: int,
    ) -> Image.Image:
        """
        Capture a rectangular region.

        Parameters
        ----------
        left : int
            Left screen coordinate.

        top : int
            Top screen coordinate.

        width : int
            Width of capture region.

        height : int
            Height of capture region.

        Returns
        -------
        PIL.Image.Image
            Captured image.
        """

        if width <= 0:
            raise ValueError("Width must be greater than zero.")

        if height <= 0:
            raise ValueError("Height must be greater than zero.")

        right = left + width
        bottom = top + height

        logger.info(
            self.MODULE,
            f"Capturing region ({left}, {top}) "
            f"{width}x{height}"
        )

        image = ImageGrab.grab(
            bbox=(left, top, right, bottom)
        )

        logger.info(
            self.MODULE,
            f"Capture completed ({image.width}x{image.height})"
        )

        return image