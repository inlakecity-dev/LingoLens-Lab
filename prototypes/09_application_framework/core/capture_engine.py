"""
core/capture_engine.py

Capture Engine

Responsible for capturing images from the Windows desktop.

The native DesktopVisionEngine provides the complete virtual desktop.
Python performs region cropping on the captured image.

This module contains no OCR, Translation or UI logic.
"""

import atexit
import ctypes
import os

from dataclasses import dataclass

from pathlib import Path

from PIL import Image


# ------------------------------------------------------------
# Native bridge image structure
# ------------------------------------------------------------

class DVEPB_Image(ctypes.Structure):
    """
    Native image structure exposed by
    DesktopVisionEnginePythonBridge.dll.
    """

    _fields_ = [
        ("width", ctypes.c_uint32),
        ("height", ctypes.c_uint32),
        ("bytesPerPixel", ctypes.c_uint32),
        ("pixels", ctypes.POINTER(ctypes.c_uint8)),
        ("pixelBytes", ctypes.c_uint64),
    ]


# ------------------------------------------------------------
# Native bridge state
# ------------------------------------------------------------

_bridge_dll = None
_engine_initialized = False


# ------------------------------------------------------------
# Native bridge discovery
# ------------------------------------------------------------

def _find_bridge_dll() -> Path:
    """
    Locate DesktopVisionEnginePythonBridge.dll.

    An environment variable can override the default location:

        DESKTOPVISIONENGINE_BRIDGE_DLL

    Otherwise the expected development layout is used:

        Projects/
        ├── DesktopVisionEngine/
        │   └── x64/Debug/
        │       └── DesktopVisionEnginePythonBridge.dll
        │
        └── LingoLens-Lab/
            └── prototypes/...
    """

    environment_path = os.environ.get(
        "DESKTOPVISIONENGINE_BRIDGE_DLL"
    )

    if environment_path:
        path = Path(environment_path)

        if path.exists():
            return path

        raise FileNotFoundError(
            "DESKTOPVISIONENGINE_BRIDGE_DLL points to a "
            f"missing file:\n{path}"
        )

    # capture_engine.py is located at:
    #
    # LingoLens-Lab/
    #   prototypes/
    #     09_application_framework/
    #       core/
    #         capture_engine.py
    #
    # parents[4] = Projects/

    projects_dir = (
        Path(__file__).resolve().parents[4]
    )

    bridge_path = (
        projects_dir
        / "DesktopVisionEngine"
        / "x64"
        / "Debug"
        / "DesktopVisionEnginePythonBridge.dll"
    )

    if not bridge_path.exists():
        raise FileNotFoundError(
            "DesktopVisionEnginePythonBridge.dll "
            "could not be found.\n\n"
            f"Expected location:\n{bridge_path}\n\n"
            "Set DESKTOPVISIONENGINE_BRIDGE_DLL if "
            "the native engine is located elsewhere."
        )

    return bridge_path


# ------------------------------------------------------------
# Native bridge initialization
# ------------------------------------------------------------

def _ensure_native_engine() -> None:
    """
    Load and initialize the native DesktopVisionEngine.

    Initialization happens lazily on the first capture.
    """

    global _bridge_dll
    global _engine_initialized

    if _engine_initialized:
        return

    bridge_path = _find_bridge_dll()

    _bridge_dll = ctypes.WinDLL(
        str(bridge_path)
    )

    # --------------------------------------------------------
    # Define native function signatures.
    # --------------------------------------------------------

    _bridge_dll.DVEPB_Initialize.argtypes = []

    _bridge_dll.DVEPB_Initialize.restype = (
        ctypes.c_bool
    )

    _bridge_dll.DVEPB_Shutdown.argtypes = []

    _bridge_dll.DVEPB_Shutdown.restype = None

    _bridge_dll.DVEPB_CaptureDesktop.argtypes = [
        ctypes.POINTER(DVEPB_Image)
    ]

    _bridge_dll.DVEPB_CaptureDesktop.restype = (
        ctypes.c_bool
    )

    _bridge_dll.DVEPB_FreeImage.argtypes = [
        ctypes.POINTER(DVEPB_Image)
    ]

    _bridge_dll.DVEPB_FreeImage.restype = None

    # --------------------------------------------------------
    # Initialize native engine.
    # --------------------------------------------------------

    if not _bridge_dll.DVEPB_Initialize():
        _bridge_dll = None

        raise RuntimeError(
            "DesktopVisionEngine initialization failed."
        )

    _engine_initialized = True


# ------------------------------------------------------------
# Native bridge shutdown
# ------------------------------------------------------------

def shutdown_capture_engine() -> None:
    """
    Shut down the native DesktopVisionEngine.

    Safe to call multiple times.
    """

    global _bridge_dll
    global _engine_initialized

    if (
        _bridge_dll is not None
        and _engine_initialized
    ):
        _bridge_dll.DVEPB_Shutdown()

    _bridge_dll = None
    _engine_initialized = False


atexit.register(
    shutdown_capture_engine
)


# ------------------------------------------------------------
# Captured region
# ------------------------------------------------------------

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


# ------------------------------------------------------------
# Full desktop capture
# ------------------------------------------------------------

def capture_fullscreen() -> Image.Image:
    """
    Capture the complete Windows virtual desktop
    using DesktopVisionEngine.

    Returns
    -------
    PIL.Image.Image
        Complete virtual desktop image in RGBA format.
    """

    _ensure_native_engine()

    native_image = DVEPB_Image()

    try:

        # ----------------------------------------------------
        # Capture native desktop image.
        # ----------------------------------------------------

        success = _bridge_dll.DVEPB_CaptureDesktop(
            ctypes.byref(native_image)
        )

        if not success:
            raise RuntimeError(
                "DesktopVisionEngine failed to "
                "capture the desktop."
            )

        if native_image.pixels is None:
            raise RuntimeError(
                "DesktopVisionEngine returned an "
                "empty pixel buffer."
            )

        if native_image.width == 0:
            raise RuntimeError(
                "DesktopVisionEngine returned "
                "zero width."
            )

        if native_image.height == 0:
            raise RuntimeError(
                "DesktopVisionEngine returned "
                "zero height."
            )

        if native_image.bytesPerPixel != 4:
            raise RuntimeError(
                "Unsupported native pixel format: "
                f"{native_image.bytesPerPixel} bytes/pixel."
            )

        expected_bytes = (
            native_image.width
            * native_image.height
            * native_image.bytesPerPixel
        )

        if native_image.pixelBytes != expected_bytes:
            raise RuntimeError(
                "Native pixel buffer size mismatch: "
                f"{native_image.pixelBytes} "
                f"(expected {expected_bytes})."
            )

        # ----------------------------------------------------
        # Copy native memory into Python-managed memory.
        #
        # The native buffer must be released before this
        # function returns.
        # ----------------------------------------------------

        pixel_buffer = ctypes.string_at(
            native_image.pixels,
            native_image.pixelBytes,
        )

        # ----------------------------------------------------
        # Native format is BGRA.
        # Convert it to a normal Pillow RGBA image.
        # ----------------------------------------------------

        image = Image.frombuffer(
            "RGBA",
            (
                native_image.width,
                native_image.height,
            ),
            pixel_buffer,
            "raw",
            "BGRA",
            0,
            1,
        ).copy()

        return image

    finally:

        # ----------------------------------------------------
        # Native C++ owns this memory.
        # Always release it through the bridge.
        # ----------------------------------------------------

        _bridge_dll.DVEPB_FreeImage(
            ctypes.byref(native_image)
        )


# ------------------------------------------------------------
# Region capture
# ------------------------------------------------------------

def capture_region(
    left: int,
    top: int,
    right: int,
    bottom: int,
) -> CapturedRegion:
    """
    Capture a rectangular desktop region.

    The complete virtual desktop is captured by the native
    engine first. Python then crops the requested region.

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

    if right <= left:
        raise ValueError(
            "Region right coordinate must be "
            "greater than left coordinate."
        )

    if bottom <= top:
        raise ValueError(
            "Region bottom coordinate must be "
            "greater than top coordinate."
        )

    desktop = capture_fullscreen()

    desktop_width = desktop.width
    desktop_height = desktop.height

    # --------------------------------------------------------
    # Validate against the current virtual desktop image.
    # --------------------------------------------------------

    if left < 0:
        raise ValueError(
            f"Region left coordinate is outside "
            f"the captured desktop: {left}"
        )

    if top < 0:
        raise ValueError(
            f"Region top coordinate is outside "
            f"the captured desktop: {top}"
        )

    if right > desktop_width:
        raise ValueError(
            f"Region right coordinate {right} "
            f"exceeds desktop width {desktop_width}."
        )

    if bottom > desktop_height:
        raise ValueError(
            f"Region bottom coordinate {bottom} "
            f"exceeds desktop height {desktop_height}."
        )

    # --------------------------------------------------------
    # Crop from the native full-desktop image.
    # --------------------------------------------------------

    image = desktop.crop(
        (
            left,
            top,
            right,
            bottom,
        )
    )

    return CapturedRegion(
        image=image,
        left=left,
        top=top,
        right=right,
        bottom=bottom,
    )


# ------------------------------------------------------------
# TranslationMap bounds capture
# ------------------------------------------------------------

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

    if width <= 0:
        raise ValueError(
            "Region width must be greater than zero."
        )

    if height <= 0:
        raise ValueError(
            "Region height must be greater than zero."
        )

    return capture_region(
        left,
        top,
        left + width,
        top + height,
    )