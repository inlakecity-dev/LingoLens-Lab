"""
menu.py

Creates the application menu bar.
"""
from theme import apply_theme
import tkinter as tk

from config import (
    OCR_LANGUAGE_MAP,
    SOURCE_LANGUAGE_MAP,
    TARGET_LANGUAGE_MAP,
)
from logger import logger


class MenuBar:

    def __init__(self, root, controller, app_settings):

        self.root = root
        self.controller = controller
        self.app_settings = app_settings

        self.menu_bar = tk.Menu(root)

        # Stores the ON/OFF state of Live Translation
        self.live_translation = tk.BooleanVar(value=False)

        # Language menu variables
        self.source_language = tk.StringVar(
            value=self.app_settings.source_language
        )

        self.target_language = tk.StringVar(
            value=self.app_settings.target_language
        )
                
        self.theme = tk.StringVar(
            value=self.app_settings.theme
        )

        self.ocr_language_vars = {}

        self.create_menus()

        self.root.config(menu=self.menu_bar)

    def create_menus(self):

        self.create_file_menu()
        self.create_lens_menu()
        self.create_translate_menu()
        self.create_tools_menu()
        self.create_view_menu()
        self.create_help_menu()

    # --------------------------------------------------
    # FILE MENU
    # --------------------------------------------------

    def create_file_menu(self):

        file_menu = tk.Menu(self.menu_bar, tearoff=0)

        file_menu.add_command(
            label="New Session",
            command=lambda: self.menu_action(
                "FILE",
                "New Session selected"
            )
        )

        file_menu.add_separator()

        file_menu.add_command(
            label="Save Translation",
            command=lambda: self.menu_action(
                "FILE",
                "Save Translation selected"
            )
        )

        file_menu.add_command(
            label="Export History",
            command=lambda: self.menu_action(
                "FILE",
                "Export History selected"
            )
        )

        file_menu.add_separator()

        file_menu.add_command(
            label="Exit",
            command=self.exit_application
        )

        self.menu_bar.add_cascade(
            label="File",
            menu=file_menu
        )

    # --------------------------------------------------
    # LENS MENU
    # --------------------------------------------------

    def create_lens_menu(self):

        lens_menu = tk.Menu(self.menu_bar, tearoff=0)

        lens_menu.add_checkbutton(
            label="Live Translation",
            variable=self.live_translation,
            command=self.toggle_live_translation
        )

        lens_menu.add_separator()

        lens_menu.add_command(
            label="Open Floating Lens",
            command=lambda: self.menu_action(
                "LENS",
                "Open Floating Lens selected"
            )
        )

        lens_menu.add_command(
            label="Lens Settings",
            command=lambda: self.menu_action(
                "LENS",
                "Lens Settings selected"
            )
        )

        self.menu_bar.add_cascade(
            label="Lens",
            menu=lens_menu
        )

    # --------------------------------------------------
    # TRANSLATE MENU
    # --------------------------------------------------

    def create_translate_menu(self):

        translate_menu = tk.Menu(self.menu_bar, tearoff=0)

        selection_menu = tk.Menu(translate_menu, tearoff=0)

        selection_menu.add_command(
            label="Rectangle",
            command=self.controller.start_rectangle_translation
        )

        selection_menu.add_command(
            label="Circle",
            command=lambda: self.menu_action(
                "TRANSLATE",
                "Circle selected"
            )
        )

        selection_menu.add_command(
            label="Freehand",
            command=lambda: self.menu_action(
                "TRANSLATE",
                "Freehand selected"
            )
        )

        selection_menu.add_command(
            label="Window",
            command=lambda: self.menu_action(
                "TRANSLATE",
                "Window selected"
            )
        )

        selection_menu.add_command(
            label="Entire Screen",
            command=lambda: self.menu_action(
                "TRANSLATE",
                "Entire Screen selected"
            )
        )

        translate_menu.add_cascade(
            label="Selection",
            menu=selection_menu
        )

        translate_menu.add_separator()

        translate_menu.add_command(
            label="Clipboard",
            command=lambda: self.menu_action(
                "TRANSLATE",
                "Clipboard selected"
            )
        )

        translate_menu.add_command(
            label="Open Image",
            command=lambda: self.menu_action(
                "TRANSLATE",
                "Open Image selected"
            )
        )

        translate_menu.add_command(
            label="Recent Images",
            command=lambda: self.menu_action(
                "TRANSLATE",
                "Recent Images selected"
            )
        )

        self.menu_bar.add_cascade(
            label="Translate",
            menu=translate_menu
        )

    # --------------------------------------------------
    # TOOLS MENU
    # --------------------------------------------------

    def create_tools_menu(self):

        tools_menu = tk.Menu(self.menu_bar, tearoff=0)

        settings_menu = tk.Menu(tools_menu, tearoff=0)
        ocr_menu = tk.Menu(settings_menu, tearoff=0)
        source_menu = tk.Menu(settings_menu, tearoff=0)
        target_menu = tk.Menu(settings_menu, tearoff=0)

        # OCR Languages

        for language in OCR_LANGUAGE_MAP:

            enabled = (
                language in self.app_settings.enabled_ocr_languages
            )

            variable = tk.BooleanVar(value=enabled)

            self.ocr_language_vars[language] = variable

            ocr_menu.add_checkbutton(
                label=language,
                variable=variable,
                command=lambda lang=language: (
                    self.update_ocr_language(lang)
                )
            )

        # Source Language

        for language in SOURCE_LANGUAGE_MAP:

            source_menu.add_radiobutton(
                label=language,
                variable=self.source_language,
                value=language,
                command=self.update_source_language
            )

        # Target Language

        for language in TARGET_LANGUAGE_MAP:

            target_menu.add_radiobutton(
                label=language,
                variable=self.target_language,
                value=language,
                command=self.update_target_language
            )

        settings_menu.add_cascade(
            label="OCR Languages",
            menu=ocr_menu
        )

        settings_menu.add_cascade(
            label="Source Language",
            menu=source_menu
        )

        settings_menu.add_cascade(
            label="Target Language",
            menu=target_menu
        )

        tools_menu.add_cascade(
            label="Settings",
            menu=settings_menu
        )

        tools_menu.add_separator()

        tools_menu.add_command(
            label="History",
            command=lambda: self.menu_action(
                "TOOLS",
                "History selected"
            )
        )

        tools_menu.add_command(
            label="Log Viewer",
            command=lambda: self.menu_action(
                "TOOLS",
                "Log Viewer selected"
            )
        )

        self.menu_bar.add_cascade(
            label="Tools",
            menu=tools_menu
        )

    # --------------------------------------------------
    # VIEW MENU
    # --------------------------------------------------

    def create_view_menu(self):

        view_menu = tk.Menu(self.menu_bar, tearoff=0)

        theme_menu = tk.Menu(view_menu, tearoff=0)

        theme_menu.add_radiobutton(
            label="Light",
            variable=self.theme,
            value="light",
            command=self.update_theme
        )

        theme_menu.add_radiobutton(
            label="Dark",
            variable=self.theme,
            value="dark",
            command=self.update_theme
        )

        theme_menu.add_radiobutton(
            label="System",
            variable=self.theme,
            value="system",
            command=self.update_theme
        )

        view_menu.add_cascade(
            label="Theme",
            menu=theme_menu
        )

        view_menu.add_separator()

        view_menu.add_command(
            label="Always On Top",
            command=lambda: self.menu_action(
                "VIEW",
                "Always On Top selected"
            )
        )

        view_menu.add_command(
            label="Reset Layout",
            command=lambda: self.menu_action(
                "VIEW",
                "Reset Layout selected"
            )
        )

        self.menu_bar.add_cascade(
            label="View",
            menu=view_menu
        )

    # --------------------------------------------------
    # HELP MENU
    # --------------------------------------------------

    def create_help_menu(self):

        help_menu = tk.Menu(self.menu_bar, tearoff=0)

        help_menu.add_command(
            label="Documentation",
            command=lambda: self.menu_action(
                "HELP",
                "Documentation selected"
            )
        )

        help_menu.add_command(
            label="Keyboard Shortcuts",
            command=lambda: self.menu_action(
                "HELP",
                "Keyboard Shortcuts selected"
            )
        )

        help_menu.add_separator()

        help_menu.add_command(
            label="Check for Updates",
            command=lambda: self.menu_action(
                "HELP",
                "Check for Updates selected"
            )
        )

        help_menu.add_separator()

        help_menu.add_command(
            label="About",
            command=self.show_about
        )

        self.menu_bar.add_cascade(
            label="Help",
            menu=help_menu
        )

    # --------------------------------------------------
    # SETTINGS ACTIONS
    # --------------------------------------------------

    def update_ocr_language(self, language):

        enabled_languages = [
            name
            for name, variable in self.ocr_language_vars.items()
            if variable.get()
        ]

        self.app_settings.enabled_ocr_languages = enabled_languages

        logger.info(
            "TOOLS",
            f"OCR Languages updated: {', '.join(enabled_languages)}"
        )

    def update_source_language(self):

        self.app_settings.source_language = (
            self.source_language.get()
        )

        logger.info(
            "TOOLS",
            f"Source Language: {self.source_language.get()}"
        )

    def update_target_language(self):

        self.app_settings.target_language = (
            self.target_language.get()
        )

        logger.info(
            "TOOLS",
            f"Target Language: {self.target_language.get()}"
        )
        
    def update_theme(self):

        self.app_settings.theme = self.theme.get()

        apply_theme(
            self.root,
            self.app_settings.theme
        )

        logger.info(
            "VIEW",
            f"{self.app_settings.theme.title()} Theme selected"
        )    

    # --------------------------------------------------
    # WINDOW ACTIONS
    # --------------------------------------------------

    def show_about(self):

        logger.info(
            "HELP",
            "About selected"
        )

        self.controller.show_about()

    def exit_application(self):

        logger.info(
            "FILE",
            "Application Exit"
        )

        self.root.destroy()

    # --------------------------------------------------
    # MENU ACTIONS
    # --------------------------------------------------

    def menu_action(self, module, message):

        logger.info(module, message)

    # --------------------------------------------------
    # LENS ACTIONS
    # --------------------------------------------------

    def toggle_live_translation(self):

        if self.live_translation.get():

            logger.info(
                "LENS",
                "Live Translation Enabled"
            )

        else:

            logger.info(
                "LENS",
                "Live Translation Disabled"
            )