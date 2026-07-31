"""
core/capture_engine.py

Capture Engine

Responsible for capturing images from the Windows desktop.

Responsibilities
----------------
- Capture the entire desktop.
- Capture a rectangular desktop region.

This module contains no OCR, Translation or UI logic.
"""

from dataclasses import dataclass

from PIL import Image, ImageGrab


@dataclass(slots=True)
class CapturedRegion:
    """
    Represents a captured region of the Windows desktop.
    """

    image: Image.Image
    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        """Width of the captured region."""
        return self.right - self.left

    @property
    def height(self) -> int:
        """Height of the captured region."""
        return self.bottom - self.top

    @property
    def bounds(self) -> tuple[int, int, int, int]:
        """
        Return bounds in the format expected by TranslationMap.

        Returns
        -------
        tuple
            (left, top, width, height)
        """
        return (
            self.left,
            self.top,
            self.width,
            self.height,
        )


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
) -> CapturedRegion:
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
    CapturedRegion
        Captured desktop region and its coordinates.
    """

    image = ImageGrab.grab(
        bbox=(left, top, right, bottom)
    )

    return CapturedRegion(
        image=image,
        left=left,
        top=top,
        right=right,
        bottom=bottom,
    )


def capture_bounds(
    bounds: tuple[int, int, int, int],
) -> CapturedRegion:
    """
    Capture a region using TranslationMap bounds.

    Parameters
    ----------
    bounds : tuple
        Region in the format:
        (left, top, width, height)

    Returns
    -------
    CapturedRegion
        Captured desktop region.
    """

    left, top, width, height = bounds

    return capture_region(
        left,
        top,
        left + width,
        top + height,
    )