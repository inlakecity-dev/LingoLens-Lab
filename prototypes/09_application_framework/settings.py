"""
settings.py

Creates the Settings window.
"""

import tkinter as tk


class SettingsWindow:

    def __init__(self, root):

        self.root = root
        
        
    def show(self):

        settings = tk.Toplevel(self.root)

        settings.title("Settings")

        settings.resizable(False, False)

        settings.geometry("450x300")
        
        tk.Label(
            settings,
            text="Settings",
            font=("Segoe UI", 16, "bold")
        ).pack(pady=(20, 10))
    
        tk.Label(
            settings,
            text="General settings will appear here.",
            font=("Segoe UI", 10)
        ).pack(pady=10)
    
        tk.Button(
            settings,
            text="Close",
            width=12,
            command=settings.destroy
        ).pack(pady=30)