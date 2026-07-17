"""
core.display

Display-related helper functions for LingoLens.

Currently provides:
- Windows DPI Awareness

Future additions may include:
- Screen resolution
- Display scaling
- Multi-monitor detection
- Primary monitor information
"""

import ctypes


def enable_dpi_awareness():
    """
    Enable Windows DPI Awareness.

    This ensures that screen coordinates returned by the UI
    match the physical pixels used by screen capture APIs.

    Safe to call multiple times.

    On non-Windows platforms this function does nothing.
    """

    try:
        # Windows 8.1+
        ctypes.windll.shcore.SetProcessDpiAwareness(2)

    except Exception:
        try:
            # Windows Vista / 7
            ctypes.windll.user32.SetProcessDPIAware()

        except Exception:
            # Non-Windows or unsupported system
            pass