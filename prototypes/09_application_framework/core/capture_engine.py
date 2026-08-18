"""
core/capture_engine.py

Capture Engine

Responsible for capturing images from the Windows desktop.

The native DesktopVisionEngine provides the complete virtual desktop
and physical monitor layout. Python performs region cropping on the
captured image.

This module contains no OCR, Translation or UI logic.
"""

import atexit
import ctypes
import os
import threading

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
# Native bridge output structure
# ------------------------------------------------------------

class DVEPB_Output(ctypes.Structure):
    """
    Native physical display metadata exposed by
    DesktopVisionEnginePythonBridge.dll.

    Coordinates use Windows virtual-desktop coordinates.
    """

    _fields_ = [
        ("left", ctypes.c_int32),
        ("top", ctypes.c_int32),
        ("right", ctypes.c_int32),
        ("bottom", ctypes.c_int32),
        ("attachedToDesktop", ctypes.c_uint8),
        ("primary", ctypes.c_uint8),
    ]


# ------------------------------------------------------------
# Native bridge dirty region structure
# ------------------------------------------------------------

class DVEPB_DirtyRegion(ctypes.Structure):
    """
    Native desktop dirty-region metadata.

    Coordinates use Windows virtual-desktop coordinates.
    """

    _fields_ = [
        ("left", ctypes.c_int32),
        ("top", ctypes.c_int32),
        ("right", ctypes.c_int32),
        ("bottom", ctypes.c_int32),
    ]


# ------------------------------------------------------------
# Native bridge move region structure
# ------------------------------------------------------------

class DVEPB_MoveRegion(ctypes.Structure):
    """
    Native desktop move-region metadata.

    Destination and source coordinates use Windows
    virtual-desktop coordinates.
    """

    _fields_ = [
        ("destinationLeft", ctypes.c_int32),
        ("destinationTop", ctypes.c_int32),
        ("destinationRight", ctypes.c_int32),
        ("destinationBottom", ctypes.c_int32),
        ("sourceX", ctypes.c_int32),
        ("sourceY", ctypes.c_int32),
    ]


# ------------------------------------------------------------
# Python desktop change representation
# ------------------------------------------------------------

@dataclass(slots=True)
class DesktopChangeRegion:
    """
    Represents one changed desktop region.

    Coordinates use Windows virtual-desktop coordinates.
    """

    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        """Return region width."""

        return self.right - self.left

    @property
    def height(self) -> int:
        """Return region height."""

        return self.bottom - self.top

    @property
    def bounds(self) -> tuple[int, int, int, int]:
        """
        Return region bounds as:

            (left, top, width, height)
        """

        return (
            self.left,
            self.top,
            self.width,
            self.height,
        )


@dataclass(slots=True)
class DesktopMoveRegion:
    """
    Represents one desktop move operation.

    All coordinates use Windows virtual-desktop coordinates.
    """

    destination_left: int
    destination_top: int
    destination_right: int
    destination_bottom: int
    source_x: int
    source_y: int

    @property
    def destination_bounds(
        self,
    ) -> tuple[int, int, int, int]:
        """
        Return destination bounds as:

            (left, top, width, height)
        """

        return (
            self.destination_left,
            self.destination_top,
            self.destination_right
            - self.destination_left,
            self.destination_bottom
            - self.destination_top,
        )


# ------------------------------------------------------------
# Python monitor representation
# ------------------------------------------------------------

@dataclass(slots=True)
class DesktopMonitor:
    """
    Represents one physical monitor in the Windows
    virtual desktop.
    """

    left: int
    top: int
    right: int
    bottom: int
    attached_to_desktop: bool
    primary: bool

    @property
    def width(self) -> int:
        """Monitor width."""

        return self.right - self.left

    @property
    def height(self) -> int:
        """Monitor height."""

        return self.bottom - self.top

    @property
    def bounds(self) -> tuple[int, int, int, int]:
        """
        Return monitor bounds as:

            (left, top, width, height)
        """

        return (
            self.left,
            self.top,
            self.width,
            self.height,
        )


# ------------------------------------------------------------
# Native bridge state
# ------------------------------------------------------------

_bridge_dll = None
_engine_initialized = False

_desktop_monitors: list[DesktopMonitor] = []
_desktop_bounds: tuple[int, int, int, int] = (
    0,
    0,
    0,
    0,
)


# ------------------------------------------------------------
# Native engine synchronization
# ------------------------------------------------------------
#
# DesktopVisionEngine owns stateful DXGI Desktop Duplication
# sessions. The same native engine is used by multiple Python
# consumers:
#
#     DesktopObserver
#         -> capture_desktop_changes()
#
#     ControllerPipeline
#         -> capture_fullscreen()
#
# These operations must never enter the native engine
# concurrently.
#
# RLock is used because some protected functions call other
# protected functions internally.
# ------------------------------------------------------------

_native_lock = threading.RLock()


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
# Desktop bounds calculation
# ------------------------------------------------------------

def _calculate_desktop_bounds(
    monitors: list[DesktopMonitor],
) -> tuple[int, int, int, int]:
    """
    Calculate the complete virtual desktop bounds
    from the detected physical monitors.

    Returns
    -------
    tuple
        (left, top, width, height)
    """

    if not monitors:
        raise RuntimeError(
            "No desktop monitors detected."
        )

    left = min(
        monitor.left
        for monitor in monitors
    )

    top = min(
        monitor.top
        for monitor in monitors
    )

    right = max(
        monitor.right
        for monitor in monitors
    )

    bottom = max(
        monitor.bottom
        for monitor in monitors
    )

    return (
        left,
        top,
        right - left,
        bottom - top,
    )


# ------------------------------------------------------------
# Load output metadata
# ------------------------------------------------------------

def _load_desktop_metadata() -> None:
    """
    Load physical monitor metadata from the native engine
    and calculate the virtual desktop bounds.

    This is performed once when the native engine is
    initialized.
    """

    global _desktop_monitors
    global _desktop_bounds

    output_count = (
        _bridge_dll.DVEPB_GetOutputCount()
    )

    if output_count == 0:
        raise RuntimeError(
            "DesktopVisionEngine detected no displays."
        )

    monitors = []

    for index in range(output_count):

        native_output = DVEPB_Output()

        success = (
            _bridge_dll.DVEPB_GetOutput(
                index,
                ctypes.byref(native_output),
            )
        )

        if not success:
            raise RuntimeError(
                "DesktopVisionEngine failed to "
                f"retrieve output #{index}."
            )

        monitors.append(
            DesktopMonitor(
                left=native_output.left,
                top=native_output.top,
                right=native_output.right,
                bottom=native_output.bottom,
                attached_to_desktop=bool(
                    native_output.attachedToDesktop
                ),
                primary=bool(
                    native_output.primary
                ),
            )
        )

    _desktop_monitors = monitors

    _desktop_bounds = (
        _calculate_desktop_bounds(
            monitors
        )
    )


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

    with _native_lock:

        if _engine_initialized:
            return

        bridge_path = _find_bridge_dll()

        _bridge_dll = ctypes.WinDLL(
            str(bridge_path)
        )

        # ----------------------------------------------------
        # Image functions
        # ----------------------------------------------------

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

        # ----------------------------------------------------
        # Unified Desktop State Acquisition
        # ----------------------------------------------------

        _bridge_dll.DVEPB_CaptureDesktopState.argtypes = [
            ctypes.POINTER(DVEPB_Image)
        ]

        _bridge_dll.DVEPB_CaptureDesktopState.restype = (
            ctypes.c_bool
        )

        _bridge_dll.DVEPB_FreeImage.argtypes = [
            ctypes.POINTER(DVEPB_Image)
        ]

        _bridge_dll.DVEPB_FreeImage.restype = None

        # ----------------------------------------------------
        # Desktop Change Observation
        # ----------------------------------------------------

        _bridge_dll.DVEPB_CaptureDesktopChanges.argtypes = []

        _bridge_dll.DVEPB_CaptureDesktopChanges.restype = (
            ctypes.c_bool
        )

        # ----------------------------------------------------
        # Output metadata functions
        # ----------------------------------------------------

        _bridge_dll.DVEPB_GetOutputCount.argtypes = []

        _bridge_dll.DVEPB_GetOutputCount.restype = (
            ctypes.c_uint32
        )

        _bridge_dll.DVEPB_GetOutput.argtypes = [
            ctypes.c_uint32,
            ctypes.POINTER(DVEPB_Output),
        ]

        _bridge_dll.DVEPB_GetOutput.restype = (
            ctypes.c_bool
        )

        # ----------------------------------------------------
        # Desktop dirty-region functions
        # ----------------------------------------------------

        _bridge_dll.DVEPB_GetDirtyRegionCount.argtypes = []

        _bridge_dll.DVEPB_GetDirtyRegionCount.restype = (
            ctypes.c_uint32
        )

        _bridge_dll.DVEPB_GetDirtyRegion.argtypes = [
            ctypes.c_uint32,
            ctypes.POINTER(DVEPB_DirtyRegion),
        ]

        _bridge_dll.DVEPB_GetDirtyRegion.restype = (
            ctypes.c_bool
        )

        # ----------------------------------------------------
        # Desktop move-region functions
        # ----------------------------------------------------

        _bridge_dll.DVEPB_GetMoveRegionCount.argtypes = []

        _bridge_dll.DVEPB_GetMoveRegionCount.restype = (
            ctypes.c_uint32
        )

        _bridge_dll.DVEPB_GetMoveRegion.argtypes = [
            ctypes.c_uint32,
            ctypes.POINTER(DVEPB_MoveRegion),
        ]

        _bridge_dll.DVEPB_GetMoveRegion.restype = (
            ctypes.c_bool
        )

        # ----------------------------------------------------
        # Initialize native engine.
        # ----------------------------------------------------

        if not _bridge_dll.DVEPB_Initialize():
            _bridge_dll = None

            raise RuntimeError(
                "DesktopVisionEngine initialization failed."
            )

        try:

            _load_desktop_metadata()

        except Exception:

            _bridge_dll.DVEPB_Shutdown()

            _bridge_dll = None

            raise

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
    global _desktop_monitors
    global _desktop_bounds

    with _native_lock:

        if (
            _bridge_dll is not None
            and _engine_initialized
        ):
            _bridge_dll.DVEPB_Shutdown()

        _bridge_dll = None
        _engine_initialized = False

        _desktop_monitors = []

        _desktop_bounds = (
            0,
            0,
            0,
            0,
        )


atexit.register(
    shutdown_capture_engine
)


# ------------------------------------------------------------
# Desktop metadata
# ------------------------------------------------------------

def get_monitors() -> list[DesktopMonitor]:
    """
    Return the physical monitors detected by the
    native DesktopVisionEngine.

    Returns
    -------
    list[DesktopMonitor]
        Monitor layout using Windows virtual-desktop
        coordinates.
    """

    _ensure_native_engine()

    with _native_lock:
        return _desktop_monitors.copy()


def get_desktop_bounds() -> tuple[int, int, int, int]:
    """
    Return the complete Windows virtual desktop bounds.

    The returned format is:

        (left, top, width, height)

    The coordinates are derived from the physical monitor
    layout rather than assuming that the desktop starts at
    coordinate 0,0.
    """

    _ensure_native_engine()

    with _native_lock:
        return _desktop_bounds


# ------------------------------------------------------------
# Desktop Change Metadata
# ------------------------------------------------------------

def _get_last_desktop_changes_locked() -> dict:
    """
    Read desktop change metadata.

    The caller must already hold _native_lock.
    """

    dirty_regions = []

    dirty_count = (
        _bridge_dll.DVEPB_GetDirtyRegionCount()
    )

    for index in range(dirty_count):

        native_region = (
            DVEPB_DirtyRegion()
        )

        success = (
            _bridge_dll.DVEPB_GetDirtyRegion(
                index,
                ctypes.byref(
                    native_region
                ),
            )
        )

        if not success:
            raise RuntimeError(
                "DesktopVisionEngine failed to "
                f"retrieve dirty region #{index}."
            )

        dirty_regions.append(
            DesktopChangeRegion(
                left=native_region.left,
                top=native_region.top,
                right=native_region.right,
                bottom=native_region.bottom,
            )
        )

    move_regions = []

    move_count = (
        _bridge_dll.DVEPB_GetMoveRegionCount()
    )

    for index in range(move_count):

        native_region = (
            DVEPB_MoveRegion()
        )

        success = (
            _bridge_dll.DVEPB_GetMoveRegion(
                index,
                ctypes.byref(
                    native_region
                ),
            )
        )

        if not success:
            raise RuntimeError(
                "DesktopVisionEngine failed to "
                f"retrieve move region #{index}."
            )

        move_regions.append(
            DesktopMoveRegion(
                destination_left=(
                    native_region.destinationLeft
                ),
                destination_top=(
                    native_region.destinationTop
                ),
                destination_right=(
                    native_region.destinationRight
                ),
                destination_bottom=(
                    native_region.destinationBottom
                ),
                source_x=native_region.sourceX,
                source_y=native_region.sourceY,
            )
        )

    return {
        "dirty_regions": dirty_regions,
        "move_regions": move_regions,
    }


def get_last_desktop_changes() -> dict:
    """
    Return desktop change metadata from the most recent
    native desktop capture.

    The native DesktopVisionEngine updates its dirty and
    move regions whenever a desktop change observation or
    desktop image capture is performed.

    Returns
    -------
    dict
        {
            "dirty_regions": list[DesktopChangeRegion],
            "move_regions": list[DesktopMoveRegion],
        }
    """

    _ensure_native_engine()

    with _native_lock:
        return _get_last_desktop_changes_locked()


# ------------------------------------------------------------
# Desktop Observation Capture
# ------------------------------------------------------------

def capture_desktop_changes() -> dict:
    """
    Perform one native desktop observation cycle and return
    the desktop change metadata produced by that cycle.

    The captured desktop image is NOT requested.

    This function is intended for DesktopObserver and
    observation-only scenarios.

    It does not replace capture_region(),
    capture_fullscreen(), or capture_desktop_state().
    """

    _ensure_native_engine()

    with _native_lock:

        success = (
            _bridge_dll.DVEPB_CaptureDesktopChanges()
        )

        if not success:
            raise RuntimeError(
                "DesktopVisionEngine failed to "
                "capture desktop changes for observation."
            )

        return _get_last_desktop_changes_locked()


# ------------------------------------------------------------
# Unified Desktop State Capture
# ------------------------------------------------------------

def capture_desktop_state() -> dict:
    """
    Perform one unified native desktop acquisition.

    The native DesktopVisionEngine acquires the desktop once
    and produces both:

        1. Complete virtual desktop image.
        2. Desktop-change metadata belonging to that
           same native acquisition.

    Returns
    -------
    dict
        {
            "image": PIL.Image.Image,
            "dirty_regions": list[DesktopChangeRegion],
            "move_regions": list[DesktopMoveRegion],
        }

    This is the preferred acquisition path for Live Mode.

    Important
    ---------
    This function performs exactly one native desktop
    acquisition. It does NOT call capture_desktop_changes()
    after capturing the image.
    """

    _ensure_native_engine()

    native_image = DVEPB_Image()

    with _native_lock:

        try:

            # ------------------------------------------------
            # Perform one unified native acquisition.
            # ------------------------------------------------

            success = (
                _bridge_dll.DVEPB_CaptureDesktopState(
                    ctypes.byref(native_image)
                )
            )

            if not success:
                raise RuntimeError(
                    "DesktopVisionEngine failed to "
                    "capture unified desktop state."
                )

            if not native_image.pixels:
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

            # ------------------------------------------------
            # Verify native image dimensions against the
            # virtual desktop metadata.
            # ------------------------------------------------

            (
                desktop_left,
                desktop_top,
                desktop_width,
                desktop_height,
            ) = _desktop_bounds

            if native_image.width != desktop_width:
                raise RuntimeError(
                    "Native desktop width does not match "
                    "desktop metadata: "
                    f"{native_image.width} "
                    f"(expected {desktop_width})."
                )

            if native_image.height != desktop_height:
                raise RuntimeError(
                    "Native desktop height does not match "
                    "desktop metadata: "
                    f"{native_image.height} "
                    f"(expected {desktop_height})."
                )

            # ------------------------------------------------
            # Copy native memory into Python-managed memory.
            # ------------------------------------------------

            pixel_buffer = ctypes.string_at(
                native_image.pixels,
                native_image.pixelBytes,
            )

            # ------------------------------------------------
            # Native format is BGRA.
            # Convert it to RGBA.
            # ------------------------------------------------

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

            # ------------------------------------------------
            # The native engine stores the metadata from the
            # SAME acquisition in its last-change state.
            #
            # Read it before releasing the Python lock, but
            # still within the same native-engine critical
            # section.
            # ------------------------------------------------

            changes = _get_last_desktop_changes_locked()

            return {
                "image": image,
                "dirty_regions": changes[
                    "dirty_regions"
                ],
                "move_regions": changes[
                    "move_regions"
                ],
            }

        finally:

            # ------------------------------------------------
            # Native C++ owns this memory.
            # Always release it through the bridge.
            # ------------------------------------------------

            _bridge_dll.DVEPB_FreeImage(
                ctypes.byref(native_image)
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

    with _native_lock:

        try:

            # ------------------------------------------------
            # Capture native desktop image.
            # ------------------------------------------------

            success = _bridge_dll.DVEPB_CaptureDesktop(
                ctypes.byref(native_image)
            )

            if not success:
                raise RuntimeError(
                    "DesktopVisionEngine failed to "
                    "capture the desktop."
                )

            if not native_image.pixels:
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

            # ------------------------------------------------
            # Verify native image dimensions against the
            # virtual desktop metadata.
            # ------------------------------------------------

            (
                desktop_left,
                desktop_top,
                desktop_width,
                desktop_height,
            ) = _desktop_bounds

            if native_image.width != desktop_width:
                raise RuntimeError(
                    "Native desktop width does not match "
                    "desktop metadata: "
                    f"{native_image.width} "
                    f"(expected {desktop_width})."
                )

            if native_image.height != desktop_height:
                raise RuntimeError(
                    "Native desktop height does not match "
                    "desktop metadata: "
                    f"{native_image.height} "
                    f"(expected {desktop_height})."
                )

            # ------------------------------------------------
            # Copy native memory into Python-managed memory.
            # ------------------------------------------------

            pixel_buffer = ctypes.string_at(
                native_image.pixels,
                native_image.pixelBytes,
            )

            # ------------------------------------------------
            # Native format is BGRA.
            # Convert it to RGBA.
            # ------------------------------------------------

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

            # ------------------------------------------------
            # Native C++ owns this memory.
            # Always release it through the bridge.
            # ------------------------------------------------

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

    (
        desktop_left,
        desktop_top,
        desktop_width,
        desktop_height,
    ) = get_desktop_bounds()

    desktop_right = (
        desktop_left
        + desktop_width
    )

    desktop_bottom = (
        desktop_top
        + desktop_height
    )

    # --------------------------------------------------------
    # Validate against the actual Windows virtual desktop.
    # --------------------------------------------------------

    if left < desktop_left:
        raise ValueError(
            f"Region left coordinate {left} "
            f"is outside the virtual desktop."
        )

    if top < desktop_top:
        raise ValueError(
            f"Region top coordinate {top} "
            f"is outside the virtual desktop."
        )

    if right > desktop_right:
        raise ValueError(
            f"Region right coordinate {right} "
            f"exceeds virtual desktop right boundary "
            f"{desktop_right}."
        )

    if bottom > desktop_bottom:
        raise ValueError(
            f"Region bottom coordinate {bottom} "
            f"exceeds virtual desktop bottom boundary "
            f"{desktop_bottom}."
        )

    # --------------------------------------------------------
    # Convert Windows desktop coordinates into image
    # coordinates.
    # --------------------------------------------------------

    crop_left = (
        left - desktop_left
    )

    crop_top = (
        top - desktop_top
    )

    crop_right = (
        right - desktop_left
    )

    crop_bottom = (
        bottom - desktop_top
    )

    image = desktop.crop(
        (
            crop_left,
            crop_top,
            crop_right,
            crop_bottom,
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