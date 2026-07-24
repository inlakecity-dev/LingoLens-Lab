"""
ocr_languages_window.py

Creates the OCR Languages window.
"""

import tkinter as tk
from tkinter import ttk

import config
from helpers import center_window, set_window_icon


class OCRLanguagesWindow:

    def __init__(
        self,
        root,
        app_settings
    ):

        self.root = root
        self.app_settings = app_settings

        self.language_vars = {}

    def save_settings(self):

        selected_languages = []

        for language, variable in self.language_vars.items():

            if variable.get():

                selected_languages.append(language)

        self.app_settings.ocr_languages = selected_languages

        self.window.destroy()

    def show(self):

        self.window = tk.Toplevel(self.root)

        set_window_icon(self.window)

        self.window.title("OCR Languages")

        self.window.resizable(False, False)

        center_window(
            self.window,
            400,
            320
        )

        content = ttk.Frame(
            self.window,
            padding=20
        )

        content.pack(
            fill="both",
            expand=True
        )

        ttk.Label(
            content,
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
                content,
                text=language,
                variable=variable
            ).pack(
                anchor="w",
                pady=2
            )

        ttk.Separator(
            content,
            orient="horizontal"
        ).pack(
            fill="x",
            pady=20
        )

        button_frame = ttk.Frame(content)

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
            padx=5
        )

        ttk.Button(
            button_frame,
            text="Cancel",
            width=12,
            command=self.window.destroy
        ).pack(
            side="left"
        )