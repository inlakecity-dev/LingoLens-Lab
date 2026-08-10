"""
core/controller_pipeline.py

Controller Image Pipeline

Provides the shared image capture pipeline used by the Controller.

## Responsibilities

- Capture a desktop region.
- Process the captured image using the Controller's
  shared image processing pipeline.

This class does NOT:

- Perform Live Translation
- Update the TranslationMap
- Control the Floating Lens
- Manage DesktopObserver
"""

from __future__ import annotations

import time

from core.capture_engine import capture_region

from logger import logger
from core.ocr import extract_text
from core.translator import translate_text
from core.history import save_translation

from config import (
    OCR_LANGUAGE_MAP,
    SOURCE_LANGUAGE_MAP,
    TARGET_LANGUAGE_MAP,
)


class ControllerImagePipeline:
    """
    Shared image capture pipeline for the Controller.
    """

    MODULE = "ControllerPipeline"

    def __init__(self, controller):
        """
        Parameters
        ----------
        controller
            Shared application controller.
        """

        self.controller = controller

        logger.info(
            self.MODULE,
            "Controller image pipeline initialized."
        )

    # --------------------------------------------------
    # SNAPSHOT
    # --------------------------------------------------

    def capture_snapshot(
        self,
        left,
        top,
        width,
        height,
    ):
        """
        Capture a desktop region and process it through
        the Controller's shared image processing pipeline.

        Parameters
        ----------
        left : int
            Left desktop coordinate.

        top : int
            Top desktop coordinate.

        width : int
            Capture width.

        height : int
            Capture height.

        Returns
        -------
        dict
            {
                "captured_region": CapturedRegion,
                "result": dict
            }
        """

        logger.info(
            self.MODULE,
            "Capturing desktop snapshot."
        )

        start = time.perf_counter()

        # --------------------------------------------------
        # Native DesktopVisionEngine capture.
        #
        # capture_region() captures the complete native
        # virtual desktop and crops the requested region.
        # --------------------------------------------------

        region = capture_region(
            left,
            top,
            left + width,
            top + height,
        )

        capture_time = time.perf_counter() - start

        print(
            f"Region Size : "
            f"{region.image.width} x "
            f"{region.image.height}"
        )

        print(
            f"Capture     : "
            f"{capture_time:.3f} sec"
        )

        result = self.process_image(
            region.image
        )

        result["capture_time"] = capture_time

        logger.info(
            self.MODULE,
            "Snapshot processing completed."
        )

        return {
            "captured_region": region,
            "result": result,
        }

    # --------------------------------------------------
    # IMAGE PROCESSING PIPELINE
    # --------------------------------------------------

    def process_image(self, image):
        """
        Process an image through the OCR,
        Translation and History pipeline.

        This shared pipeline is used by every
        workflow that requires image processing.

        The caller is responsible for deciding
        what should happen with the returned result.
        """

        # ----------------------------------------------
        # Read current settings
        # ----------------------------------------------

        source_language = SOURCE_LANGUAGE_MAP[
            self.controller.app_settings.source_language
        ]

        target_language = TARGET_LANGUAGE_MAP[
            self.controller.app_settings.target_language
        ]

        ocr_languages = "+".join(
            OCR_LANGUAGE_MAP[language]
            for language in
            self.controller.app_settings.enabled_ocr_languages
        )

        total_start = time.perf_counter()

        # ----------------------------------------------
        # OCR
        # ----------------------------------------------

        start = time.perf_counter()

        original_text = extract_text(
            image,
            self.controller.app_settings.enabled_ocr_languages,
        )

        ocr_time = time.perf_counter() - start

        print(
            f"OCR         : "
            f"{ocr_time:.3f} sec"
        )

        if not original_text.strip():

            total_time = (
                time.perf_counter()
                - total_start
            )

            print(
                f"TOTAL       : "
                f"{total_time:.3f} sec\n"
            )

            return {
                "status": "no_text",
                "original": "",
                "translation": "",
                "history_file": None,
                "ocr_language": ocr_languages,
                "source_language": source_language,
                "target_language": target_language,
                "ocr_time": ocr_time,
                "translation_time": 0,
                "history_time": 0,
                "total_time": total_time,
            }

        # ----------------------------------------------
        # Translation
        # ----------------------------------------------

        start = time.perf_counter()

        translated_text = translate_text(
            original_text,
            source_language,
            target_language,
        )

        translation_time = (
            time.perf_counter()
            - start
        )

        print(
            f"Translation : "
            f"{translation_time:.3f} sec"
        )

        # ----------------------------------------------
        # History
        # ----------------------------------------------

        start = time.perf_counter()

        history_file = save_translation(
            original_text,
            translated_text,
            source_language,
            target_language,
        )

        history_time = (
            time.perf_counter()
            - start
        )

        print(
            f"History     : "
            f"{history_time:.3f} sec"
        )

        total_time = (
            time.perf_counter()
            - total_start
        )

        print("-" * 35)

        print(
            f"TOTAL       : "
            f"{total_time:.3f} sec\n"
        )

        return {
            "status": "success",
            "original": original_text,
            "translation": translated_text,
            "history_file": history_file,
            "ocr_language": ocr_languages,
            "source_language": source_language,
            "target_language": target_language,
            "ocr_time": ocr_time,
            "translation_time": translation_time,
            "history_time": history_time,
            "total_time": total_time,
        }