"""
theme.py

Centralized theme management for LingoLens.

Responsibilities:
- Define application themes
- Apply Light, Dark, or System theme
- Notify themed widgets when the theme changes

No application logic belongs here.
"""

from tkinter import ttk


# ------------------------------------------------------------------
# Theme Definitions
# ------------------------------------------------------------------

LIGHT_THEME = {
    "background": "#F3F3F3",
    "surface": "#FFFFFF",
    "text": "#1F1F1F",
    "secondary_text": "#555555",
    "accent": "#0078D4",
    "border": "#D9D9D9",
}

DARK_THEME = {
    "background": "#202020",
    "surface": "#2B2B2B",
    "text": "#FFFFFF",
    "secondary_text": "#C8C8C8",
    "accent": "#4CC2FF",
    "border": "#404040",
}


# ------------------------------------------------------------------
# Theme State
# ------------------------------------------------------------------

_current_theme = LIGHT_THEME

_themed_widgets = []


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------

def get_theme():
    """
    Returns the currently active theme dictionary.
    """
    return _current_theme


def register_widget(widget):
    """
    Registers a widget that supports apply_theme().
    """

    if widget not in _themed_widgets:
        _themed_widgets.append(widget)


def unregister_widget(widget):
    """
    Removes a widget from theme updates.
    """

    if widget in _themed_widgets:
        _themed_widgets.remove(widget)


# ------------------------------------------------------------------
# Theme Engine
# ------------------------------------------------------------------

def apply_theme(root, theme_name="system"):
    """
    Applies the selected application theme.
    """

    global _current_theme

    if theme_name == "dark":
        _current_theme = DARK_THEME

    elif theme_name == "system":
        # Future:
        # Detect Windows/macOS/Linux theme.
        _current_theme = LIGHT_THEME

    else:
        _current_theme = LIGHT_THEME

    theme = _current_theme

    # --------------------------------------------------------------
    # ttk Styling
    # --------------------------------------------------------------

    style = ttk.Style(root)

    style.theme_use("clam")

    style.configure(
        ".",
        background=theme["background"],
        foreground=theme["text"],
    )

    style.configure(
        "TFrame",
        background=theme["background"],
    )

    style.configure(
        "TLabel",
        background=theme["background"],
        foreground=theme["text"],
    )

    style.configure(
        "TButton",
        padding=6,
    )

    root.configure(
        background=theme["background"]
    )

    # --------------------------------------------------------------
    # Notify all themed widgets
    # --------------------------------------------------------------

    for widget in _themed_widgets:

        if hasattr(widget, "apply_theme"):

            try:
                widget.apply_theme()

            except Exception:
                pass