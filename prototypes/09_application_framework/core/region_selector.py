"""
core.region_selector

Provides a reusable transparent screen region selector
for LingoLens.
"""

import tkinter as tk


def select_region():
    """
    Display a transparent fullscreen window that allows
    the user to select a rectangular region.

    Returns:
        tuple:
            (x1, y1, x2, y2)
    """

    coordinates = {}

    root = tk.Tk()
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
                event.x,
                event.y,
            )

    def on_release(event):
        coordinates["x2"] = event.x_root
        coordinates["y2"] = event.y_root

        root.destroy()

    canvas.bind("<ButtonPress-1>", on_press)
    canvas.bind("<B1-Motion>", on_drag)
    canvas.bind("<ButtonRelease-1>", on_release)

    root.mainloop()

    return (
        coordinates["x1"],
        coordinates["y1"],
        coordinates["x2"],
        coordinates["y2"],
    )