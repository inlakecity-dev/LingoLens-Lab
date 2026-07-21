"""
app_settings.py

Stores the application's current runtime settings.

Responsibilities:
- Hold current application settings
- Provide shared settings for the UI and controller

No UI or application logic belongs here.
"""

import config


class AppSettings:

    def __init__(self):

        # Translation Settings
        self.source_language = config.DEFAULT_SOURCE_LANGUAGE
        self.target_language = config.DEFAULT_TARGET_LANGUAGE

        # OCR Settings
        self.ocr_languages = config.OCR_LANGUAGES

        # History
        self.save_history = True

        # Lens
        self.live_translation = False