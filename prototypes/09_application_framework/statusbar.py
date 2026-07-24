"""
statusbar.py

Creates the application status bar.
"""

import tkinter as tk

from theme import get_theme, register_widget


class StatusBar:

    def __init__(self, root):

        self.root = root

        self.status_text = tk.StringVar()

        self.status_text.set("Ready")

        self.status_label = tk.Label(
            root,
            textvariable=self.status_text,
            anchor="w",
            relief=tk.SUNKEN,
            padx=8,
            pady=2,
        )

        self.status_label.pack(
            side=tk.BOTTOM,
            fill=tk.X
        )

        # Apply current theme
        self.apply_theme()

        # Receive future theme updates
        register_widget(self)

    # --------------------------------------------------
    # Theme
    # --------------------------------------------------

    def apply_theme(self):

        theme = get_theme()

        self.status_label.configure(
            bg=theme["surface"],
            fg=theme["text"],
            activebackground=theme["surface"],
            activeforeground=theme["text"],
            highlightbackground=theme["border"],
        )

    # --------------------------------------------------
    # Public Methods
    # --------------------------------------------------

    def set_status(self, message):

        self.status_text.set(message)