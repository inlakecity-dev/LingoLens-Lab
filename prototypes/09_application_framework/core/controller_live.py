"""
core/controller_live.py

Controller Live Mode

Coordinates the Live Translation workflow.

## Responsibilities

- Start Live Mode.
- Stop Live Mode.
- Receive unified desktop acquisition state.
- Pass complete desktop frames through ChangeFilter.
- Retain the latest complete desktop image.
- Retain only the latest meaningful filtered dirty regions.
- Coalesce dirty regions within the latest desktop state.
- Prevent historical dirty regions from accumulating while
  OCR/translation is busy.
- Crop changed regions from the latest acquired desktop image.
- Discard stale processing results only when the processed
  region itself changed again.
- Update the TranslationMap.
- Exclude LingoLens-owned windows from desktop capture.

This class does NOT:

- Perform OCR
- Perform Translation
- Capture desktop regions directly
- Own the TranslationMap
- Own the DesktopObserver
- Perform pixel-difference analysis directly
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
import threading

from logger import logger
from core.capture_engine import get_desktop_bounds
from core.change_filter import ChangeFilter
from core.capture_engine import DesktopChangeRegion


# --------------------------------------------------
# Win32 capture exclusion
# --------------------------------------------------

WDA_EXCLUDEFROMCAPTURE = 0x00000011


class ControllerLive:
    """
    Coordinates the Live Translation workflow.

    Live processing uses a single background worker.

    If desktop states arrive while OCR/translation is
    already running:

        - the newest complete desktop image is retained
        - ChangeFilter compares each complete frame with
          the previous complete frame
        - the newest filtered dirty-region set replaces
          older pending dirty-region sets
        - regions within that newest state are coalesced
        - historical dirty regions are NOT accumulated
        - a newer desktop generation does not automatically
          invalidate an existing result
        - only a change overlapping the region being processed
          makes that result stale
        - remaining regions from an older generation are
          abandoned when a newer generation is waiting
    """

    MODULE = "ControllerLive"

    # --------------------------------------------------
    # Live processing tuning
    # --------------------------------------------------

    LIVE_SETTLE_DELAY = 0.20

    IGNORE_INITIAL_FULL_DESKTOP_CHANGE = True

    MAX_COALESCED_DESKTOP_AREA_RATIO = 0.35

    MAX_COALESCED_WIDTH_RATIO = 0.75

    MAX_COALESCED_HEIGHT_RATIO = 0.75

    def __init__(self, controller):
        """
        Parameters
        ----------
        controller
            Shared application controller.
        """

        self.controller = controller

        # --------------------------------------------------
        # Live processing state
        # --------------------------------------------------

        self.running = False

        self._worker_thread = None

        self._work_event = threading.Event()

        self._stop_event = threading.Event()

        self._pending_lock = threading.Lock()

        #
        # Pixel-difference filter.
        #

        self._change_filter = ChangeFilter()

        #
        # Always retain the newest complete desktop state.
        #

        self._pending_desktop_state = None

        #
        # Only filtered regions from the newest pending
        # desktop state are retained.
        #

        self._pending_dirty_regions = []

        #
        # Used only for the first desktop state of a Live
        # session.
        #

        self._initial_state_received = False

        #
        # Diagnostic/work sequence number.
        #

        self._generation = 0

        logger.info(
            self.MODULE,
            "Controller live service initialized."
        )

    # --------------------------------------------------
    # LIVE MODE
    # --------------------------------------------------

    def start_live_mode(self):
        """
        Start Live Translation.

        Desktop observation and Live processing run in
        background threads so the application remains
        responsive.

        Only one Live processing worker is allowed.
        """

        if self.running:
            return

        logger.info(
            self.MODULE,
            "Starting Live Mode."
        )

        self.running = True

        self._stop_event.clear()
        self._work_event.clear()

        #
        # A new Live session must begin with a completely
        # fresh pixel-difference baseline.
        #

        self._change_filter.reset()

        with self._pending_lock:

            self._pending_desktop_state = None

            self._pending_dirty_regions = []

            self._initial_state_received = False

            self._generation += 1

        #
        # Exclude all LingoLens-owned windows from capture.
        #
        # This is applied at the Windows capture level before
        # DesktopObserver starts producing desktop states.
        #

        self._exclude_lingolense_windows_from_capture()

        self._worker_thread = threading.Thread(
            target=self._worker_loop,
            name="ControllerLiveWorker",
            daemon=True,
        )

        self._worker_thread.start()

        self.controller.desktop_observer.start()

    def stop_live_mode(self):
        """
        Stop Live Translation.

        The DesktopObserver is stopped first so no new
        desktop states are generated.

        The current OCR/translation operation cannot be
        forcibly interrupted. Its result will be ignored
        because Live Mode is no longer running.
        """

        if not self.running:
            return

        logger.info(
            self.MODULE,
            "Stopping Live Mode."
        )

        self.running = False

        #
        # Stop receiving new desktop changes first.
        #

        self.controller.desktop_observer.stop()

        #
        # Invalidate pending work.
        #

        with self._pending_lock:

            self._generation += 1

            self._pending_desktop_state = None

            self._pending_dirty_regions = []

        #
        # Reset the ChangeFilter baseline so the next
        # Live session starts cleanly.
        #

        self._change_filter.reset()

        #
        # Tell the worker to finish.
        #

        self._stop_event.set()

        self._work_event.set()

        worker_thread = self._worker_thread

        self._worker_thread = None

        if (
            worker_thread is not None
            and worker_thread is not threading.current_thread()
            and worker_thread.is_alive()
        ):

            logger.info(
                self.MODULE,
                "Live worker is finishing its current job."
            )

    # --------------------------------------------------
    # LINGOLENSE CAPTURE EXCLUSION
    # --------------------------------------------------

    @staticmethod
    def _get_window_metadata(hwnd):
        """
        Return diagnostic metadata for a Windows HWND.

        The metadata is used only for logging so that a
        capture-excluded HWND can be correlated with its
        visible screen location.

        Returns
        -------
        dict
            Window title, class name, and screen bounds.
        """

        user32 = ctypes.windll.user32

        title_buffer = ctypes.create_unicode_buffer(
            512
        )

        class_buffer = ctypes.create_unicode_buffer(
            256
        )

        try:

            user32.GetWindowTextW(
                hwnd,
                title_buffer,
                len(title_buffer),
            )

        except Exception:

            title_buffer.value = ""

        try:

            user32.GetClassNameW(
                hwnd,
                class_buffer,
                len(class_buffer),
            )

        except Exception:

            class_buffer.value = ""

        rect = wintypes.RECT()

        try:

            rect_result = user32.GetWindowRect(
                hwnd,
                ctypes.byref(rect),
            )

        except Exception:

            rect_result = 0

        if rect_result:

            bounds = (
                rect.left,
                rect.top,
                rect.right,
                rect.bottom,
            )

        else:

            bounds = None

        return {
            "title": title_buffer.value,
            "class_name": class_buffer.value,
            "bounds": bounds,
        }

    @staticmethod
    def _get_lingolense_windows():
        """
        Return top-level windows belonging to the current
        LingoLens process.

        The current process ID is used so only windows owned
        by LingoLens are considered.

        Returns
        -------
        list[int]
            Window handles belonging to this process.
        """

        user32 = ctypes.windll.user32

        current_process_id = os.getpid()

        windows = []

        enum_windows_proc = (
            ctypes.WINFUNCTYPE(
                wintypes.BOOL,
                wintypes.HWND,
                wintypes.LPARAM,
            )
        )

        def enum_window(
            hwnd,
            _lparam,
        ):

            if not user32.IsWindow(hwnd):
                return True

            process_id = wintypes.DWORD()

            user32.GetWindowThreadProcessId(
                hwnd,
                ctypes.byref(process_id),
            )

            if process_id.value != current_process_id:
                return True

            #
            # Only top-level windows are relevant here.
            #
            # Desktop duplication exclusion is applied to
            # actual window handles, not child controls.
            #

            owner = user32.GetWindow(
                hwnd,
                4,  # GW_OWNER
            )

            if owner:
                #
                # Owned dialogs are still LingoLens windows,
                # therefore retain them as capture exclusions.
                #
                pass

            windows.append(hwnd)

            return True

        callback = enum_windows_proc(
            enum_window
        )

        user32.EnumWindows(
            callback,
            0,
        )

        return windows

    @staticmethod
    def _exclude_lingolense_windows_from_capture():
        """
        Apply WDA_EXCLUDEFROMCAPTURE to all windows owned by
        the current LingoLens process.

        This prevents LingoLens's own visible UI from appearing
        in the desktop capture and therefore prevents its UI
        activity from becoming DXGI dirty-region input.

        The method intentionally operates at the Windows
        capture level rather than adding another ChangeFilter
        rule.

        Diagnostic information is logged for every HWND so that
        a leaked DXGI region can later be correlated with the
        corresponding LingoLens window.
        """

        user32 = ctypes.windll.user32

        windows = (
            ControllerLive._get_lingolense_windows()
        )

        if not windows:

            logger.warning(
                ControllerLive.MODULE,
                "No LingoLens windows found for "
                "capture exclusion."
            )

            return

        excluded_count = 0

        for hwnd in windows:

            try:

                metadata = (
                    ControllerLive._get_window_metadata(
                        hwnd
                    )
                )

                result = (
                    user32.SetWindowDisplayAffinity(
                        hwnd,
                        WDA_EXCLUDEFROMCAPTURE,
                    )
                )

                last_error = (
                    ctypes.get_last_error()
                )

                title = metadata["title"]

                class_name = (
                    metadata["class_name"]
                )

                bounds = metadata["bounds"]

                if result:

                    excluded_count += 1

                    logger.info(
                        ControllerLive.MODULE,
                        "LingoLens window excluded "
                        "from desktop capture: "
                        f"HWND={hwnd}, "
                        f"title={title!r}, "
                        f"class={class_name!r}, "
                        f"bounds={bounds}, "
                        f"attribute={WDA_EXCLUDEFROMCAPTURE}, "
                        f"result={result}, "
                        f"last_error={last_error}"
                    )

                else:

                    logger.warning(
                        ControllerLive.MODULE,
                        "Failed to exclude LingoLens "
                        "window from desktop capture: "
                        f"HWND={hwnd}, "
                        f"title={title!r}, "
                        f"class={class_name!r}, "
                        f"bounds={bounds}, "
                        f"attribute={WDA_EXCLUDEFROMCAPTURE}, "
                        f"result={result}, "
                        f"last_error={last_error}"
                    )

            except Exception as error:

                logger.warning(
                    ControllerLive.MODULE,
                    "Exception while excluding "
                    f"LingoLens window HWND={hwnd}: "
                    f"{error}"
                )

        logger.info(
            ControllerLive.MODULE,
            "LingoLens capture exclusion applied to "
            f"{excluded_count} window(s)."
        )

    # --------------------------------------------------
    # DESKTOP STATE
    # --------------------------------------------------

    def on_desktop_state_changed(
        self,
        desktop_state,
    ):
        """
        Receive a unified desktop acquisition from
        DesktopObserver.

        The complete acquisition is passed through
        ChangeFilter before Live OCR work is queued.

        Dirty regions are NOT accumulated across multiple
        desktop acquisitions.
        """

        if not self.running:
            return

        if not desktop_state:
            return

        desktop_image = desktop_state.get(
            "image"
        )

        dirty_regions = desktop_state.get(
            "dirty_regions",
            [],
        )

        move_regions = desktop_state.get(
            "move_regions",
            [],
        )

        if desktop_image is None:

            logger.warning(
                self.MODULE,
                "Received desktop state without an image."
            )

            return

        try:

            filtered_regions = (
                self._change_filter.filter_regions(
                    desktop_image=desktop_image,
                    dirty_regions=dirty_regions,
                    desktop_bounds=get_desktop_bounds(),
                )
            )

        except Exception as error:

            logger.error(
                self.MODULE,
                "ChangeFilter failed: "
                f"{error}"
            )

            return

        #
        # First desktop acquisition establishes the baseline.
        #

        with self._pending_lock:

            is_initial_state = (
                not self._initial_state_received
            )

            self._initial_state_received = True

        # --------------------------------------------------
        # Initial desktop state
        # --------------------------------------------------

        if is_initial_state:

            if self.IGNORE_INITIAL_FULL_DESKTOP_CHANGE:

                logger.info(
                    self.MODULE,
                    "Initial desktop acquisition received. "
                    "Using it as Live pixel-difference "
                    "baseline; initial OCR work is skipped."
                )

                return

        # --------------------------------------------------
        # No meaningful pixel change
        # --------------------------------------------------

        if not filtered_regions:

            if dirty_regions:

                logger.info(
                    self.MODULE,
                    "ChangeFilter found no meaningful pixel "
                    "change inside "
                    f"{len(dirty_regions)} "
                    "DXGI dirty region(s). "
                    "OCR work skipped."
                )

            elif move_regions:

                logger.info(
                    self.MODULE,
                    "Desktop move region(s) received, but "
                    "no dirty region produced OCR work."
                )

            return

        logger.info(
            self.MODULE,
            "Desktop state changed "
            f"({len(dirty_regions)} DXGI dirty region(s), "
            f"{len(filtered_regions)} filtered region(s), "
            f"{len(move_regions)} move region(s))."
        )

        # --------------------------------------------------
        # Diagnostic filtered-region logging
        # --------------------------------------------------

        for index, region in enumerate(
            filtered_regions,
            start=1,
        ):

            logger.info(
                self.MODULE,
                f"Filtered region [{index}] bounds: "
                f"{region.bounds}"
            )

        #
        # Coalesce only regions belonging to this newest
        # desktop acquisition.
        #

        coalesced_regions = (
            self._coalesce_dirty_regions(
                filtered_regions
            )
        )

        with self._pending_lock:

            self._generation += 1

            generation = self._generation

            self._pending_desktop_state = (
                desktop_state
            )

            self._pending_dirty_regions = (
                coalesced_regions
            )

            pending_region_count = len(
                self._pending_dirty_regions
            )

        logger.info(
            self.MODULE,
            "Live processing generation "
            f"{generation} queued with "
            f"{pending_region_count} coalesced region(s)."
        )

        self._work_event.set()

    # --------------------------------------------------
    # WORKER LOOP
    # --------------------------------------------------

    def _worker_loop(self):
        """
        Process Live Translation work sequentially.
        """

        logger.info(
            self.MODULE,
            "Live processing worker started."
        )

        while not self._stop_event.is_set():

            self._work_event.wait()

            self._work_event.clear()

            if self._stop_event.is_set():
                break

            self._stop_event.wait(
                self.LIVE_SETTLE_DELAY
            )

            if self._stop_event.is_set():
                break

            pending = self._get_pending_work()

            if pending is None:
                continue

            (
                desktop_state,
                dirty_regions,
                generation,
            ) = pending

            if not desktop_state:
                continue

            if not dirty_regions:
                continue

            try:

                self._process_desktop_state(
                    desktop_state,
                    dirty_regions,
                    generation,
                )

            except Exception as error:

                logger.error(
                    self.MODULE,
                    "Live processing failed: "
                    f"{error}"
                )

        logger.info(
            self.MODULE,
            "Live processing worker stopped."
        )

    # --------------------------------------------------
    # PENDING WORK
    # --------------------------------------------------

    def _get_pending_work(self):
        """
        Retrieve and clear the latest pending desktop work.
        """

        with self._pending_lock:

            desktop_state = (
                self._pending_desktop_state
            )

            dirty_regions = list(
                self._pending_dirty_regions
            )

            self._pending_desktop_state = None

            self._pending_dirty_regions = []

            generation = self._generation

        if not desktop_state:
            return None

        if not dirty_regions:
            return None

        return (
            desktop_state,
            dirty_regions,
            generation,
        )

    # --------------------------------------------------
    # PROCESSING VALIDITY
    # --------------------------------------------------

    def _is_processing_allowed(self):
        """
        Return True when Live Mode is still active.
        """

        if self._stop_event.is_set():
            return False

        if not self.running:
            return False

        return True

    def _has_newer_generation(
        self,
        generation,
    ):
        """
        Return True when a newer desktop generation has
        arrived while the supplied generation is being
        processed.
        """

        with self._pending_lock:

            return self._generation > generation

    def _has_region_changed_since_processing(
        self,
        region,
    ):
        """
        Return True when a newer desktop acquisition contains
        a filtered dirty region that overlaps or touches the
        region currently being processed.
        """

        if not self.running:
            return True

        if self._stop_event.is_set():
            return True

        with self._pending_lock:

            pending_regions = list(
                self._pending_dirty_regions
            )

        if not pending_regions:
            return False

        current = (
            region.left,
            region.top,
            region.right,
            region.bottom,
        )

        for pending_region in pending_regions:

            pending = (
                pending_region.left,
                pending_region.top,
                pending_region.right,
                pending_region.bottom,
            )

            if self._regions_touch_or_overlap(
                current,
                pending,
            ):

                return True

        return False

    # --------------------------------------------------
    # DESKTOP REGION HELPERS
    # --------------------------------------------------

    def _coalesce_dirty_regions(
        self,
        regions,
    ):
        """
        Merge overlapping or safely adjacent dirty regions.
        """

        if not regions:
            return []

        (
            desktop_left,
            desktop_top,
            desktop_width,
            desktop_height,
        ) = get_desktop_bounds()

        max_area = (
            desktop_width
            * desktop_height
            * self.MAX_COALESCED_DESKTOP_AREA_RATIO
        )

        max_width = (
            desktop_width
            * self.MAX_COALESCED_WIDTH_RATIO
        )

        max_height = (
            desktop_height
            * self.MAX_COALESCED_HEIGHT_RATIO
        )

        merged = []

        for region in regions:

            current = (
                region.left,
                region.top,
                region.right,
                region.bottom,
            )

            changed = True

            while changed:

                changed = False

                remaining = []

                for existing in merged:

                    existing_bounds = (
                        existing.left,
                        existing.top,
                        existing.right,
                        existing.bottom,
                    )

                    if not self._regions_touch_or_overlap(
                        current,
                        existing_bounds,
                    ):

                        remaining.append(
                            existing
                        )

                        continue

                    candidate = (
                        min(
                            current[0],
                            existing_bounds[0],
                        ),
                        min(
                            current[1],
                            existing_bounds[1],
                        ),
                        max(
                            current[2],
                            existing_bounds[2],
                        ),
                        max(
                            current[3],
                            existing_bounds[3],
                        ),
                    )

                    candidate_width = (
                        candidate[2]
                        - candidate[0]
                    )

                    candidate_height = (
                        candidate[3]
                        - candidate[1]
                    )

                    candidate_area = (
                        candidate_width
                        * candidate_height
                    )

                    if (
                        candidate_area > max_area
                        or candidate_width > max_width
                        or candidate_height > max_height
                    ):

                        remaining.append(
                            existing
                        )

                        continue

                    current = candidate

                    changed = True

                merged = remaining

            merged.append(
                DesktopChangeRegion(
                    left=current[0],
                    top=current[1],
                    right=current[2],
                    bottom=current[3],
                )
            )

        if len(regions) != len(merged):

            logger.info(
                self.MODULE,
                "Dirty-region coalescing reduced "
                f"{len(regions)} region(s) to "
                f"{len(merged)} bounded region(s)."
            )

        return merged

    @staticmethod
    def _regions_touch_or_overlap(
        first,
        second,
    ):
        """
        Return True when two rectangular regions overlap
        or touch each other.
        """

        return not (
            first[2] < second[0]
            or second[2] < first[0]
            or first[3] < second[1]
            or second[3] < first[1]
        )

    # --------------------------------------------------
    # LIVE PROCESSING
    # --------------------------------------------------

    def _process_desktop_state(
        self,
        desktop_state,
        dirty_regions,
        generation,
    ):
        """
        Process one unified desktop acquisition.

        Dirty regions have already passed through ChangeFilter.

        The Live region is handed to the shared
        ControllerImagePipeline, which performs the crop from
        the already captured unified desktop image and then
        runs positional OCR and translation.

        No additional desktop capture is performed here.

        A result is discarded only when:

            1. Live Mode has stopped, or
            2. the same/overlapping region changed again while
               OCR/translation was running.
        """

        desktop_image = desktop_state.get(
            "image"
        )

        if desktop_image is None:

            logger.warning(
                self.MODULE,
                "Live desktop state contains no image."
            )

            return

        if not dirty_regions:
            return

        for dirty_region in dirty_regions:

            if self._has_newer_generation(
                generation
            ):

                logger.info(
                    self.MODULE,
                    "Newer Live generation detected "
                    f"while processing generation "
                    f"{generation}. "
                    "Remaining regions from the older "
                    "generation will be skipped."
                )

                return

            if not self._is_processing_allowed():

                logger.info(
                    self.MODULE,
                    "Stopping Live processing before "
                    f"region processing "
                    f"(generation {generation})."
                )

                return

            left = dirty_region.left
            top = dirty_region.top
            right = dirty_region.right
            bottom = dirty_region.bottom

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

            if (
                left < desktop_left
                or top < desktop_top
                or right > desktop_right
                or bottom > desktop_bottom
                or right <= left
                or bottom <= top
            ):

                logger.warning(
                    self.MODULE,
                    "Skipping invalid dirty region: "
                    f"{dirty_region.bounds}"
                )

                continue

            region_width = (
                right - left
            )

            region_height = (
                bottom - top
            )

            logger.info(
                self.MODULE,
                "Processing filtered dirty region "
                f"({left}, {top}, "
                f"{region_width}, {region_height}) "
                "through ControllerImagePipeline."
            )

            #
            # ControllerImagePipeline.process_live_region()
            # performs the crop from the SAME unified desktop
            # image and preserves the absolute desktop origin
            # for positional OCR.
            #
            # No second desktop capture occurs here.
            #

            live_result = (
                self.controller.image_pipeline.process_live_region(
                    desktop_image,
                    (
                        left,
                        top,
                        region_width,
                        region_height,
                    ),
                )
            )

            result = live_result.get(
                "result",
                {},
            )

            result_status = result.get(
                "status",
                "missing",
            )

            result_entries = result.get(
                "entries",
                [],
            )

            logger.info(
                self.MODULE,
                "Live pipeline returned "
                f"status={result_status}, "
                f"entries={len(result_entries)}, "
                f"generation={generation}."
            )

            if not self._is_processing_allowed():

                logger.info(
                    self.MODULE,
                    "Discarding Live result because "
                    "Live Mode stopped."
                )

                return

            if self._has_region_changed_since_processing(
                dirty_region
            ):

                logger.info(
                    self.MODULE,
                    "Discarding stale Live result for "
                    f"region {dirty_region.bounds}: "
                    "the same/overlapping region changed "
                    "again during processing."
                )

                continue

            if result_status != "success":
                continue

            entries = result_entries

            if not self._is_processing_allowed():

                logger.info(
                    self.MODULE,
                    "Skipping TranslationMap commit because "
                    "Live Mode stopped."
                )

                return

            if self._has_region_changed_since_processing(
                dirty_region
            ):

                logger.info(
                    self.MODULE,
                    "Skipping TranslationMap commit for "
                    f"region {dirty_region.bounds}: "
                    "region changed before commit."
                )

                continue

            logger.info(
                self.MODULE,
                "Updating TranslationMap with "
                f"{len(entries)} positional entr"
                f"{'y' if len(entries) == 1 else 'ies'} "
                f"(generation {generation})."
            )

            self.controller.translation_map.remove_entries_in_region(
                dirty_region.bounds
            )

            for entry in entries:

                self.controller.translation_map.add_entry(
                    entry["bounds"],
                    entry["original"],
                    entry["translation"],
                )

            logger.info(
                self.MODULE,
                "TranslationMap updated successfully "
                f"with {len(entries)} entr"
                f"{'y' if len(entries) == 1 else 'ies'} "
                f"for generation {generation}."
            )