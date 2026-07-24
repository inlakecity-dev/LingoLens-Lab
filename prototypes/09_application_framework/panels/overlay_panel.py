"""
overlay_panel.py

Floating overlay panel for LingoLens.

Responsibilities:
- Display one panel at a time
- Overlay the workspace
- Show / Hide / Toggle panels

No application logic belongs here.
"""

from tkinter import ttk


class OverlayPanel(ttk.Frame):

    def __init__(self, parent):

        super().__init__(
            parent,
            relief="solid",
            borderwidth=1
        )

        # Allow the overlay to size itself to its content.
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

        self._panels = {}
        self._current = None

        self.place_forget()

    # --------------------------------------------------
    # Registration
    # --------------------------------------------------

    def register(self, name, panel):

        self._panels[name] = panel
        panel.close_callback = self.hide

    # --------------------------------------------------
    # Show Panel
    # --------------------------------------------------

    def show(self, name):

        panel = self._panels.get(name)

        if panel is None:
            return

        if self._current is not None:
            self._current.grid_remove()

        self._current = panel

        panel.grid(
            row=0,
            column=0,
            sticky="nsew"
        )

        # Let Tkinter calculate the panel's natural size.
        self.update_idletasks()
        panel.update_idletasks()

        width = panel.winfo_reqwidth()
        height = panel.winfo_reqheight()

        self.place(
            relx=1.0,
            rely=0.0,
            anchor="ne",
            width=width,
            height=height
        )

        self.lift()

    # --------------------------------------------------
    # Hide Panel
    # --------------------------------------------------

    def hide(self):

        if self._current is not None:
            self._current.grid_remove()
            self._current = None

        self.place_forget()

    # --------------------------------------------------
    # Toggle Panel
    # --------------------------------------------------

    def toggle(self, name):

        if self._current is self._panels.get(name):
            self.hide()
        else:
            self.show(name)

    # --------------------------------------------------
    # Helpers
    # --------------------------------------------------

    def is_visible(self):

        return self._current is not None

    def contains(self, x_root, y_root):

        if not self.is_visible():
            return False

        left = self.winfo_rootx()
        top = self.winfo_rooty()
        right = left + self.winfo_width()
        bottom = top + self.winfo_height()

        return left <= x_root <= right and top <= y_root <= bottom