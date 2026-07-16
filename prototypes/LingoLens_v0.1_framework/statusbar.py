"""
statusbar.py

Creates the application status bar.
"""

import tkinter as tk


class StatusBar:

    def __init__(self, root):

        self.root = root

        self.status_text = tk.StringVar()

        self.status_text.set("Ready")

        self.status_label = tk.Label(
            root,
            textvariable=self.status_text,
            anchor="w",
            relief=tk.SUNKEN
        )

        self.status_label.pack(
            side=tk.BOTTOM,
            fill=tk.X
        )

    def set_status(self, message):

        self.status_text.set(message)