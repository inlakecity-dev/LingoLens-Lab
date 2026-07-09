import tkinter as tk
from PIL import ImageGrab
import pytesseract
from deep_translator import GoogleTranslator
from tkinter import messagebox

pytesseract.pytesseract.tesseract_cmd = (
    r"C:\Users\harish.singh.bisht\AppData\Local\Programs\Tesseract-OCR\tesseract.exe"
)

root = tk.Tk()
root.attributes("-fullscreen", True)
root.attributes("-alpha", 0.3)

start_x = start_y = 0

canvas = tk.Canvas(root, cursor="cross")
canvas.pack(fill="both", expand=True)

rect = None

def on_press(event):
    global start_x, start_y, rect

    start_x = event.x
    start_y = event.y

    rect = canvas.create_rectangle(
        start_x,
        start_y,
        start_x,
        start_y,
        outline="blue",
        width=2
    )

def on_drag(event):
    canvas.coords(
        rect,
        start_x,
        start_y,
        event.x,
        event.y
    )

def on_release(event):

    root.destroy()

    screenshot = ImageGrab.grab(
        bbox=(
            start_x,
            start_y,
            event.x,
            event.y
        )
    )

    screenshot.save("selection.png")

    text = pytesseract.image_to_string(
        screenshot,
        lang="eng+hin+jpn+chi_sim+rus"
    )

    translated = GoogleTranslator(
        source="auto",
        target="en"
    ).translate(text)

    messagebox.showinfo(
        "Translation",
        f"Original:\n\n{text.strip()}\n\n"
        f"Translation:\n\n{translated}"
    )

    print("Saved selection.png")

canvas.bind("<ButtonPress-1>", on_press)
canvas.bind("<B1-Motion>", on_drag)
canvas.bind("<ButtonRelease-1>", on_release)

root.mainloop()