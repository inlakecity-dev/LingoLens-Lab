"""
base_panel.py

Reusable base class for all docked sidebar panels.

Responsibilities:
- Common panel container
- Consistent padding
- Content area
- Close callback

No business logic belongs here.
"""

from tkinter import ttk


class BasePanel(ttk.Frame):

    def __init__(self, parent):

        super().__init__(
            parent,
            padding=10
        )

        self.close_callback = None

        # --------------------------------------------------
        # Content
        # --------------------------------------------------

        self.content = ttk.Frame(self)

        self.content.pack(
            fill="both",
            expand=True
        )

    def close(self):
        """Request the panel to close."""

        if callable(self.close_callback):
            self.close_callback()