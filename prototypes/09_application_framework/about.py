"""
about.py

Creates the About window.
"""

import tkinter as tk


class AboutWindow:

    def __init__(self, root):

        self.root = root

    def show(self):

        about = tk.Toplevel(self.root)

        about.title("About LingoLens")

        about.resizable(False, False)

        about.geometry("420x280")

        tk.Label(
            about,
            text="LingoLens",
            font=("Segoe UI", 16, "bold")
        ).pack(pady=(20, 5))

        tk.Label(
            about,
            text="Read. Understand. Continue.",
            font=("Segoe UI", 10)
        ).pack()

        tk.Label(
            about,
            text="",
        ).pack()

        tk.Label(
            about,
            text="Prototype 09\nProfessional Application Framework",
            justify="center"
        ).pack()

        tk.Label(
            about,
            text="",
        ).pack()

        tk.Label(
            about,
            text="Created by\nHarish Singh Bisht",
            justify="center"
        ).pack()

        tk.Button(
            about,
            text="OK",
            width=10,
            command=about.destroy
        ).pack(pady=20)