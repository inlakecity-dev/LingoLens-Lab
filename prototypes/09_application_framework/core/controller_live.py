"""
core/controller_live.py

Controller Live Mode

Coordinates the Live Translation workflow.

Responsibilities
----------------
- Start Live Mode.
- Stop Live Mode.
- Process desktop change notifications.
- Update the TranslationMap.

This class does NOT:
- Perform OCR
- Perform Translation
- Capture desktop regions directly
- Own the TranslationMap
- Own the DesktopObserver
"""

from __future__ import annotations

from logger import logger


class ControllerLive:
    """
    Coordinates the Live Translation workflow.
    """

    MODULE = "ControllerLive"

    def __init__(self, controller):
        """
        Parameters
        ----------
        controller
            Shared application controller.
        """

        self.controller = controller

        logger.info(
            self.MODULE,
            "Controller live service initialized."
        )

    # --------------------------------------------------
    # LIVE MODE
    # --------------------------------------------------

    def start_live_mode(self):
        """
        Start Live Translation.
        """

        logger.info(
            self.MODULE,
            "Starting Live Mode."
        )

        self.controller.desktop_observer.start()

    def stop_live_mode(self):
        """
        Stop Live Translation.
        """

        logger.info(
            self.MODULE,
            "Stopping Live Mode."
        )

        self.controller.desktop_observer.stop()

    # --------------------------------------------------
    # DESKTOP CHANGES
    # --------------------------------------------------

    def on_desktop_changed(
        self,
        dirty_regions,
    ):
        """
        Process desktop changes reported by the
        Desktop Observer.
        """

        logger.info(
            self.MODULE,
            f"Desktop changed ({len(dirty_regions)} dirty region(s))."
        )

        for bounds in dirty_regions:

            # ------------------------------------------
            # Remove outdated translations
            # ------------------------------------------

            self.controller.translation_map.remove_entries_in_region(
                bounds
            )

            # ------------------------------------------
            # Capture updated region
            # ------------------------------------------

            snapshot = (
                self.controller.image_pipeline.capture_snapshot(
                    *bounds
                )
            )

            result = snapshot["result"]

            if result["status"] != "success":
                continue

            # ------------------------------------------
            # Update Translation Map
            # ------------------------------------------

            self.controller.translation_map.add_entry(
                snapshot["captured_region"].bounds,
                result["original"],
                result["translation"],
            )