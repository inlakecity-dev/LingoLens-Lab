"""
LingoLens Controller Test

Development tool for testing the complete
translation pipeline without the main UI.
"""

import time

from controller import translate_region
from core.region_selector import select_region
from core.display import enable_dpi_awareness

enable_dpi_awareness()


# ==========================================================
# Language Options
# ==========================================================

OCR_LANGUAGES = {
    "1": ("English", "eng"),
    "2": ("Hindi", "hin"),
    "3": ("English + Hindi", "eng+hin"),
    "4": ("Japanese", "jpn"),
    "5": ("Chinese", "chi_sim"),
}

TARGET_LANGUAGES = {
    "1": ("English", "en"),
    "2": ("Hindi", "hi"),
    "3": ("Japanese", "ja"),
    "4": ("Chinese", "zh-CN"),
    "5": ("French", "fr"),
    "6": ("German", "de"),
}


# ==========================================================
# Language Selection
# ==========================================================

def select_ocr_language():
    """Prompt user to select an OCR language."""

    print("OCR Language")
    print("-" * 60)

    for key, value in OCR_LANGUAGES.items():
        print(f"{key}. {value[0]}")

    choice = input("\nSelect OCR Language : ").strip()

    return OCR_LANGUAGES.get(choice, OCR_LANGUAGES["1"])


def select_target_language():
    """Prompt user to select a target translation language."""

    print("\nTarget Language")
    print("-" * 60)

    for key, value in TARGET_LANGUAGES.items():
        print(f"{key}. {value[0]}")

    choice = input("\nSelect Target Language : ").strip()

    return TARGET_LANGUAGES.get(choice, TARGET_LANGUAGES["1"])


# ==========================================================
# Output
# ==========================================================

def print_results(result, elapsed_time):
    """Display translation results."""

    print("\n" + "=" * 60)
    print("Translation Result")
    print("=" * 60)

    print("\nStatus")
    print("-" * 60)

    if result["status"] == "no_text":
        print("No text detected.")
        print("\nProcessing Time")
        print("-" * 60)
        print(f"{elapsed_time:.2f} seconds")
        return

    print("Success")

    print("\nOriginal Text")
    print("-" * 60)
    print(result["original"])

    print("\nTranslation")
    print("-" * 60)
    print(result["translation"])

    print("\nHistory File")
    print("-" * 60)
    print(result["history_file"])

    print("\nOCR Language")
    print("-" * 60)
    print(result["ocr_language"])

    print("\nSource Language")
    print("-" * 60)
    print(result["source_language"])

    print("\nTarget Language")
    print("-" * 60)
    print(result["target_language"])

    print("\nProcessing Time")
    print("-" * 60)
    print(f"{elapsed_time:.2f} seconds")


# ==========================================================
# Main
# ==========================================================

def main():
    """Run the complete translation pipeline."""

    print("=" * 60)
    print("           LingoLens Controller Test")
    print("=" * 60)
    print()

    ocr_name, ocr_code = select_ocr_language()
    target_name, target_code = select_target_language()

    print("\nSelected Languages")
    print("-" * 60)
    print(f"OCR Language    : {ocr_name}")
    print(f"Target Language : {target_name}")

    print("\nLaunching Region Selector...")
    print("Click and drag to select the text you want to translate.\n")

    selection = select_region()

    if selection is None:
        print("\nSelection cancelled.")
        return

    x1, y1, x2, y2 = selection

    print("\nSelected Region")
    print("-" * 60)
    print(f"X1 : {x1}")
    print(f"Y1 : {y1}")
    print(f"X2 : {x2}")
    print(f"Y2 : {y2}")

    start_time = time.perf_counter()

    try:
        result = translate_region(
            x1,
            y1,
            x2,
            y2,
            ocr_languages=ocr_code,
            source_language="auto",
            target_language=target_code,
        )

        elapsed_time = time.perf_counter() - start_time

        print_results(result, elapsed_time)

    except Exception as error:
        print("\n" + "=" * 60)
        print("Error")
        print("=" * 60)
        print(error)


# ==========================================================
# Entry Point
# ==========================================================

if __name__ == "__main__":
    main()