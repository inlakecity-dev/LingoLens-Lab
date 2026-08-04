"""
core/controller_tools.py

Controller Tools service.

Coordinates application tool actions.

Responsibilities
----------------
- Show History.
- Show Log Viewer.

This service does NOT:
- Perform OCR.
- Perform Translation.
- Manage Live Mode.
- Manage the Floating Lens.
"""

from __future__ import annotations

from tkinter import messagebox

from logger import logger


class ControllerTools:
    """
    Coordinates application tool actions.
    """

    MODULE = "ControllerTools"

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
            "Controller tools service initialized."
        )

    # --------------------------------------------------
    # History
    # --------------------------------------------------

    def show_history(self):
        """
        Open the History window.
        """

        logger.info(
            "TOOLS",
            "History selected"
        )

        messagebox.showinfo(
            "History",
            "History window will be implemented in the next phase."
        )

    # --------------------------------------------------
    # Log Viewer
    # --------------------------------------------------

    def show_log_viewer(self):
        """
        Open the Log Viewer.
        """

        logger.info(
            "TOOLS",
            "Log Viewer selected"
        )

        messagebox.showinfo(
            "Log Viewer",
            "Log Viewer will be implemented in the next phase."
        )