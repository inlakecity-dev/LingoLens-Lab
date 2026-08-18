"""
core/ui_filter.py

Layer 2 - Desktop UI Filter

Defines structural exclusion rules for desktop UI regions
that must never become OCR input.

Current responsibility
----------------------
- Detect the current Windows taskbar rectangles.
- Remove DXGI dirty regions that overlap the taskbar.

Important
---------
This layer operates on DXGI dirty-region boundaries.

It does NOT:

- perform OCR
- inspect text
- perform pixel-difference analysis
- classify text-like shapes
- filter LingoLens windows
- replace ChangeFilter
- crop desktop images
- update TranslationMap

The complete desktop image must still reach ChangeFilter so
its pixel-difference baseline remains synchronized.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes

from logger import logger


class UIFilter:
    """
    Layer 2 structural desktop UI filter.

    The filter removes known desktop UI regions before the
    regions are passed to ChangeFilter.

    Current structural exclusion:

        Windows Taskbar
    """

    MODULE = "UIFilter"

    def __init__(self):
        """
        Initialize the UI filter.
        """

        logger.info(
            self.MODULE,
            "UI filter initialized."
        )

    # --------------------------------------------------
    # PUBLIC API
    # --------------------------------------------------

    def filter_dirty_regions(
        self,
        dirty_regions,
    ):
        """
        Remove known unwanted desktop UI regions from the
        supplied DXGI dirty regions.

        Parameters
        ----------
        dirty_regions
            Iterable of DesktopChangeRegion objects.

        Returns
        -------
        list
            Dirty regions that are not excluded by Layer 2.
        """

        if not dirty_regions:
            return []

        taskbar_rects = self._get_taskbar_rects()

        if not taskbar_rects:

            logger.info(
                self.MODULE,
                "No taskbar rectangles detected. "
                "All DXGI dirty regions retained."
            )

            return list(dirty_regions)

        filtered_regions = []

        for region in dirty_regions:

            region_bounds = (
                region.left,
                region.top,
                region.right,
                region.bottom,
            )

            overlaps_taskbar = False

            for taskbar in taskbar_rects:

                if self._regions_overlap(
                    region_bounds,
                    taskbar,
                ):

                    overlaps_taskbar = True

                    logger.info(
                        self.MODULE,
                        "Ignoring DXGI dirty region "
                        f"{region.bounds} because it "
                        "overlaps taskbar "
                        f"{taskbar}."
                    )

                    break

            if not overlaps_taskbar:

                filtered_regions.append(
                    region
                )

        removed_count = (
            len(dirty_regions)
            - len(filtered_regions)
        )

        if removed_count:

            logger.info(
                self.MODULE,
                "Taskbar exclusion removed "
                f"{removed_count} dirty region(s) "
                "before ChangeFilter."
            )

        return filtered_regions

    # --------------------------------------------------
    # TASKBAR DETECTION
    # --------------------------------------------------

    @staticmethod
    def _get_taskbar_rects():
        """
        Return the current Windows taskbar rectangles.

        Coordinates use Windows virtual-desktop coordinates.

        The primary taskbar is reported by:

            Shell_TrayWnd

        Secondary-monitor taskbars use:

            Shell_SecondaryTrayWnd

        Geometry is queried for every filtering operation so
        taskbar auto-hide/reveal state does not depend on a
        stale cached rectangle.

        Returns
        -------
        list[tuple[int, int, int, int]]
            Taskbar rectangles in virtual-desktop coordinates.
        """

        user32 = ctypes.windll.user32

        class_names = (
            "Shell_TrayWnd",
            "Shell_SecondaryTrayWnd",
        )

        rects = []

        for class_name in class_names:

            hwnd = user32.FindWindowW(
                class_name,
                None,
            )

            while hwnd:

                rect = wintypes.RECT()

                if user32.GetWindowRect(
                    hwnd,
                    ctypes.byref(rect),
                ):

                    if (
                        rect.right > rect.left
                        and rect.bottom > rect.top
                    ):

                        bounds = (
                            rect.left,
                            rect.top,
                            rect.right,
                            rect.bottom,
                        )

                        if bounds not in rects:

                            rects.append(
                                bounds
                            )

                hwnd = user32.FindWindowExW(
                    None,
                    hwnd,
                    class_name,
                    None,
                )

        return rects

    # --------------------------------------------------
    # REGION GEOMETRY
    # --------------------------------------------------

    @staticmethod
    def _regions_overlap(
        first,
        second,
    ):
        """
        Return True when two rectangles overlap.

        Parameters
        ----------
        first
            (left, top, right, bottom)

        second
            (left, top, right, bottom)
        """

        return not (
            first[2] <= second[0]
            or second[2] <= first[0]
            or first[3] <= second[1]
            or second[3] <= first[1]
        )