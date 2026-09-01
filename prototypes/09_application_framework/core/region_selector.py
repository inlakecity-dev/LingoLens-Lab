"""
core.region_selector

Provides a reusable transparent screen region selector
for LingoLens.

The selector covers the complete Windows virtual desktop,
including all connected monitors.
"""

import tkinter as tk

from core.capture_engine import get_desktop_bounds


MIN_SELECTION_SIZE = 10


def select_region(parent):
    """
    Display a transparent window covering the complete
    Windows virtual desktop and allow the user to select
    a rectangular region.

    Returns
    -------
    tuple
        (x1, y1, x2, y2)

        Coordinates are absolute Windows virtual-desktop
        coordinates.

    None
        If the selection is cancelled.
    """

    coordinates = {}

    # --------------------------------------------------
    # Get complete Windows virtual desktop bounds
    # --------------------------------------------------

    (
        desktop_left,
        desktop_top,
        desktop_width,
        desktop_height,
    ) = get_desktop_bounds()

    # --------------------------------------------------
    # Create selector window
    # --------------------------------------------------

    root = tk.Toplevel(parent)

    root.title(
        "LingoLens Region Selector"
    )

    #
    # Do NOT use Tkinter fullscreen here.
    #
    # "-fullscreen" normally targets the primary monitor.
    #
    # Instead explicitly position the selector over the
    # complete Windows virtual desktop.
    #

    root.overrideredirect(True)

    root.geometry(
        f"{desktop_width}x{desktop_height}"
        f"{desktop_left:+d}"
        f"{desktop_top:+d}"
    )

    root.attributes(
        "-alpha",
        0.30
    )

    root.configure(
        bg="black"
    )

    # --------------------------------------------------
    # Canvas
    # --------------------------------------------------

    canvas = tk.Canvas(
        root,
        cursor="cross",
        bg="black",
        highlightthickness=0,
    )

    canvas.pack(
        fill="both",
        expand=True
    )

    rectangle = None

    # --------------------------------------------------
    # Selection helpers
    # --------------------------------------------------

    def cancel_selection(event=None):
        """
        Cancel the current selection.
        """

        coordinates.clear()

        try:
            root.grab_release()
        except tk.TclError:
            pass

        root.destroy()

    def on_press(event):
        """
        Start a new selection.
        """

        nonlocal rectangle

        #
        # event.x_root / event.y_root are absolute screen
        # coordinates. These are exactly what we need for
        # the TranslationMap and capture engine.
        #

        coordinates["x1"] = event.x_root
        coordinates["y1"] = event.y_root

        #
        # Canvas coordinates are local to the selector
        # window, so convert absolute desktop coordinates
        # into selector-local coordinates.
        #

        local_x = (
            event.x_root
            - desktop_left
        )

        local_y = (
            event.y_root
            - desktop_top
        )

        rectangle = canvas.create_rectangle(
            local_x,
            local_y,
            local_x,
            local_y,
            outline="red",
            width=2,
        )

    def on_drag(event):
        """
        Update the selection rectangle while dragging.
        """

        if rectangle is None:
            return

        start_x = (
            coordinates["x1"]
            - desktop_left
        )

        start_y = (
            coordinates["y1"]
            - desktop_top
        )

        current_x = (
            event.x_root
            - desktop_left
        )

        current_y = (
            event.y_root
            - desktop_top
        )

        canvas.coords(
            rectangle,
            start_x,
            start_y,
            current_x,
            current_y,
        )

    def on_release(event):
        """
        Complete the selection.
        """

        coordinates["x2"] = event.x_root
        coordinates["y2"] = event.y_root

        # --------------------------------------------------
        # Normalize absolute desktop coordinates
        # --------------------------------------------------

        x1 = min(
            coordinates["x1"],
            coordinates["x2"],
        )

        y1 = min(
            coordinates["y1"],
            coordinates["y2"],
        )

        x2 = max(
            coordinates["x1"],
            coordinates["x2"],
        )

        y2 = max(
            coordinates["y1"],
            coordinates["y2"],
        )

        # --------------------------------------------------
        # Ignore accidental clicks
        # --------------------------------------------------

        if (
            (x2 - x1) < MIN_SELECTION_SIZE
            or
            (y2 - y1) < MIN_SELECTION_SIZE
        ):

            cancel_selection()

            return

        # --------------------------------------------------
        # Store normalized absolute coordinates
        # --------------------------------------------------

        coordinates["x1"] = x1
        coordinates["y1"] = y1
        coordinates["x2"] = x2
        coordinates["y2"] = y2

        try:
            root.grab_release()
        except tk.TclError:
            pass

        root.destroy()

    # --------------------------------------------------
    # Events
    # --------------------------------------------------

    canvas.bind(
        "<ButtonPress-1>",
        on_press
    )

    canvas.bind(
        "<B1-Motion>",
        on_drag
    )

    canvas.bind(
        "<ButtonRelease-1>",
        on_release
    )

    root.bind(
        "<Escape>",
        cancel_selection
    )

    # --------------------------------------------------
    # Activate selector
    # --------------------------------------------------

    root.grab_set()

    root.focus_force()

    root.wait_window()

    # --------------------------------------------------
    # Return selection
    # --------------------------------------------------

    if not coordinates:
        return None

    return (
        coordinates["x1"],
        coordinates["y1"],
        coordinates["x2"],
        coordinates["y2"],
    )