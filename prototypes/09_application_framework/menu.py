"""
menu.py

Creates the application menu bar.
"""

import tkinter as tk
from logger import logger


class MenuBar:
    """
    Creates the application menu bar.
    """

    def __init__(self, root):

        self.root = root

        self.menu_bar = tk.Menu(root)

        self.create_menus()

        self.root.config(menu=self.menu_bar)

    def create_menus(self):

        self.create_file_menu()
        self.create_lens_menu()
        self.create_translate_menu()
        self.create_tools_menu()
        self.create_view_menu()
        self.create_help_menu()

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
            label="Exit",
            command=self.root.quit
        )

        self.menu_bar.add_cascade(
            label="File",
            menu=file_menu
        )

    def create_lens_menu(self):
        pass

    def create_translate_menu(self):
        pass

    def create_tools_menu(self):
        pass

    def create_view_menu(self):
        pass

    def create_help_menu(self):
        pass

    def menu_action(self, module, message):
        """
        Handles menu click events.
        """

        logger.info(module, message)