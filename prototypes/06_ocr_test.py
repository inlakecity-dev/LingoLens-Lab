from PIL import Image
import pytesseract

pytesseract.pytesseract.tesseract_cmd = (
    r"C:\Users\harish.singh.bisht\AppData\Local\Programs\Tesseract-OCR\tesseract.exe"
)

image = Image.open("OCRTest.png")

text = pytesseract.image_to_string(
    image,
    lang="eng+jpn+chi_sim+hin+rus+san"
)

print("\nDetected Text:\n")
print(text)