"""
helpers.py

Shared utility functions used throughout the application.
"""

import os


def center_window(window, width, height):
    """
    Center a Tkinter window on the screen.
    """

    window.update_idletasks()

    screen_width = window.winfo_screenwidth()
    screen_height = window.winfo_screenheight()

    x = (screen_width - width) // 2
    y = (screen_height - height) // 2

    window.geometry(f"{width}x{height}+{x}+{y}")


def resource_path(relative_path):
    """
    Returns the correct resource path.

    Works both in development and after packaging with PyInstaller.
    """

    try:
        base_path = os.sys._MEIPASS
    except AttributeError:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)