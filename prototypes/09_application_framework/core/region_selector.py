"""
core.region_selector

Provides a reusable transparent screen region selector
for LingoLens.
"""

import tkinter as tk

MIN_SELECTION_SIZE = 10


def select_region(parent):
    """
    Display a transparent fullscreen window that allows
    the user to select a rectangular region.

    Returns:
        tuple:
            (x1, y1, x2, y2)

        or

        None
            if the selection is cancelled.
    """

    coordinates = {}

    root = tk.Toplevel(parent)
    root.title("LingoLens Region Selector")

    root.attributes("-fullscreen", True)
    root.attributes("-alpha", 0.30)

    root.configure(bg="black")

    canvas = tk.Canvas(
        root,
        cursor="cross",
        bg="black",
        highlightthickness=0,
    )

    canvas.pack(fill="both", expand=True)

    rectangle = None

    def cancel_selection(event=None):
        coordinates.clear()
        root.destroy()

    def on_press(event):
        nonlocal rectangle

        coordinates["x1"] = event.x_root
        coordinates["y1"] = event.y_root

        rectangle = canvas.create_rectangle(
            event.x,
            event.y,
            event.x,
            event.y,
            outline="red",
            width=2,
        )

    def on_drag(event):
        if rectangle is not None:
            canvas.coords(
                rectangle,
                coordinates["x1"],
                coordinates["y1"],
                event.x_root,
                event.y_root,
            )

    def on_release(event):

        coordinates["x2"] = event.x_root
        coordinates["y2"] = event.y_root

        # Normalize coordinates
        x1 = min(coordinates["x1"], coordinates["x2"])
        y1 = min(coordinates["y1"], coordinates["y2"])
        x2 = max(coordinates["x1"], coordinates["x2"])
        y2 = max(coordinates["y1"], coordinates["y2"])

        # Ignore accidental clicks
        if (
            (x2 - x1) < MIN_SELECTION_SIZE
            or
            (y2 - y1) < MIN_SELECTION_SIZE
        ):
            cancel_selection()
            return

        coordinates["x1"] = x1
        coordinates["y1"] = y1
        coordinates["x2"] = x2
        coordinates["y2"] = y2

        root.destroy()

    canvas.bind("<ButtonPress-1>", on_press)
    canvas.bind("<B1-Motion>", on_drag)
    canvas.bind("<ButtonRelease-1>", on_release)

    root.bind("<Escape>", cancel_selection)

    root.grab_set()
    root.focus_force()
    root.wait_window()

    if not coordinates:
        return None

    return (
        coordinates["x1"],
        coordinates["y1"],
        coordinates["x2"],
        coordinates["y2"],
    )