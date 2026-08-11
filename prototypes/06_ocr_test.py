from PIL import Image
import pytesseract


# ------------------------------------------------------------
# Tesseract
# ------------------------------------------------------------

pytesseract.pytesseract.tesseract_cmd = (
    r"C:\Users\harish.singh.bisht\AppData\Local\Programs\Tesseract-OCR\tesseract.exe"
)


# ------------------------------------------------------------
# Load test image
# ------------------------------------------------------------

image = Image.open("OCRTest.png")


# ------------------------------------------------------------
# Positional OCR
# ------------------------------------------------------------

data = pytesseract.image_to_data(
    image,
    lang="eng+jpn+chi_sim+hin+rus+san",
    output_type=pytesseract.Output.DICT,
)


# ------------------------------------------------------------
# Display OCR results
# ------------------------------------------------------------

print()
print("========================================")
print("LingoLens Positional OCR Test")
print("========================================")
print()

print(
    f"Image Size : "
    f"{image.width} x {image.height}"
)

print()

detected_count = 0


for index, text in enumerate(data["text"]):

    text = text.strip()

    if not text:
        continue

    try:
        confidence = float(
            data["conf"][index]
        )
    except (
        ValueError,
        TypeError,
    ):
        confidence = -1.0

    left = int(
        data["left"][index]
    )

    top = int(
        data["top"][index]
    )

    width = int(
        data["width"][index]
    )

    height = int(
        data["height"][index]
    )

    detected_count += 1

    print(
        f"[{detected_count:03}] "
        f"Text       : {text}"
    )

    print(
        f"     Position : "
        f"x={left}, "
        f"y={top}, "
        f"w={width}, "
        f"h={height}"
    )

    print(
        f"     Confidence : "
        f"{confidence:.1f}"
    )

    print()


# ------------------------------------------------------------
# Summary
# ------------------------------------------------------------

print("========================================")
print(
    f"Detected OCR elements : {detected_count}"
)
print("========================================")