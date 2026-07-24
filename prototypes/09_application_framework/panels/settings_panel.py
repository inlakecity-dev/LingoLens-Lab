"""
settings_panel.py

Settings flyout panel.

Responsibilities:
- Display translation settings
- Update AppSettings
- No window creation
"""

import tkinter as tk
from tkinter import ttk

import config
from panels.base_panel import BasePanel


class SettingsPanel(BasePanel):

    def __init__(self, parent, app_settings):

        super().__init__(parent)

        self.app_settings = app_settings

        # --------------------------------------------------
        # Translation
        # --------------------------------------------------

        ttk.Label(
            self.content,
            text="Source Language"
        ).pack(
            anchor="w"
        )

        self.source_language = tk.StringVar(
            value=self.app_settings.source_language
        )

        ttk.Combobox(
            self.content,
            textvariable=self.source_language,
            values=list(config.SOURCE_LANGUAGE_MAP.keys()),
            state="readonly",
            width=35
        ).pack(
            anchor="w",
            pady=(5, 15)
        )

        ttk.Label(
            self.content,
            text="Target Language"
        ).pack(
            anchor="w"
        )

        self.target_language = tk.StringVar(
            value=self.app_settings.target_language
        )

        ttk.Combobox(
            self.content,
            textvariable=self.target_language,
            values=list(config.TARGET_LANGUAGE_MAP.keys()),
            state="readonly",
            width=35
        ).pack(
            anchor="w",
            pady=(5, 20)
        )

        ttk.Separator(
            self.content,
            orient="horizontal"
        ).pack(
            fill="x",
            pady=10
        )

        # --------------------------------------------------
        # Buttons
        # --------------------------------------------------

        button_frame = ttk.Frame(self.content)

        button_frame.pack(
            anchor="e",
            pady=(10, 0)
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

        self.app_settings.source_language = (
            self.source_language.get()
        )

        self.app_settings.target_language = (
            self.target_language.get()
        )

        self.close()