"""
translation_view.py

Displays OCR text and translated text.

Responsibilities:
- Show original text
- Show translated text
- Clear display
- Update display

No OCR, translation, or history logic belongs here.
"""

import tkinter as tk
from tkinter import ttk

import config
from theme import get_theme


class TranslationView(ttk.Frame):

    def __init__(self, parent):

        super().__init__(parent, padding=10)

        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        self.rowconfigure(3, weight=1)

        # -------------------------
        # Original Text
        # -------------------------

        ttk.Label(
            self,
            text="Original Text"
        ).grid(
            row=0,
            column=0,
            sticky="w",
            pady=(0, 5)
        )

        self.original_text = tk.Text(
            self,
            width=40,
            height=10,
            font=("Nirmala UI", 12),
            wrap="word",
            relief="solid",
            borderwidth=1
        )

        self.original_text.grid(
            row=1,
            column=0,
            sticky="nsew"
        )

        # -------------------------
        # Translation
        # -------------------------

        ttk.Label(
            self,
            text="Translation"
        ).grid(
            row=2,
            column=0,
            sticky="w",
            pady=(10, 5)
        )

        self.translation_text = tk.Text(
            self,
            height=8,
            font=("Nirmala UI", 12),
            wrap="word",
            relief="solid",
            borderwidth=1
        )

        self.translation_text.grid(
            row=3,
            column=0,
            sticky="nsew"
        )

        # Apply current theme
        self.apply_theme()

    # --------------------------------------------------
    # Theme
    # --------------------------------------------------

    def apply_theme(self):

        theme = get_theme()

        text_options = {
            "bg": theme["surface"],
            "fg": theme["text"],
            "insertbackground": theme["text"],
            "selectbackground": theme["accent"],
            "selectforeground": "#FFFFFF",
            "highlightbackground": theme["border"],
            "highlightcolor": theme["accent"],
        }

        self.original_text.configure(**text_options)
        self.translation_text.configure(**text_options)

    # --------------------------------------------------
    # PUBLIC METHODS
    # --------------------------------------------------

    def clear(self):

        self.original_text.delete("1.0", tk.END)
        self.translation_text.delete("1.0", tk.END)

    def update(self, result):

        self.clear()

        self.original_text.insert(
            tk.END,
            result.get("original", "")
        )

        self.translation_text.insert(
            tk.END,
            result.get("translation", "")
        )