"""
menu.py

Creates the application menu bar.
"""

import tkinter as tk
from logger import logger


class MenuBar:

    def __init__(self, root):

        self.root = root

        self.menu_bar = tk.Menu(root)

        # Stores the ON/OFF state of Live Translation
        self.live_translation = tk.BooleanVar(value=False)

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
            command=self.root.quit
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
    # TRANSLATE MENUS
    # --------------------------------------------------

    def create_translate_menu(self):

        translate_menu = tk.Menu(self.menu_bar, tearoff=0)

    # Selection Submenu
        selection_menu = tk.Menu(translate_menu, tearoff=0)

        selection_menu.add_command(
            label="Rectangle",
            command=lambda: self.menu_action(
                "TRANSLATE",
                "Rectangle selected"
            )
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
    # PLACEHOLDER MENUS
    # --------------------------------------------------
    
    def create_tools_menu(self):

        tools_menu = tk.Menu(self.menu_bar, tearoff=0)

        self.menu_bar.add_cascade(
            label="Tools",
            menu=tools_menu
        )

    def create_view_menu(self):

        view_menu = tk.Menu(self.menu_bar, tearoff=0)

        self.menu_bar.add_cascade(
            label="View",
            menu=view_menu
        )

    def create_help_menu(self):

        help_menu = tk.Menu(self.menu_bar, tearoff=0)

        self.menu_bar.add_cascade(
            label="Help",
            menu=help_menu
        )

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