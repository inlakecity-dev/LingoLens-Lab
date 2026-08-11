"""
floating_lens.py

Floating Lens window.

The Floating Lens is a viewport over the TranslationMap.

It does NOT:
- Capture the desktop.
- Perform OCR.
- Perform Translation.
- Create TranslationMap entries.

It only:
- Determines its current desktop position and dimensions.
- Queries the TranslationMap for visible translations.
- Renders the appropriate translation.
"""

import tkinter as tk

from theme import (
    register_widget,
    unregister_widget,
)


class FloatingLensWindow:
    """
    Floating Lens overlay window.

    The lens acts only as a viewport over the
    TranslationMap.
    """

    def __init__(
        self,
        parent,
        app_settings,
        lens_controller,
    ):

        self.parent = parent
        self.app_settings = app_settings
        self.lens_controller = lens_controller

        self.is_open = False

        self.window = None

        self._drag_x = 0
        self._drag_y = 0

        self.create_window()
        self.create_widgets()

        register_widget(self)

        self.apply_theme()

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

        self.status_indicator = tk.Label(
            self.status_bar,
            text="●",
            font=("Segoe UI", 10)
        )

        self.status_indicator.pack(
            side="left",
            padx=(8, 4)
        )

        self.status_label = tk.Label(
            self.status_bar,
            text="Ready",
            anchor="w",
            font=("Segoe UI", 9)
        )

        self.status_label.pack(
            side="left"
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
        """
        Display the Floating Lens.

        The lens does NOT capture the desktop.

        It determines its viewport bounds and queries
        the TranslationMap for translated regions that
        intersect the viewport.
        """

        self.is_open = True

        self.lens_controller.start()

        self.window.deiconify()

        self.window.update_idletasks()
        self.window.update()

        self.update_viewport()

    def hide(self):

        self.is_open = False

        self.lens_controller.stop()

        self.window.withdraw()

    def toggle(self):

        if self.is_open:
            self.hide()
        else:
            self.show()

    def close(self):

        self.hide()

    # --------------------------------------------------
    # TranslationMap Viewport
    # --------------------------------------------------

    def update_viewport(self):
        """
        Query the TranslationMap using the current
        Floating Lens viewport.

        This method performs no capture, OCR or
        translation.
        """

        if not self.is_open:
            return

        bounds = self.get_viewport_bounds()

        entries = (
            self.lens_controller.get_visible_translations(
                bounds
            )
        )

        self.render_entries(
            entries
        )

    def render_entries(self, entries):
        """
        Render translations returned by the
        TranslationMap.
        """

        if not entries:

            self.set_translation(
                ""
            )

            self.set_status(
                "No translation in view",
                "gray",
            )

            return

        #
        # For the current single-label UI, display
        # the visible translated regions together.
        #
        translations = []

        for entry in entries:

            if entry.translation:

                translations.append(
                    entry.translation
                )

        if not translations:

            self.set_translation(
                ""
            )

            self.set_status(
                "No translation in view",
                "gray",
            )

            return

        self.set_translation(
            "\n\n".join(
                translations
            )
        )

        self.set_status(
            "Translation Available",
            "green",
        )

    # --------------------------------------------------
    # Translation Display
    # --------------------------------------------------

    def set_translation(
        self,
        text,
    ):

        if not text:

            text = "No translation in view."

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
        color="green",
    ):

        self.status_label.config(
            text=status
        )

        self.status_indicator.config(
            fg=color
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

        #
        # The lens has moved.
        #
        # Query the TranslationMap using the
        # new viewport position.
        #

        self.window.update_idletasks()

        self.update_viewport()

    # --------------------------------------------------
    # Viewport Bounds
    # --------------------------------------------------

    def get_viewport_bounds(
        self,
    ) -> tuple[int, int, int, int]:
        """
        Return the desktop region occupied by the
        Floating Lens translation viewport.

        Returns
        -------
        tuple
            (left, top, width, height)
        """

        self.window.update_idletasks()

        left = (
            self.content.winfo_rootx()
        )

        top = (
            self.content.winfo_rooty()
        )

        width = (
            self.content.winfo_width()
        )

        height = (
            self.content.winfo_height()
        )

        return (
            left,
            top,
            width,
            height,
        )

    # --------------------------------------------------
    # Theme
    # --------------------------------------------------

    def apply_theme(self):

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

        self.status_indicator.configure(
            bg="#202020",
            fg="green"
        )

    # --------------------------------------------------
    # Cleanup
    # --------------------------------------------------

    def destroy(self):

        unregister_widget(self)

        if self.window is not None:

            self.window.destroy()