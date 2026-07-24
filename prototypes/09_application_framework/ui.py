"""
ui.py
"""

import tkinter as tk
from tkinter import ttk

import config
from helpers import center_window
from menu import MenuBar
from statusbar import StatusBar
from about import AboutWindow
from controller import Controller
from core.region_selector import select_region
from core.display import enable_dpi_awareness
from translation_view import TranslationView
from app_settings import AppSettings
from theme import apply_theme


class MainWindow:

    def __init__(self):

        enable_dpi_awareness()

        self.root = tk.Tk()
        self.root.iconbitmap(config.APP_ICON)
        self.root.title(config.APP_NAME)

        # --------------------------------------------------
        # Runtime
        # --------------------------------------------------

        self.app_settings = AppSettings()

        # --------------------------------------------------
        # Theme
        # --------------------------------------------------

        apply_theme(
            self.root,
            self.app_settings.theme
        )

        self.controller = Controller(
            self.app_settings
        )

        # --------------------------------------------------
        # Menu
        # --------------------------------------------------

        self.menu_bar = MenuBar(
            self.root,
            self,
            self.app_settings
        )

        # --------------------------------------------------
        # Workspace
        # --------------------------------------------------

        self.workspace = ttk.Frame(
            self.root
        )

        self.workspace.pack(
            fill="both",
            expand=True
        )

        self.workspace.rowconfigure(
            0,
            weight=1
        )

        self.workspace.columnconfigure(
            0,
            weight=1
        )

        # --------------------------------------------------
        # Translation View
        # --------------------------------------------------

        self.translation_view = TranslationView(
            self.workspace
        )

        self.translation_view.grid(
            row=0,
            column=0,
            sticky="nsew"
        )

        # --------------------------------------------------
        # Status Bar
        # --------------------------------------------------

        self.status_bar = StatusBar(
            self.root
        )

        # --------------------------------------------------
        # Window
        # --------------------------------------------------

        center_window(
            self.root,
            config.WINDOW_WIDTH,
            config.WINDOW_HEIGHT
        )

    # --------------------------------------------------
    # Menu Commands
    # --------------------------------------------------

    def show_about(self):

        AboutWindow(
            self.root
        ).show()

    # --------------------------------------------------
    # Translation
    # --------------------------------------------------

    def start_rectangle_translation(self):

        selection = select_region(
            self.root
        )

        if selection is None:
            return

        x1, y1, x2, y2 = selection

        result = self.controller.translate_region(
            x1,
            y1,
            x2,
            y2,
        )

        self.translation_view.update(
            result
        )

    # --------------------------------------------------
    # Run
    # --------------------------------------------------

    def run(self):

        self.root.mainloop()