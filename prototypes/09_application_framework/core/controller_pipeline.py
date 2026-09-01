"""
core/controller_pipeline.py

Controller Image Pipeline

Provides the shared image capture and image-processing
pipeline used by the Controller.

## Responsibilities

- Capture a desktop region for Manual Mode.
- Process an already captured desktop image for Live Mode.
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

from core.capture_engine import (
    capture_region,
    get_desktop_bounds,
)

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
    Shared image capture and image-processing pipeline
    for the Controller.
    """

    MODULE = "ControllerPipeline"

    # --------------------------------------------------
    # Live OCR context
    # --------------------------------------------------
    #
    # ChangeFilter intentionally returns a tight region
    # around the pixels that actually changed.
    #
    # A text change can therefore be much smaller than
    # the complete word, sentence, or paragraph containing
    # that change.
    #
    # Live OCR needs additional surrounding context so
    # Tesseract can recognize the complete text block.
    #
    # These values affect ONLY Live Mode.
    # Manual Mode continues to use the exact selected region.
    #

    LIVE_OCR_CONTEXT_X = 200
    LIVE_OCR_CONTEXT_Y = 40

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

        This is the existing Manual Mode API.

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
        # Manual Mode captures the requested region through
        # the existing capture_region() API.
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
    # LIVE REGION PROCESSING
    # --------------------------------------------------

    def process_live_region(
        self,
        desktop_image,
        bounds,
    ):
        """
        Process a changed desktop region from an already
        captured unified desktop image.

        This method is used by Live Mode.

        IMPORTANT
        ---------
        This method does NOT perform another desktop
        capture.

        The supplied desktop_image must originate from
        the same unified DesktopVisionEngine acquisition
        that produced the dirty-region metadata.

        The incoming bounds represent the meaningful
        changed region identified by ChangeFilter.

        ChangeFilter intentionally produces tight regions.
        Therefore this method expands that region slightly
        before OCR so that a changed character or word can
        be recognized in the context of its surrounding
        text.

        Parameters
        ----------
        desktop_image : PIL.Image
            Complete virtual desktop image.

        bounds : tuple
            Region in Windows virtual-desktop coordinates:

                (left, top, width, height)

        Returns
        -------
        dict
            {
                "result": dict
            }
        """

        if desktop_image is None:
            raise ValueError(
                "Live desktop image cannot be None."
            )

        if not bounds or len(bounds) != 4:
            raise ValueError(
                "Live region bounds must contain "
                "(left, top, width, height)."
            )

        left, top, width, height = bounds

        if width <= 0:
            raise ValueError(
                "Live region width must be "
                "greater than zero."
            )

        if height <= 0:
            raise ValueError(
                "Live region height must be "
                "greater than zero."
            )

        # --------------------------------------------------
        # Determine the virtual desktop image origin.
        #
        # The native DesktopVisionEngine image represents
        # the complete Windows virtual desktop.
        # --------------------------------------------------

        (
            desktop_left,
            desktop_top,
            desktop_width,
            desktop_height,
        ) = get_desktop_bounds()

        desktop_right = (
            desktop_left
            + desktop_width
        )

        desktop_bottom = (
            desktop_top
            + desktop_height
        )

        region_right = (
            left
            + width
        )

        region_bottom = (
            top
            + height
        )

        # --------------------------------------------------
        # Validate the incoming ChangeFilter region.
        # --------------------------------------------------

        if left < desktop_left:
            raise ValueError(
                f"Live region left coordinate {left} "
                f"is outside the virtual desktop."
            )

        if top < desktop_top:
            raise ValueError(
                f"Live region top coordinate {top} "
                f"is outside the virtual desktop."
            )

        if region_right > desktop_right:
            raise ValueError(
                f"Live region right coordinate "
                f"{region_right} exceeds virtual "
                f"desktop right boundary "
                f"{desktop_right}."
            )

        if region_bottom > desktop_bottom:
            raise ValueError(
                f"Live region bottom coordinate "
                f"{region_bottom} exceeds virtual "
                f"desktop bottom boundary "
                f"{desktop_bottom}."
            )

        # --------------------------------------------------
        # Expand the region for OCR context.
        #
        # The incoming region is the actual changed area.
        #
        # Example:
        #
        #     ChangeFilter:
        #
        #             [30 x 24]
        #
        #     becomes:
        #
        #             [430 x 104]
        #     approximately, subject to desktop boundaries.
        #
        # This gives OCR enough surrounding text to identify
        # the complete word/text block.
        #
        # The expanded coordinates are used only for OCR.
        # The resulting OCR bounding boxes are still converted
        # back into absolute desktop coordinates.
        # --------------------------------------------------

        context_left = max(
            desktop_left,
            left - self.LIVE_OCR_CONTEXT_X,
        )

        context_top = max(
            desktop_top,
            top - self.LIVE_OCR_CONTEXT_Y,
        )

        context_right = min(
            desktop_right,
            region_right + self.LIVE_OCR_CONTEXT_X,
        )

        context_bottom = min(
            desktop_bottom,
            region_bottom + self.LIVE_OCR_CONTEXT_Y,
        )

        context_width = (
            context_right
            - context_left
        )

        context_height = (
            context_bottom
            - context_top
        )

        if context_width <= 0:
            raise ValueError(
                "Expanded Live OCR context width must be "
                "greater than zero."
            )

        if context_height <= 0:
            raise ValueError(
                "Expanded Live OCR context height must be "
                "greater than zero."
            )

        logger.info(
            self.MODULE,
            "Expanded Live OCR region "
            f"from ({left}, {top}, {width}, {height}) "
            f"to ({context_left}, {context_top}, "
            f"{context_width}, {context_height})."
        )

        # --------------------------------------------------
        # Convert Windows virtual-desktop coordinates into
        # coordinates inside the unified desktop image.
        # --------------------------------------------------

        crop_left = (
            context_left
            - desktop_left
        )

        crop_top = (
            context_top
            - desktop_top
        )

        crop_right = (
            context_right
            - desktop_left
        )

        crop_bottom = (
            context_bottom
            - desktop_top
        )

        # --------------------------------------------------
        # Crop from the already captured desktop image.
        #
        # NO native capture occurs here.
        # --------------------------------------------------

        region_image = desktop_image.crop(
            (
                crop_left,
                crop_top,
                crop_right,
                crop_bottom,
            )
        )

        # --------------------------------------------------
        # Process the expanded OCR context.
        #
        # IMPORTANT:
        #
        # The origin passed to process_image() is the
        # expanded context origin, NOT the original
        # ChangeFilter region origin.
        #
        # This ensures OCR coordinates are mapped correctly
        # back to Windows desktop coordinates.
        # --------------------------------------------------

        result = self.process_image(
            region_image,
            origin_left=context_left,
            origin_top=context_top,
        )

        return {
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

        logger.info(
            self.MODULE,
            "Image processing started "
            f"for image {image.width}x{image.height} "
            f"at origin ({origin_left}, {origin_top})."
        )

        # ----------------------------------------------
        # Positional OCR
        # ----------------------------------------------

        logger.info(
            self.MODULE,
            "Positional OCR started."
        )

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

        logger.info(
            self.MODULE,
            "Positional OCR completed "
            f"with {len(ocr_data) if ocr_data else 0} "
            "detected item(s)."
        )

        # ----------------------------------------------
        # No OCR text
        # ----------------------------------------------

        if not ocr_data:

            logger.info(
                self.MODULE,
                "No OCR text detected. "
                "Returning no_text result."
            )

            total_time = (
                time.perf_counter()
                - total_start
            )

            print(
                f"TOTAL       : "
                f"{total_time:.3f} sec\n"
            )

            logger.info(
                self.MODULE,
                "Image processing returning "
                "with status=no_text."
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

        logger.info(
            self.MODULE,
            "Grouping OCR items into text blocks."
        )

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

        logger.info(
            self.MODULE,
            "OCR grouping completed: "
            f"{len(grouped_blocks)} text block(s)."
        )

        # ----------------------------------------------
        # Prepare translation jobs
        # ----------------------------------------------

        translation_jobs = []

        for block_items in grouped_blocks.values():

            if not block_items:
                continue

            # ------------------------------------------
            # Sort words in Tesseract reading order.
            # ------------------------------------------

            block_items.sort(
                key=lambda item: (
                    item.get("line_num", 0),
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

            translation_jobs.append(
                {
                    "block_text": block_text,
                    "bounds": (
                        desktop_left,
                        desktop_top,
                        desktop_width,
                        desktop_height,
                    ),
                }
            )

        # ----------------------------------------------
        # Translation
        # ----------------------------------------------

        translated_entries = []

        all_original_text = []
        all_translation_text = []

        logger.info(
            self.MODULE,
            "Translation started for "
            f"{len(translation_jobs)} text block(s)."
        )

        translation_start = time.perf_counter()

        def translate_job(job):
            """
            Translate one independent OCR text block.

            The existing translate_text() API is retained.
            """

            block_text = job["block_text"]

            logger.info(
                self.MODULE,
                "Translating text block "
                f"({len(block_text)} characters)."
            )

            translated_text = translate_text(
                block_text,
                source_language,
                target_language,
            )

            if translated_text is None:
                translated_text = ""

            return {
                "bounds": job["bounds"],
                "original": block_text,
                "translation": str(
                    translated_text
                ).strip(),
            }

        # ----------------------------------------------
        # Sequential translation
        #
        # Translate one OCR block at a time.
        #
        # This intentionally avoids sending several
        # GoogleTranslator requests simultaneously.
        #
        # The previous concurrent implementation could
        # cause the external translation service to return
        # server/error responses.
        # ----------------------------------------------

        for job in translation_jobs:

            translated_entries.append(
                translate_job(job)
            )

        translation_time = (
            time.perf_counter()
            - translation_start
        )

        print(
            f"Translation : "
            f"{translation_time:.3f} sec"
        )

        logger.info(
            self.MODULE,
            "Translation completed. "
            f"{len(translated_entries)} translated "
            "region(s) generated."
        )

        # ----------------------------------------------
        # Combined text
        # ----------------------------------------------

        logger.info(
            self.MODULE,
            "Combining original and translated text."
        )

        for entry in translated_entries:

            all_original_text.append(
                entry["original"]
            )

            all_translation_text.append(
                entry["translation"]
            )

        original_text = "\n".join(
            all_original_text
        ).strip()

        translated_text = "\n".join(
            all_translation_text
        ).strip()

        # ----------------------------------------------
        # History
        # ----------------------------------------------

        logger.info(
            self.MODULE,
            "History save started."
        )

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

        logger.info(
            self.MODULE,
            "History save completed."
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

        logger.info(
            self.MODULE,
            "Image processing stages completed. "
            f"Total time: {total_time:.3f} sec."
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

        result = {
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

        logger.info(
            self.MODULE,
            "Image processing returning "
            f"with status={result['status']}, "
            f"entries={len(translated_entries)}."
        )

        return result