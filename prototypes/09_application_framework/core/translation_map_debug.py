"""
core/translation_map_debug.py

Debug renderer for the LingoLens TranslationMap.

This module creates a visual snapshot of the complete virtual
desktop with TranslationMap entries overlaid.

The renderer is intentionally separate from TranslationMap so
the TranslationMap remains a pure data model.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


class TranslationMapDebugRenderer:
    """Render a visual debug snapshot of the TranslationMap."""

    DEFAULT_OUTPUT = Path("debug") / "translation_map_debug.png"

    def render(
        self,
        desktop_image,
        translation_map,
        output_path=None,
    ):
        """
        Render TranslationMap entries over the complete desktop image.

        Returns
        -------
        Path
            Path to the generated PNG.
        """

        if desktop_image is None:
            raise ValueError("Desktop image cannot be None.")

        if translation_map is None:
            raise ValueError("TranslationMap cannot be None.")

        if output_path is None:
            output_path = self.DEFAULT_OUTPUT

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        image = desktop_image.convert("RGB").copy()
        draw = ImageDraw.Draw(image)

        desktop_left, desktop_top, _, _ = (
            translation_map.get_desktop_bounds()
        )

        entries = translation_map.get_entries()

        font = self._get_font(14)
        small_font = self._get_font(12)

        for index, entry in enumerate(entries, start=1):
            left, top, width, height = entry.bounds

            x1 = left - desktop_left
            y1 = top - desktop_top
            x2 = x1 + width
            y2 = y1 + height

            x1 = max(0, min(x1, image.width))
            y1 = max(0, min(y1, image.height))
            x2 = max(0, min(x2, image.width))
            y2 = max(0, min(y2, image.height))

            draw.rectangle(
                (x1, y1, x2, y2),
                outline="red",
                width=2,
            )

            original = str(entry.original or "").replace(
                "\n", " "
            ).strip()

            translation = str(entry.translation or "").replace(
                "\n", " "
            ).strip()

            label = (
                f"#{index} "
                f"{original[:80]} → {translation[:80]}"
            )

            draw.text(
                (x1, max(0, y1 - 20)),
                label,
                fill="red",
                font=font,
            )

            coordinate_text = (
                f"{left},{top} {width}x{height}"
            )

            draw.text(
                (x1, min(y2 + 2, image.height - 16)),
                coordinate_text,
                fill="red",
                font=small_font,
            )

        image.save(output_path, format="PNG")

        return output_path

    @staticmethod
    def _get_font(size):
        """Return a usable system font with a safe fallback."""

        for candidate in ("arial.ttf", "segoeui.ttf"):
            try:
                return ImageFont.truetype(candidate, size)
            except OSError:
                continue

        return ImageFont.load_default()