"""
Application Configuration
"""

# ==========================================================
# Application Information
# ==========================================================

APP_NAME = "LingoLens"

VERSION = "0.9"

# ==========================================================
# Window Configuration
# ==========================================================

WINDOW_WIDTH = 900
WINDOW_HEIGHT = 600

# ==========================================================
# Assets
# ==========================================================

APP_ICON = "assets/branding/LingoLens_Icon.ico"

# ==========================================================
# Fonts
# ==========================================================

FONT = ("Nirmala UI", 11)

# ==========================================================
# Tesseract OCR executable path
# ==========================================================

TESSERACT_PATH = (
    r"C:\Users\harish.singh.bisht\AppData\Local\Programs\Tesseract-OCR\tesseract.exe"
)

# ==========================================================
# OCR Configuration
# ==========================================================

OCR_LANGUAGE_MAP = {
    "English": "eng",
    "Hindi": "hin",
    "Japanese": "jpn",
    "Chinese": "chi_sim",
}

DEFAULT_OCR_LANGUAGES = [
    "English",
    "Hindi",
    "Japanese",
    "Chinese",
]

# ==========================================================
# Translation Languages
# ==========================================================

SOURCE_LANGUAGE_MAP = {
    "Auto Detect": "auto",
    "English": "en",
    "Hindi": "hi",
    "Japanese": "ja",
    "Chinese": "zh-CN",
}

TARGET_LANGUAGE_MAP = {
    "English": "en",
    "Hindi": "hi",
    "Japanese": "ja",
    "Chinese": "zh-CN",
}

DEFAULT_SOURCE_LANGUAGE = "Auto Detect"
DEFAULT_TARGET_LANGUAGE = "English"

# ==========================================================
# History Configuration
# ==========================================================

HISTORY_FOLDER = "history"