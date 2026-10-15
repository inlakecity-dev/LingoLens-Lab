"""
core/controller_pipeline.py

Controller Image Pipeline

Provides the shared image capture and image-processing
pipeline used by the Controller.

## Responsibilities

- Capture a desktop region for Manual Mode.
- Process an already captured desktop image for Live Mode.
- Perform positional OCR.
- Translate detected visual text lines.
- Return translated regions with desktop coordinates.
- Preserve the existing image-processing API.

This class does NOT:

- Update the TranslationMap.
- Control the Floating Lens.
- Manage DesktopObserver.
"""

from __future__ import annotations

import re
import time
from pathlib import Path

from core.capture_engine import (
    capture_region,
    get_desktop_bounds,
)

from logger import logger
from core.ocr import extract_text_data
from core.translator import translate_text_batch
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

    LIVE_OCR_CONTEXT_X = 200
    LIVE_OCR_CONTEXT_Y = 40

    # --------------------------------------------------
    # Visual OCR line grouping
    # --------------------------------------------------

    LINE_MIN_HORIZONTAL_GAP = 60
    LINE_MAX_HORIZONTAL_GAP = 160
    LINE_HORIZONTAL_GAP_FACTOR = 6

    # --------------------------------------------------
    # Translation-context diagnostics
    #
    # IMPORTANT:
    #
    # These settings are diagnostic only.
    # They do NOT change translation behavior.
    # --------------------------------------------------

    TRANSLATION_CONTEXT_MAX_VERTICAL_GAP = 80
    TRANSLATION_CONTEXT_MAX_HORIZONTAL_OFFSET = 250

    # --------------------------------------------------
    # OCR normalization
    # --------------------------------------------------

    @staticmethod
    def _is_cjk_character(character):
        """
        Return True when a character belongs to a CJK,
        Hiragana or Katakana Unicode block.

        This is intentionally limited to scripts where
        whitespace between individual characters is normally
        an OCR artifact rather than meaningful word spacing.
        """

        if not character:
            return False

        codepoint = ord(character)

        return (
            0x3400 <= codepoint <= 0x4DBF      # CJK Extension A
            or 0x4E00 <= codepoint <= 0x9FFF   # CJK Unified
            or 0xF900 <= codepoint <= 0xFAFF   # CJK Compatibility
            or 0x3040 <= codepoint <= 0x309F   # Hiragana
            or 0x30A0 <= codepoint <= 0x30FF   # Katakana
            or 0x31F0 <= codepoint <= 0x31FF   # Katakana Extensions
            or 0xAC00 <= codepoint <= 0xD7AF   # Hangul
        )

    @staticmethod
    def _is_devanagari_character(character):
        """
        Return True when a character belongs to the
        Devanagari Unicode block.
        """

        if not character:
            return False

        codepoint = ord(character)

        return 0x0900 <= codepoint <= 0x097F

    @classmethod
    def _is_predominantly_hindi(cls, text):
        """
        Return True when the text contains a meaningful
        amount of Devanagari and is therefore likely to be
        Hindi OCR rather than English, German or another
        language.

        This is intentionally conservative so that the Hindi
        cleanup cannot affect other language text.
        """

        if not text:
            return False

        devanagari_count = sum(
            1
            for character in text
            if cls._is_devanagari_character(character)
        )

        letter_count = sum(
            1
            for character in text
            if character.isalpha()
        )

        if devanagari_count < 2:
            return False

        if letter_count == 0:
            return False

        return (
            devanagari_count / letter_count
        ) >= 0.60

    @classmethod
    def _normalize_hindi_ocr_text(cls, text):
        """
        Apply conservative cleanup to predominantly Hindi OCR.

        The goal is to remove obvious OCR contamination without
        changing normal Hindi word spacing.

        Examples of contamination observed in Live Mode:

            "1 के दौरान कंप्यूटर..."
                -> "के दौरान कंप्यूटर..."

        The cleanup intentionally does NOT attempt to rewrite
        Hindi words or punctuation and does NOT alter geometry.
        """

        if not text:
            return text

        if not cls._is_predominantly_hindi(text):
            return text

        # --------------------------------------------------
        # Remove an isolated leading numeric OCR artifact.
        #
        # Example observed:
        #
        #   "1 के दौरान कंप्यूटर..."
        #
        # This is intentionally restricted to the beginning
        # of a predominantly Devanagari line.
        # --------------------------------------------------

        text = re.sub(
            r"^\s*[0-9]+\s+(?=[\u0900-\u097F])",
            "",
            text,
        )

        # --------------------------------------------------
        # Remove an isolated Latin OCR token when it appears
        # directly between Devanagari text.
        #
        # Example observed in the logs:
        #
        #   "... सुरक्षित Su से सेव ..."
        #
        # This is deliberately conservative:
        #
        # - only short alphabetic tokens are considered
        # - the token must be surrounded by Devanagari
        # - normal English words elsewhere in a Hindi line
        #   are preserved
        #
        # This is text cleanup only. Geometry is untouched.
        # --------------------------------------------------

        text = re.sub(
            r"(?<=[\u0900-\u097F])\s+[A-Za-z]{1,3}\s+(?=[\u0900-\u097F])",
            " ",
            text,
        )

        # --------------------------------------------------
        # Remove repeated whitespace introduced by cleanup.
        # --------------------------------------------------

        text = re.sub(
            r"\s+",
            " ",
            text,
        ).strip()

        return text

    @classmethod
    def _normalize_ocr_text(cls, text):
        """
        Normalize obvious OCR whitespace noise while
        preserving normal word spacing.

        Examples
        --------
        CJK OCR:
            "今 回 の ア ッ プ デ ー ト"
            -> "今回のアップデート"

        German/English:
            "Die neue Version bietet"
            -> "Die neue Version bietet"

        Hindi:
            Obvious OCR contamination is removed conservatively,
            while normal Hindi word spacing is preserved.

        This method changes text only. OCR geometry and
        confidence data remain untouched.
        """

        if text is None:
            return ""

        text = str(text).strip()

        if not text:
            return ""

        # --------------------------------------------------
        # Normalize all ordinary whitespace first.
        #
        # This preserves word boundaries while removing
        # accidental repeated spaces/tabs/newlines.
        # --------------------------------------------------

        text = re.sub(
            r"\s+",
            " ",
            text,
        ).strip()

        if not text:
            return ""

        # --------------------------------------------------
        # Hindi-specific OCR cleanup.
        #
        # This runs before CJK normalization and only applies
        # to predominantly Devanagari text.
        # --------------------------------------------------

        text = cls._normalize_hindi_ocr_text(
            text
        )

        if not text:
            return ""

        # --------------------------------------------------
        # Remove whitespace between CJK/Hiragana/Katakana/
        # Hangul characters.
        #
        # This specifically addresses OCR output such as:
        #
        #   今 回 の ア ッ プ デ ー ト
        #
        # -> 今回のアップデート
        #
        # IMPORTANT:
        #
        # Always inspect the original text by character
        # position. Do not calculate the next character
        # from the length of the already-normalized output,
        # because removed spaces change that length.
        # --------------------------------------------------

        normalized_characters = []

        for index, character in enumerate(text):

            if character == " ":

                previous_character = (
                    text[index - 1]
                    if index > 0
                    else ""
                )

                next_character = (
                    text[index + 1]
                    if index + 1 < len(text)
                    else ""
                )

                if (
                    cls._is_cjk_character(
                        previous_character
                    )
                    and cls._is_cjk_character(
                        next_character
                    )
                ):
                    continue

            normalized_characters.append(
                character
            )

        text = "".join(
            normalized_characters
        )

        # --------------------------------------------------
        # Remove spaces around common CJK punctuation.
        #
        # Example:
        #
        #   で 、 シ ス テ ム は
        #
        # becomes:
        #
        #   で、システムは
        # --------------------------------------------------

        cjk_punctuation = (
            "、。，．！？：；"
            "「」『』（）［］【】"
            "〈〉《》〔〕"
            "・"
        )

        punctuation_pattern = (
            rf"\s*([{re.escape(cjk_punctuation)}])\s*"
        )

        text = re.sub(
            punctuation_pattern,
            r"\1",
            text,
        )

        # --------------------------------------------------
        # Final whitespace normalization.
        #
        # This intentionally does NOT remove spaces between
        # Latin or Devanagari words.
        # --------------------------------------------------

        text = re.sub(
            r"\s+",
            " ",
            text,
        ).strip()

        return text

    @classmethod
    def _build_line_text(cls, line_items):
        """
        Build normalized text from OCR items belonging to
        one physical visual line.

        Physical line membership and item geometry are not
        modified here. Only the resulting textual
        representation is normalized.
        """

        raw_text = " ".join(
            item["text"]
            for item in line_items
            if item.get("text", "").strip()
        ).strip()

        return cls._normalize_ocr_text(
            raw_text
        )

    @staticmethod
    def _get_line_confidence_summary(line_items):
        """
        Return a diagnostic confidence summary for one
        physical OCR line.

        IMPORTANT:
        This method is diagnostic only.

        It does not modify, filter, reorder, or reject
        OCR results.
        """

        valid_confidences = [
            float(item["confidence"])
            for item in line_items
            if item.get("confidence", -1) >= 0
        ]

        if not valid_confidences:
            return {
                "average": None,
                "minimum": None,
                "maximum": None,
                "below_50": 0,
                "below_70": 0,
                "valid_count": 0,
            }

        return {
            "average": (
                sum(valid_confidences)
                / len(valid_confidences)
            ),
            "minimum": min(
                valid_confidences
            ),
            "maximum": max(
                valid_confidences
            ),
            "below_50": sum(
                confidence < 50
                for confidence in valid_confidences
            ),
            "below_70": sum(
                confidence < 70
                for confidence in valid_confidences
            ),
            "valid_count": len(
                valid_confidences
            ),
        }

    @staticmethod
    def _line_has_terminal_punctuation(text):
        """
        Return True when a physical OCR line appears to end
        with sentence-ending punctuation.

        This method is diagnostic only.

        It intentionally recognizes punctuation commonly
        encountered in Latin, Devanagari, Chinese and Japanese
        text.
        """

        if not text:
            return False

        stripped = text.rstrip()

        if not stripped:
            return False

        return stripped[-1] in (
            ".",
            "!",
            "?",
            ":",
            ";",
            "。",
            "！",
            "？",
            "：",
            "；",
            "।",
            "॥",
        )

    @staticmethod
    def _line_horizontal_overlap(first_bounds, second_bounds):
        """
        Return the horizontal overlap distance between two
        TranslationMap-style bounds.

        Bounds format:

            (left, top, width, height)
        """

        first_left, _, first_width, _ = first_bounds
        second_left, _, second_width, _ = second_bounds

        first_right = first_left + first_width
        second_right = second_left + second_width

        return max(
            0,
            min(first_right, second_right)
            - max(first_left, second_left),
        )

    @classmethod
    def _diagnose_translation_context_groups(
        cls,
        translation_jobs,
    ):
        """
        Diagnose likely linguistic continuation groups.

        IMPORTANT
        ---------
        This method is diagnostic only.

        It does NOT:

        - change translation_jobs
        - merge physical OCR lines
        - change bounds
        - change OCR output
        - change translation input
        - change TranslationMap behavior

        The purpose is to identify cases where a physical
        OCR line appears to continue into the following
        physical line.

        This is particularly useful for cases such as:

            इसके अलावा, Microsoft Teams के साथ ...
            जिससे ऑनलाइन मीटिंग में
            शामिल होना अधिक सुविधाजनक हो गया है।

        where the second line is not a complete linguistic
        sentence even though it is a valid physical OCR line.
        """

        if not translation_jobs:
            logger.info(
                cls.MODULE,
                "Translation-context diagnostic: "
                "no translation jobs available."
            )
            return

        candidate_groups = []

        for index in range(
            len(translation_jobs) - 1
        ):

            current = translation_jobs[index]
            following = translation_jobs[index + 1]

            current_bounds = current["bounds"]
            following_bounds = following["bounds"]

            current_left = current_bounds[0]
            current_top = current_bounds[1]
            current_width = current_bounds[2]
            current_height = current_bounds[3]

            following_left = following_bounds[0]
            following_top = following_bounds[1]
            following_width = following_bounds[2]
            following_height = following_bounds[3]

            current_bottom = (
                current_top
                + current_height
            )

            vertical_gap = (
                following_top
                - current_bottom
            )

            if vertical_gap < 0:
                vertical_gap = 0

            horizontal_offset = abs(
                following_left
                - current_left
            )

            horizontal_overlap = (
                cls._line_horizontal_overlap(
                    current_bounds,
                    following_bounds,
                )
            )

            current_has_terminal_punctuation = (
                cls._line_has_terminal_punctuation(
                    current["line_text"]
                )
            )

            # --------------------------------------------------
            # Diagnostic candidate criteria.
            #
            # We deliberately require several spatial signals:
            #
            # 1. Lines are vertically close.
            # 2. Their left edges are reasonably aligned OR
            #    their horizontal ranges overlap.
            # 3. The current line does not end with strong
            #    sentence punctuation.
            #
            # This is deliberately conservative and is NOT
            # used to modify translation behavior.
            # --------------------------------------------------

            spatially_close = (
                vertical_gap
                <= cls.TRANSLATION_CONTEXT_MAX_VERTICAL_GAP
            )

            horizontally_related = (
                horizontal_overlap > 0
                or horizontal_offset
                <= cls.TRANSLATION_CONTEXT_MAX_HORIZONTAL_OFFSET
            )

            likely_continuation = (
                spatially_close
                and horizontally_related
                and not current_has_terminal_punctuation
            )

            if not likely_continuation:
                continue

            candidate_groups.append(
                {
                    "first_index": index + 1,
                    "second_index": index + 2,
                    "first_text": current["line_text"],
                    "second_text": following["line_text"],
                    "first_bounds": current_bounds,
                    "second_bounds": following_bounds,
                    "vertical_gap": vertical_gap,
                    "horizontal_offset": horizontal_offset,
                    "horizontal_overlap": horizontal_overlap,
                }
            )

        logger.info(
            cls.MODULE,
            "TRANSLATION CONTEXT DIAGNOSTIC: "
            f"{len(candidate_groups)} "
            "possible continuation pair(s) detected "
            f"among {len(translation_jobs)} "
            "physical translation unit(s)."
        )

        for index, candidate in enumerate(
            candidate_groups,
            start=1,
        ):

            logger.info(
                cls.MODULE,
                "TRANSLATION CONTEXT CANDIDATE "
                f"[{index:03d}] "
                f"physical_units="
                f"{candidate['first_index']},"
                f"{candidate['second_index']} "
                f"vertical_gap="
                f"{candidate['vertical_gap']} "
                f"horizontal_offset="
                f"{candidate['horizontal_offset']} "
                f"horizontal_overlap="
                f"{candidate['horizontal_overlap']} "
                f"first_bounds="
                f"{candidate['first_bounds']} "
                f"second_bounds="
                f"{candidate['second_bounds']} "
                f"first_text="
                f"{candidate['first_text'][:200]!r} "
                f"second_text="
                f"{candidate['second_text'][:200]!r}"
            )

        # --------------------------------------------------
        # Also log the candidate combined text.
        #
        # This is especially useful for comparing what NLLB
        # currently receives against the linguistic context
        # it would ideally receive.
        # --------------------------------------------------

        for index, candidate in enumerate(
            candidate_groups,
            start=1,
        ):

            combined_text = (
                candidate["first_text"]
                + " "
                + candidate["second_text"]
            )

            logger.info(
                cls.MODULE,
                "TRANSLATION CONTEXT PROPOSAL "
                f"[{index:03d}] "
                f"text={combined_text[:400]!r}"
            )

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

    @classmethod
    def _group_ocr_items_into_lines(cls, ocr_data):
        """
        Group Tesseract word boxes into physical visual lines.

        Tesseract already supplies block, paragraph and line
        identifiers. This method therefore uses:

            (block_num, par_num, line_num)

        as the primary physical line identity.

        A second horizontal geometry pass is then applied to
        each Tesseract line.

        Returns
        -------
        list[list[dict]]
            OCR items grouped into physical visual text lines.
        """

        if not ocr_data:
            return []

        # --------------------------------------------------
        # Keep only valid OCR word items.
        # --------------------------------------------------

        items = [
            item
            for item in ocr_data
            if item.get("text", "").strip()
            and item.get("width", 0) > 0
            and item.get("height", 0) > 0
        ]

        if not items:
            return []

        # --------------------------------------------------
        # Sort by actual screen geometry first.
        # --------------------------------------------------

        items.sort(
            key=lambda item: (
                item.get("top", 0),
                item.get("left", 0),
            )
        )

        # --------------------------------------------------
        # Primary grouping:
        #
        # Tesseract physical line identity.
        # --------------------------------------------------

        tesseract_lines = {}

        for item in items:

            key = (
                item.get("block_num", 0),
                item.get("par_num", 0),
                item.get("line_num", 0),
            )

            tesseract_lines.setdefault(
                key,
                [],
            ).append(item)

        all_lines = []

        # --------------------------------------------------
        # Process each Tesseract line independently.
        # --------------------------------------------------

        for line_key, line_items in tesseract_lines.items():

            if not line_items:
                continue

            line_items.sort(
                key=lambda item: item.get(
                    "left",
                    0,
                )
            )

            # --------------------------------------------------
            # Calculate median OCR word height.
            # --------------------------------------------------

            heights = sorted(
                item["height"]
                for item in line_items
                if item["height"] > 0
            )

            if not heights:
                continue

            middle = len(heights) // 2

            if len(heights) % 2:
                median_height = float(
                    heights[middle]
                )
            else:
                median_height = (
                    heights[middle - 1]
                    + heights[middle]
                ) / 2.0

            horizontal_gap_threshold = max(
                cls.LINE_MIN_HORIZONTAL_GAP,
                min(
                    cls.LINE_MAX_HORIZONTAL_GAP,
                    median_height
                    * cls.LINE_HORIZONTAL_GAP_FACTOR,
                ),
            )

            # --------------------------------------------------
            # Split only when there is a large horizontal gap.
            # --------------------------------------------------

            split_line = [line_items[0]]

            for item in line_items[1:]:

                previous = split_line[-1]

                previous_right = (
                    previous["left"]
                    + previous["width"]
                )

                gap = (
                    item["left"]
                    - previous_right
                )

                if gap > horizontal_gap_threshold:

                    all_lines.append(
                        split_line
                    )

                    split_line = [item]

                else:

                    split_line.append(
                        item
                    )

            if split_line:

                all_lines.append(
                    split_line
                )

        # --------------------------------------------------
        # Final physical reading order.
        # --------------------------------------------------

        all_lines.sort(
            key=lambda line: (
                min(
                    item["top"]
                    for item in line
                ),
                min(
                    item["left"]
                    for item in line
                ),
            )
        )

        logger.info(
            cls.MODULE,
            "Tesseract line grouping produced "
            f"{len(all_lines)} physical line(s) "
            f"from {len(items)} OCR item(s)."
        )

        # --------------------------------------------------
        # DIAGNOSTIC ONLY
        #
        # Log the exact physical OCR lines after grouping.
        #
        # This intentionally logs grouped lines rather than
        # every OCR token so that diagnostic logging does not
        # introduce the large I/O overhead seen previously.
        # --------------------------------------------------

        for index, line_items in enumerate(
            all_lines,
            start=1,
        ):

            if not line_items:
                continue

            line_items.sort(
                key=lambda item: item.get(
                    "left",
                    0,
                )
            )

            line_text = cls._build_line_text(
                line_items
            )

            line_left = min(
                item["left"]
                for item in line_items
            )

            line_top = min(
                item["top"]
                for item in line_items
            )

            line_right = max(
                item["left"]
                + item["width"]
                for item in line_items
            )

            line_bottom = max(
                item["top"]
                + item["height"]
                for item in line_items
            )

            block_values = sorted(
                {
                    item.get("block_num", 0)
                    for item in line_items
                }
            )

            paragraph_values = sorted(
                {
                    item.get("par_num", 0)
                    for item in line_items
                }
            )

            line_values = sorted(
                {
                    item.get("line_num", 0)
                    for item in line_items
                }
            )

            confidence = (
                cls._get_line_confidence_summary(
                    line_items
                )
            )

            if confidence["average"] is None:

                confidence_text = (
                    "confidence_avg=N/A, "
                    "confidence_min=N/A, "
                    "confidence_max=N/A, "
                    "below50=0, "
                    "below70=0"
                )

            else:

                confidence_text = (
                    "confidence_avg="
                    f"{confidence['average']:.1f}, "
                    "confidence_min="
                    f"{confidence['minimum']:.1f}, "
                    "confidence_max="
                    f"{confidence['maximum']:.1f}, "
                    "below50="
                    f"{confidence['below_50']}, "
                    "below70="
                    f"{confidence['below_70']}"
                )

            logger.info(
                cls.MODULE,
                "OCR PHYSICAL LINE "
                f"[{index:03d}] "
                f"items={len(line_items)}, "
                f"block={block_values}, "
                f"par={paragraph_values}, "
                f"line={line_values}, "
                f"local_bounds=("
                f"{line_left}, "
                f"{line_top}, "
                f"{line_right - line_left}, "
                f"{line_bottom - line_top}), "
                f"{confidence_text}, "
                f"text={line_text[:300]}"
            )

        return all_lines

    @staticmethod
    def _bounds_intersect(
        first_bounds,
        second_bounds,
    ):
        """
        Return True when two desktop-coordinate rectangles
        have a positive-area intersection.

        Bounds format:

            (left, top, width, height)
        """

        first_left, first_top, first_width, first_height = (
            first_bounds
        )

        second_left, second_top, second_width, second_height = (
            second_bounds
        )

        first_right = (
            first_left
            + first_width
        )

        first_bottom = (
            first_top
            + first_height
        )

        second_right = (
            second_left
            + second_width
        )

        second_bottom = (
            second_top
            + second_height
        )

        return (
            first_left < second_right
            and first_right > second_left
            and first_top < second_bottom
            and first_bottom > second_top
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
        """

        logger.info(
            self.MODULE,
            "Capturing desktop snapshot."
        )

        start = time.perf_counter()

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
        # Expand region for OCR context.
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
            f"{context_width}, {context_height}). "
            "Original change region retained as "
            "TranslationMap commit boundary."
        )

        # --------------------------------------------------
        # Convert to unified desktop-image coordinates.
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
        # Crop from existing desktop image.
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
        # Process expanded OCR context.
        # --------------------------------------------------

        result = self.process_image(
            region_image,
            origin_left=context_left,
            origin_top=context_top,
            commit_bounds=bounds,
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
        commit_bounds=None,
    ):
        """
        Process an image through the positional OCR,
        Translation and History pipeline.
        """

        # ----------------------------------------------
        # Validate optional commit boundary
        # ----------------------------------------------

        if commit_bounds is not None:

            if (
                not isinstance(
                    commit_bounds,
                    (tuple, list),
                )
                or len(commit_bounds) != 4
            ):
                raise ValueError(
                    "commit_bounds must contain "
                    "(left, top, width, height)."
                )

            commit_left = commit_bounds[0]
            commit_top = commit_bounds[1]
            commit_width = commit_bounds[2]
            commit_height = commit_bounds[3]

            if commit_width <= 0:
                raise ValueError(
                    "commit_bounds width must be "
                    "greater than zero."
                )

            if commit_height <= 0:
                raise ValueError(
                    "commit_bounds height must be "
                    "greater than zero."
                )

            logger.info(
                self.MODULE,
                "Live translation commit boundary: "
                f"({commit_left}, {commit_top}, "
                f"{commit_width}, {commit_height})."
            )

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

        try:
            debug_dir = Path("debug")
            debug_dir.mkdir(
                parents=True,
                exist_ok=True,
            )

            debug_image_path = (
                debug_dir
                / "ocr_input_latest.png"
            )

            image.save(
                debug_image_path,
                format="PNG",
            )

            logger.info(
                self.MODULE,
                "OCR input image saved: "
                f"{debug_image_path} "
                f"({image.width}x{image.height}, "
                f"mode={image.mode}, "
                f"origin=({origin_left}, {origin_top}))."
            )

        except Exception as exc:
            logger.warning(
                self.MODULE,
                "Unable to save OCR input debug image: "
                f"{exc}"
            )

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
        # Group OCR words into visual text lines
        # ----------------------------------------------

        logger.info(
            self.MODULE,
            "Grouping OCR items into visual text lines."
        )

        visual_lines = (
            self._group_ocr_items_into_lines(
                ocr_data
            )
        )

        logger.info(
            self.MODULE,
            "OCR visual line grouping completed: "
            f"{len(visual_lines)} line(s)."
        )

        # ----------------------------------------------
        # Prepare translation jobs
        # ----------------------------------------------

        translation_jobs = []

        filtered_context_lines = 0

        for line_index, line_items in enumerate(
            visual_lines,
            start=1,
        ):

            if not line_items:
                continue

            line_items.sort(
                key=lambda item: item.get(
                    "left",
                    0,
                )
            )

            line_text = self._build_line_text(
                line_items
            )

            if not line_text:
                continue

            # ------------------------------------------
            # Calculate image-local bounding rectangle.
            # ------------------------------------------

            local_left = min(
                item["left"]
                for item in line_items
            )

            local_top = min(
                item["top"]
                for item in line_items
            )

            local_right = max(
                item["left"]
                + item["width"]
                for item in line_items
            )

            local_bottom = max(
                item["top"]
                + item["height"]
                for item in line_items
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

            job_bounds = (
                desktop_left,
                desktop_top,
                desktop_width,
                desktop_height,
            )

            # ------------------------------------------
            # Live Mode commit boundary
            # ------------------------------------------

            if (
                commit_bounds is not None
                and not self._bounds_intersect(
                    job_bounds,
                    commit_bounds,
                )
            ):
                filtered_context_lines += 1

                logger.info(
                    self.MODULE,
                    "Skipping OCR visual line outside "
                    "Live translation commit boundary: "
                    f"bounds={job_bounds}, "
                    f"commit_bounds={commit_bounds}, "
                    f"text={line_text[:100]}"
                )

                continue

            line_confidence = (
                self._get_line_confidence_summary(
                    line_items
                )
            )

            translation_jobs.append(
                {
                    "line_text": line_text,
                    "bounds": job_bounds,
                    "confidence": line_confidence,
                }
            )

        if commit_bounds is not None:
            logger.info(
                self.MODULE,
                "Live OCR context filtering completed: "
                f"{len(translation_jobs)} line(s) retained, "
                f"{filtered_context_lines} surrounding "
                "context line(s) excluded."
            )

        # Keep translation order deterministic.
        translation_jobs.sort(
            key=lambda job: (
                job["bounds"][1],
                job["bounds"][0],
            )
        )

        # ----------------------------------------------
        # Translation-context diagnostic
        #
        # IMPORTANT:
        #
        # This does NOT change translation_jobs.
        # It only identifies likely physical-line
        # continuation relationships for analysis.
        # ----------------------------------------------

        cls = type(self)

        cls._diagnose_translation_context_groups(
            translation_jobs
        )

        # ----------------------------------------------
        # DIAGNOSTIC ONLY
        #
        # Log the exact translation units produced by the
        # current pipeline immediately before NLLB/provider
        # translation.
        #
        # Confidence is diagnostic only and currently has
        # NO effect on whether a unit is translated.
        # ----------------------------------------------

        logger.info(
            self.MODULE,
            "CURRENT TRANSLATION UNITS: "
            f"{len(translation_jobs)}"
        )

        for index, job in enumerate(
            translation_jobs,
            start=1,
        ):

            confidence = job["confidence"]

            if confidence["average"] is None:

                confidence_text = (
                    "confidence_avg=N/A, "
                    "confidence_min=N/A, "
                    "confidence_max=N/A, "
                    "below50=0, "
                    "below70=0"
                )

            else:

                confidence_text = (
                    "confidence_avg="
                    f"{confidence['average']:.1f}, "
                    "confidence_min="
                    f"{confidence['minimum']:.1f}, "
                    "confidence_max="
                    f"{confidence['maximum']:.1f}, "
                    "below50="
                    f"{confidence['below_50']}, "
                    "below70="
                    f"{confidence['below_70']}"
                )

            logger.info(
                self.MODULE,
                "TRANSLATION UNIT "
                f"[{index:03d}] "
                f"bounds={job['bounds']}, "
                f"{confidence_text}, "
                f"text={job['line_text'][:300]}"
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
            f"{len(translation_jobs)} visual text line(s)."
        )

        translation_start = time.perf_counter()

        translation_texts = [
            job["line_text"]
            for job in translation_jobs
        ]

        logger.info(
            self.MODULE,
            "Submitting "
            f"{len(translation_texts)} visual text line(s) "
            "to the batch translation engine."
        )

        translated_texts = translate_text_batch(
            translation_texts,
            source_language,
            target_language,
        )

        # --------------------------------------------------
        # Reconnect translated text with original position.
        # --------------------------------------------------

        if len(translated_texts) != len(
            translation_jobs
        ):
            logger.error(
                self.MODULE,
                "Batch translation returned an unexpected "
                "number of results: "
                f"expected={len(translation_jobs)}, "
                f"received={len(translated_texts)}."
            )

            translated_texts = list(
                translated_texts[:len(translation_jobs)]
            )

            while len(translated_texts) < len(
                translation_jobs
            ):
                translated_texts.append("")

        for job, translated_text in zip(
            translation_jobs,
            translated_texts,
        ):

            if translated_text is None:
                translated_text = ""

            translated_text = str(
                translated_text
            ).strip()

            translated_entries.append(
                {
                    "bounds": job["bounds"],
                    "original": job["line_text"],
                    "translation": translated_text,
                }
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