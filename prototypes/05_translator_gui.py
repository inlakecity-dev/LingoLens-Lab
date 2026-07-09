import tkinter as tk
from deep_translator import GoogleTranslator
from datetime import datetime
from tkinter import messagebox

languages = {
    "English": "en",
    "Hindi": "hi",
    "Japanese": "ja",
    "Chinese": "zh-CN"
}
history = []
window = tk.Tk()

window.title("Translator")
window.geometry("600x400")

title = tk.Label(
    window,
    text="Translation Tool",
    font=("Arial", 16)
)

title.pack(pady=10)

selected_language = tk.StringVar()

selected_language.set("English")

language_label = tk.Label(
    window,
    text="Target Language"
)

language_label.pack()

language_menu = tk.OptionMenu(
    window,
    selected_language,
    *languages.keys()
)

language_menu.pack(pady=10)

input_box = tk.Text(
    window,
    height=5,
    width=60
)

input_box.pack(pady=10)


def translate_text():

    text = input_box.get(
        "1.0",
        tk.END
    )

    target_language = languages[
    selected_language.get()
    ]

    translated = GoogleTranslator(
        source="auto",
        target=target_language
    ).translate(text)

    output_box.delete(
        "1.0",
        tk.END
    )

    output_box.insert(
        tk.END,
        translated)

    history.append(
        f"Original: {text.strip()} | Translated: {translated}"
    )

translate_button = tk.Button(
    window,
    text="Translate",
    command=translate_text
)

translate_button.pack(pady=10)

def save_history():

    if len(history) == 0:

        messagebox.showwarning(
            "No History",
            "There is no history to save."
        )

        return

    timestamp = datetime.now().strftime("%m%d%yT%H%M%S")

    filename = f"THD{timestamp}.txt"

    with open(filename, "w", encoding="utf-8") as file:

        for item in history:

            file.write(item + "\n")

    messagebox.showinfo(
        "Saved",
        f"History saved to\n{filename}"
    )

save_button = tk.Button(
    window,
    text="Save History",
    command=save_history
)

save_button.pack(pady=5)

output_box = tk.Text(
    window,
    height=5,
    width=60
)

output_box.pack(pady=10)

window.mainloop()