"""
workspace_view.py

Developer Workspace Viewer.

Displays the current captured region,
OCR text and translated text.

This is a development tool used to
observe the translation pipeline while
building LingoLens.

It performs NO capture, OCR or translation.
"""

import tkinter as tk

from PIL import ImageTk


class WorkspaceView:
    """
    Developer viewer.

    Pure UI component.

    Receives a CapturedRegion and a processing
    result directly from the controller.
    """

    PREVIEW_SIZE = (320, 180)

    def __init__(self, parent):

        self.parent = parent

        self.photo = None

        self.create_widgets()

    # --------------------------------------------------
    # UI
    # --------------------------------------------------

    def create_widgets(self):

        self.frame = tk.LabelFrame(
            self.parent,
            text="Workspace Viewer",
            padx=10,
            pady=10
        )

        #
        # Captured Image
        #

        tk.Label(
            self.frame,
            text="Captured Image",
            font=("Segoe UI", 9, "bold")
        ).pack(anchor="w")

        self.image_label = tk.Label(
            self.frame,
            text="No Image",
            width=45,
            height=10,
            relief="solid",
            bd=1
        )

        self.image_label.pack(
            fill="x",
            pady=(4, 10)
        )

        #
        # OCR
        #

        tk.Label(
            self.frame,
            text="OCR Text",
            font=("Segoe UI", 9, "bold")
        ).pack(anchor="w")

        self.original_text = tk.Text(
            self.frame,
            height=4,
            wrap="word"
        )

        self.original_text.pack(
            fill="x",
            pady=(4, 10)
        )

        #
        # Translation
        #

        tk.Label(
            self.frame,
            text="Translation",
            font=("Segoe UI", 9, "bold")
        ).pack(anchor="w")

        self.translation_text = tk.Text(
            self.frame,
            height=4,
            wrap="word"
        )

        self.translation_text.pack(
            fill="x"
        )

    # --------------------------------------------------
    # Public API
    # --------------------------------------------------

    def pack(self, **kwargs):

        self.frame.pack(**kwargs)

    def update_workspace(self, captured_region, result):

        #
        # Image
        #

        image = None

        if captured_region is not None:
            image = captured_region.image

        if image is not None:

            preview = image.copy()

            preview.thumbnail(
                self.PREVIEW_SIZE
            )

            self.photo = ImageTk.PhotoImage(
                preview
            )

            self.image_label.configure(
                image=self.photo,
                text=""
            )
        else:

            self.image_label.configure(
                image="",
                text="No Image"
            )

            self.photo = None

        #
        # OCR
        #

        self.original_text.delete(
            "1.0",
            tk.END
        )

        #
        # Translation
        #

        self.translation_text.delete(
            "1.0",
            tk.END
        )

        if result is None:

            return

        self.original_text.insert(
            tk.END,
            result.get(
                "original",
                ""
            )
        )

        self.translation_text.insert(
            tk.END,
            result.get(
                "translation",
                ""
            )
        )

    def clear(self):

        self.image_label.configure(
            image="",
            text="No Image"
        )

        self.photo = None

        self.original_text.delete(
            "1.0",
            tk.END
        )

        self.translation_text.delete(
            "1.0",
            tk.END
        )