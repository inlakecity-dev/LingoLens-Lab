import pyautogui
from PIL import Image
from deep_translator import GoogleTranslator
import pytesseract

pytesseract.pytesseract.tesseract_cmd = (
    r"C:\Users\harish.singh.bisht\AppData\Local\Programs\Tesseract-OCR\tesseract.exe"
)

screenshot = pyautogui.screenshot()

screenshot.save("screen.png")

image = Image.open("screen.png")

text = pytesseract.image_to_string(
    image,
    lang="eng+hin+jpn+chi_sim+rus"
)

print("\nDetected Text:\n")
print(text)
translated = GoogleTranslator(
    source="auto",
    target="en"
).translate(text)

print("\nTranslation:\n")
print(translated)
