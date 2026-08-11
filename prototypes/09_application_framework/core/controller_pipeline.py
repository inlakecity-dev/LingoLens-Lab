"""
core/controller_pipeline.py

Controller Image Pipeline

Provides the shared image capture pipeline used by the Controller.

## Responsibilities

- Capture a desktop region.
- Perform positional OCR.
- Translate detected text blocks.
- Return translated regions with desktop coordinates.
- Preserve the existing image-processing API.

This class does NOT:

- Update the TranslationMap.
- Control the Floating Lens.
- Manage DesktopObserver.
"""

from __future__ import annotations

import time

from core.capture_engine import capture_region

from logger import logger
from core.ocr import extract_text_data
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

        OCR coordinates are converted from image-local
        coordinates into Windows desktop coordinates.

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

        capture_time = (
            time.perf_counter()
            - start
        )

        print(
            f"Region Size : "
            f"{region.image.width} x "
            f"{region.image.height}"
        )

        print(
            f"Capture     : "
            f"{capture_time:.3f} sec"
        )

        # --------------------------------------------------
        # Process the captured image.
        #
        # The region's desktop coordinates are passed into
        # the image pipeline so OCR coordinates can be
        # converted into Windows desktop coordinates.
        # --------------------------------------------------

        result = self.process_image(
            region.image,
            origin_left=region.left,
            origin_top=region.top,
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

    def process_image(
        self,
        image,
        origin_left=0,
        origin_top=0,
    ):
        """
        Process an image through the positional OCR,
        Translation and History pipeline.

        OCR coordinates are relative to the supplied
        image. They are converted into desktop
        coordinates using origin_left and origin_top.

        Parameters
        ----------
        image : PIL.Image
            Image to process.

        origin_left : int
            Windows desktop X coordinate of the
            image's left edge.

        origin_top : int
            Windows desktop Y coordinate of the
            image's top edge.

        Returns
        -------
        dict
            Processing result containing:

                "original"
                "translation"
                "entries"

            where "entries" contains translated
            positional regions.
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
        # Positional OCR
        # ----------------------------------------------

        start = time.perf_counter()

        ocr_data = extract_text_data(
            image,
            self.controller.app_settings.enabled_ocr_languages,
        )

        ocr_time = (
            time.perf_counter()
            - start
        )

        print(
            f"OCR         : "
            f"{ocr_time:.3f} sec"
        )

        # ----------------------------------------------
        # No OCR text
        # ----------------------------------------------

        if not ocr_data:

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
                "entries": [],
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
        # Group OCR words into text blocks
        # ----------------------------------------------
        #
        # Tesseract provides block / paragraph / line
        # information. We use the block and paragraph
        # identifiers to avoid translating every individual
        # word.
        #
        # Each resulting block becomes a candidate
        # TranslationMap region.
        # ----------------------------------------------

        grouped_blocks = {}

        for item in ocr_data:

            block_key = (
                item.get("block_num", 0),
                item.get("par_num", 0),
            )

            if block_key not in grouped_blocks:

                grouped_blocks[block_key] = []

            grouped_blocks[block_key].append(
                item
            )

        # ----------------------------------------------
        # Translation
        # ----------------------------------------------

        translated_entries = []

        all_original_text = []
        all_translation_text = []

        translation_start = time.perf_counter()

        for block_items in grouped_blocks.values():

            if not block_items:
                continue

            # ------------------------------------------
            # Sort words in reading order.
            # ------------------------------------------

            block_items.sort(
                key=lambda item: (
                    item.get("top", 0),
                    item.get("left", 0),
                )
            )

            # ------------------------------------------
            # Build block text.
            # ------------------------------------------

            block_text = " ".join(
                item["text"]
                for item in block_items
                if item["text"].strip()
            ).strip()

            if not block_text:
                continue

            # ------------------------------------------
            # Calculate image-local bounding rectangle.
            # ------------------------------------------

            local_left = min(
                item["left"]
                for item in block_items
            )

            local_top = min(
                item["top"]
                for item in block_items
            )

            local_right = max(
                item["left"] + item["width"]
                for item in block_items
            )

            local_bottom = max(
                item["top"] + item["height"]
                for item in block_items
            )

            # ------------------------------------------
            # Convert to Windows desktop coordinates.
            # ------------------------------------------

            desktop_left = (
                origin_left
                + local_left
            )

            desktop_top = (
                origin_top
                + local_top
            )

            desktop_width = (
                local_right
                - local_left
            )

            desktop_height = (
                local_bottom
                - local_top
            )

            # ------------------------------------------
            # Translate this text block.
            # ------------------------------------------

            translated_text = translate_text(
                block_text,
                source_language,
                target_language,
            )

            if translated_text is None:

                translated_text = ""

            translated_text = str(
                translated_text
            ).strip()

            translated_entries.append(
                {
                    "bounds": (
                        desktop_left,
                        desktop_top,
                        desktop_width,
                        desktop_height,
                    ),
                    "original": block_text,
                    "translation": translated_text,
                }
            )

            all_original_text.append(
                block_text
            )

            all_translation_text.append(
                translated_text
            )

        translation_time = (
            time.perf_counter()
            - translation_start
        )

        print(
            f"Translation : "
            f"{translation_time:.3f} sec"
        )

        # ----------------------------------------------
        # Combined text
        # ----------------------------------------------

        original_text = "\n".join(
            all_original_text
        ).strip()

        translated_text = "\n".join(
            all_translation_text
        ).strip()

        # ----------------------------------------------
        # History
        # ----------------------------------------------

        history_start = time.perf_counter()

        history_file = save_translation(
            original_text,
            translated_text,
            source_language,
            target_language,
        )

        history_time = (
            time.perf_counter()
            - history_start
        )

        print(
            f"History     : "
            f"{history_time:.3f} sec"
        )

        # ----------------------------------------------
        # Total
        # ----------------------------------------------

        total_time = (
            time.perf_counter()
            - total_start
        )

        print("-" * 35)

        print(
            f"TOTAL       : "
            f"{total_time:.3f} sec\n"
        )

        # ----------------------------------------------
        # Debug positional information
        # ----------------------------------------------

        print(
            f"Translated Regions : "
            f"{len(translated_entries)}"
        )

        for index, entry in enumerate(
            translated_entries,
            start=1,
        ):

            print(
                f"[{index:03d}] "
                f"Bounds={entry['bounds']}"
            )

            print(
                f"       Original   : "
                f"{entry['original'][:100]}"
            )

            print(
                f"       Translation: "
                f"{entry['translation'][:100]}"
            )

        # ----------------------------------------------
        # Result
        # ----------------------------------------------

        return {
            "status": "success",
            "original": original_text,
            "translation": translated_text,
            "entries": translated_entries,
            "history_file": history_file,
            "ocr_language": ocr_languages,
            "source_language": source_language,
            "target_language": target_language,
            "ocr_time": ocr_time,
            "translation_time": translation_time,
            "history_time": history_time,
            "total_time": total_time,
        }