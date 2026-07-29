"""
core/capture.py

Capture Engine

Responsible for capturing images from the Windows desktop.

Responsibilities
----------------
- Capture the entire desktop.
- Capture a rectangular desktop region.

This module contains no OCR, Translation or UI logic.
"""

from PIL import Image, ImageGrab


def capture_fullscreen() -> Image.Image:
    """
    Capture the entire Windows desktop.

    Returns
    -------
    PIL.Image.Image
        Full desktop screenshot.
    """

    return ImageGrab.grab()


def capture_region(
    left: int,
    top: int,
    right: int,
    bottom: int,
) -> Image.Image:
    """
    Capture a rectangular desktop region.

    Parameters
    ----------
    left : int
        Left desktop coordinate.

    top : int
        Top desktop coordinate.

    right : int
        Right desktop coordinate.

    bottom : int
        Bottom desktop coordinate.

    Returns
    -------
    PIL.Image.Image
        Captured image.
    """

    return ImageGrab.grab(
        bbox=(left, top, right, bottom)
    )