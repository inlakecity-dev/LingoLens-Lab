"""
desktop_observer.py

Observes the Windows desktop while Live Mode is active.

Current Version
---------------
This module defines the Desktop Observer interface.

The Windows Desktop Duplication API will be integrated in a future
revision. For now, this class manages the observer lifecycle and
notifies the Controller whenever desktop changes are detected.
"""

from logger import logger


class DesktopObserver:
    """
    Observes the Windows desktop.

    Responsibilities
    ----------------
    - Start desktop observation.
    - Stop desktop observation.
    - Notify the Controller when desktop changes occur.

    This class does NOT:
        - Capture images
        - Perform OCR
        - Translate text
        - Update the TranslationMap
    """

    def __init__(self, controller):
        """
        Initialize the Desktop Observer.

        Parameters
        ----------
        controller
            Application controller that receives desktop change events.
        """

        self.controller = controller
        self.running = False

        logger.info(
            "DESKTOP",
            "DesktopObserver initialized."
        )

    def start(self):
        """
        Start observing the desktop.
        """

        if self.running:
            return

        self.running = True

        logger.info(
            "DESKTOP",
            "DesktopObserver started."
        )

    def stop(self):
        """
        Stop observing the desktop.
        """

        if not self.running:
            return

        self.running = False

        logger.info(
            "DESKTOP",
            "DesktopObserver stopped."
        )

    def is_running(self):
        """
        Return whether the observer is currently active.
        """

        return self.running

    def notify_desktop_changed(self, dirty_regions):
        """
        Notify the controller that the desktop has changed.

        Parameters
        ----------
        dirty_regions : list[tuple]
            List of changed desktop regions.

            Format:
                (left, top, width, height)
        """

        if not self.running:
            return

        logger.info(
            "DESKTOP",
            f"Desktop changed ({len(dirty_regions)} dirty region(s))."
        )

        self.controller.on_desktop_changed(
            dirty_regions
        )