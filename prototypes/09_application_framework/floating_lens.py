"""
floating_lens.py

Floating Lens window.

Provides the floating overlay window that will
later host live OCR, translation and capture tools.
"""

import tkinter as tk

from theme import (
    register_widget,
    unregister_widget,
)


class FloatingLensWindow:
    """
    Floating Lens overlay window.
    """

    def __init__(
        self,
        parent,
        app_settings,
        lens_controller,
    ):

        self.parent = parent
        self.app_settings = app_settings

        self.window = None

        self._drag_x = 0
        self._drag_y = 0

        self.create_window()
        self.create_widgets()

        register_widget(self)

        self.apply_theme()
        self.lens_controller = lens_controller

    # --------------------------------------------------
    # Window
    # --------------------------------------------------

    def create_window(self):

        self.window = tk.Toplevel(
            self.parent
        )

        self.window.withdraw()

        self.window.overrideredirect(True)

        self.window.attributes(
            "-topmost",
            True
        )

        self.window.geometry(
            "380x260+250+200"
        )

        self.window.protocol(
            "WM_DELETE_WINDOW",
            self.close
        )

    # --------------------------------------------------
    # Widgets
    # --------------------------------------------------

    def create_widgets(self):

        #
        # Title Bar
        #

        self.title_bar = tk.Frame(
            self.window,
            height=34,
            cursor="fleur"
        )

        self.title_bar.pack(
            fill="x"
        )

        self.title_label = tk.Label(
            self.title_bar,
            text="🔍 LingoLens",
            font=("Segoe UI", 10, "bold")
        )

        self.title_label.pack(
            side="left",
            padx=10,
            pady=6
        )

        self.close_button = tk.Button(
            self.title_bar,
            text="✕",
            bd=0,
            relief="flat",
            padx=8,
            command=self.close
        )

        self.close_button.pack(
            side="right",
            padx=6,
            pady=4
        )

        #
        # Main Content
        #

        self.content = tk.Frame(
            self.window
        )

        self.content.pack(
            fill="both",
            expand=True
        )

        self.translation_label = tk.Label(
            self.content,
            text="Waiting for translation...",
            font=("Segoe UI", 12),
            justify="center",
            wraplength=320
        )

        self.translation_label.pack(
            expand=True,
            padx=20,
            pady=20
        )

        #
        # Status Bar
        #

        self.status_bar = tk.Frame(
            self.window,
            height=24
        )

        self.status_bar.pack(
            fill="x",
            side="bottom"
        )

        self.status_label = tk.Label(
            self.status_bar,
            text="Ready",
            anchor="w",
            padx=8,
            font=("Segoe UI", 9)
        )

        self.status_label.pack(
            fill="x"
        )

        #
        # Drag Events
        #

        self.title_bar.bind(
            "<ButtonPress-1>",
            self.start_move
        )

        self.title_bar.bind(
            "<B1-Motion>",
            self.on_move
        )

        self.title_label.bind(
            "<ButtonPress-1>",
            self.start_move
        )

        self.title_label.bind(
            "<B1-Motion>",
            self.on_move
        )
        
    # --------------------------------------------------
    # Window Controls
    # --------------------------------------------------

    def show(self):

        self.window.deiconify()

    def hide(self):

        self.window.withdraw()

    def toggle(self):

        if self.window.state() == "withdrawn":

            self.show()

        else:

            self.hide()

    def close(self):

        self.hide()

    # --------------------------------------------------
    # Translation Display
    # --------------------------------------------------

    def set_translation(
        self,
        text,
    ):

        if not text:

            text = "No text detected."

        self.translation_label.config(
            text=text
        )

    def clear_translation(self):

        self.translation_label.config(
            text="Waiting for translation..."
        )

    def set_status(
        self,
        status,
    ):

        self.status_label.config(
            text=status
        )

    # --------------------------------------------------
    # Dragging
    # --------------------------------------------------

    def start_move(
        self,
        event,
    ):

        self._drag_x = event.x
        self._drag_y = event.y

    def on_move(
        self,
        event,
    ):

        x = (
            self.window.winfo_x()
            + event.x
            - self._drag_x
        )

        y = (
            self.window.winfo_y()
            + event.y
            - self._drag_y
        )

        self.window.geometry(
            f"+{x}+{y}"
        )

    # --------------------------------------------------
    # Theme
    # --------------------------------------------------

    def apply_theme(self):

        #
        # Temporary colors.
        # We'll replace these with the
        # application's theme manager later.
        #

        self.window.configure(
            bg="#2B2B2B"
        )

        self.title_bar.configure(
            bg="#202020"
        )

        self.title_label.configure(
            bg="#202020",
            fg="white"
        )

        self.close_button.configure(
            bg="#202020",
            fg="white",
            activebackground="#404040",
            activeforeground="white"
        )

        self.content.configure(
            bg="#2B2B2B"
        )

        self.translation_label.configure(
            bg="#2B2B2B",
            fg="white"
        )

        self.status_bar.configure(
            bg="#202020"
        )

        self.status_label.configure(
            bg="#202020",
            fg="#DDDDDD"
        )

    # --------------------------------------------------
    # Cleanup
    # --------------------------------------------------

    def destroy(self):

        unregister_widget(self)

        if self.window is not None:

            self.window.destroy()