"""
LingoLens Application Controller

Coordinates every workflow inside LingoLens.

The Controller is the single system coordinator.

Responsibilities
----------------
• Coordinates the image processing pipeline.
• Owns Live Mode.
• Owns the TranslationMap.
• Supplies visible translations to the Floating Lens.
• Coordinates DesktopObserver.
"""

from tkinter import messagebox

from core.translation_map import TranslationMap
from core.desktop_observer import DesktopObserver
from core.controller_pipeline import ControllerImagePipeline

from core.controller_live import ControllerLive

from logger import logger



class Controller:
    """
    Central coordinator for the LingoLens application.

    The Controller is the application's System Brain.

    It coordinates the major application workflows
    and delegates implementation to specialized
    controller services.
    """

    def __init__(self, app_settings):

        self.app_settings = app_settings

        # ----------------------------------------------
        # Core Components
        # ----------------------------------------------

        # Single source of truth for the active desktop.
        self.translation_map = TranslationMap()

        # Live Desktop Observer.
        self.desktop_observer = DesktopObserver(self)
        
        # Shared image processing pipeline.
        self.image_pipeline = ControllerImagePipeline(self)
        
        self.live_controller = ControllerLive(self)

    

    # --------------------------------------------------
    # MANUAL TRANSLATION
    # --------------------------------------------------

    def translate_region(
        self,
        x1,
        y1,
        x2,
        y2,
    ):
        """
        Capture a user-selected region and process it
        through the shared image processing pipeline.

        Manual Translation and Live Translation both
        reuse the same processing pipeline.
        """

        snapshot = self.image_pipeline.capture_snapshot(
            x1,
            y1,
            x2 - x1,
            y2 - y1,
        )

        result = snapshot["result"]

        if result["status"] == "success":

            self.translation_map.add_entry(
                snapshot["captured_region"].bounds,
                result["original"],
                result["translation"],
            )  
            
        return result
     

    # --------------------------------------------------
    # LIVE MODE
    # --------------------------------------------------

    def start_live_mode(self):
        """
        Start Live Translation.
        """
        self.live_controller.start_live_mode()

    def stop_live_mode(self):
        """
        Stop Live Translation.
        """
        self.live_controller.stop_live_mode()

    def on_desktop_changed(
        self,
        dirty_regions,
    ):
        """
        Called by the Desktop Observer whenever the
        Windows desktop changes.
        """
        self.live_controller.on_desktop_changed(
            dirty_regions
        )

      
    # --------------------------------------------------
    # FLOATING LENS
    # --------------------------------------------------

    def on_lens_moved(
        self,
        bounds,
    ):
        """
        Called whenever the Floating Lens moves.

        The Floating Lens only reports its
        desktop position.

        The Controller determines which
        translations are visible.
        """

        return self.get_visible_translations(bounds)

    def get_visible_translations(
        self,
        bounds,
    ):
        """
        Return every translation visible inside
        the supplied desktop region.

        This is the ONLY supported way for the
        Floating Lens to obtain translation data.

        The TranslationMap is never exposed to
        the UI.
        """

        return self.translation_map.get_entries_in_region(
            bounds
        )

    # ----------------------------------------------
    # TOOLS
    # ----------------------------------------------

    def show_history(self):

        logger.info(
            "TOOLS",
            "History selected"
        )

        messagebox.showinfo(
            "History",
            "History window will be implemented in the next phase."
        )

    def show_log_viewer(self):

        logger.info(
            "TOOLS",
            "Log Viewer selected"
        )

        messagebox.showinfo(
            "Log Viewer",
            "Log Viewer will be implemented in the next phase."
        )