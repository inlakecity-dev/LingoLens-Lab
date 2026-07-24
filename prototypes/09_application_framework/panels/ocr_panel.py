"""
ocr_panel.py

OCR Languages flyout panel.

Responsibilities:
- Display OCR language selection
- Update AppSettings
- No window creation
"""

import tkinter as tk
from tkinter import ttk

import config
from panels.base_panel import BasePanel


class OCRPanel(BasePanel):

    def __init__(self, parent, app_settings):

        super().__init__(parent)

        self.app_settings = app_settings
        self.language_vars = {}

        # --------------------------------------------------
        # Languages
        # --------------------------------------------------

        ttk.Label(
            self.content,
            text="Select OCR languages:"
        ).pack(
            anchor="w",
            pady=(0, 15)
        )

        for language in config.OCR_LANGUAGE_MAP.keys():

            variable = tk.BooleanVar(
                value=language in self.app_settings.ocr_languages
            )

            self.language_vars[language] = variable

            ttk.Checkbutton(
                self.content,
                text=language,
                variable=variable
            ).pack(
                anchor="w",
                pady=2
            )

        ttk.Separator(
            self.content,
            orient="horizontal"
        ).pack(
            fill="x",
            pady=20
        )

        # --------------------------------------------------
        # Buttons
        # --------------------------------------------------

        button_frame = ttk.Frame(self.content)

        button_frame.pack(
            anchor="e"
        )

        ttk.Button(
            button_frame,
            text="Save",
            width=12,
            command=self.save_settings
        ).pack(
            side="left",
            padx=(0, 5)
        )

        ttk.Button(
            button_frame,
            text="Cancel",
            width=12,
            command=self.close
        ).pack(
            side="left"
        )

    def save_settings(self):

        selected_languages = []

        for language, variable in self.language_vars.items():

            if variable.get():
                selected_languages.append(language)

        self.app_settings.ocr_languages = selected_languages

        self.close()