from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
import threading

from logger import logger
from core.capture_engine import get_desktop_bounds
from core.change_filter import ChangeFilter
from core.capture_engine import DesktopChangeRegion
from core.ui_filter import UIFilter
from core.translation_map_debug import TranslationMapDebugRenderer


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
        - UI structural filtering is applied to dirty
          region metadata before ChangeFilter
        - ChangeFilter compares each complete frame with
          the previous complete frame
        - the newest filtered dirty-region set replaces
          older pending dirty-region sets
        - regions within that newest state are coalesced
        - historical dirty regions are NOT accumulated
        - a newer desktop generation does not automatically
          invalidate an existing result
        - only a change overlapping an individual OCR result
          makes that result stale
        - unaffected OCR results from the completed batch
          remain eligible for TranslationMap commit
        - remaining regions from an older generation are
          abandoned when a newer generation is waiting

    The first complete desktop acquisition is special:

        - it establishes the ChangeFilter baseline
        - it is also OCR processed once across the complete
          virtual desktop
        - its translated entries populate the TranslationMap

    After that initial bootstrap, Live Mode becomes
    incremental and processes only meaningful changed regions.
    """

    MODULE = "ControllerLive"

    # --------------------------------------------------
    # Live processing tuning
    # --------------------------------------------------

    LIVE_SETTLE_DELAY = 0.20

    INITIAL_FULL_DESKTOP_OCR = True

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
        # Layer 2 structural desktop UI filter.
        #
        # This operates only on DXGI dirty-region metadata.
        # The complete desktop image remains untouched.
        #

        self._ui_filter = UIFilter()

        #
        # Layer 3 pixel-difference / text-change filter.
        #

        self._change_filter = ChangeFilter()

        #
        # Debug renderer for visualizing the TranslationMap
        # over the complete desktop image.
        #

        self._translation_map_debug_renderer = (
            TranslationMapDebugRenderer()
        )

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

        The complete acquisition image remains untouched.

        Dirty-region metadata flows through:

            Layer 2 UIFilter
                    ↓
            ChangeFilter

        before Live OCR work is queued.

        Dirty regions are NOT accumulated across multiple
        desktop acquisitions.

        The first complete desktop acquisition is also queued
        as one full-desktop OCR region so that the TranslationMap
        is initially populated across the entire virtual desktop.
        """

        if not self.running:
            return

        if not desktop_state:
            return

        desktop_image = desktop_state.get(
            "image"
        )

        dxgi_dirty_regions = desktop_state.get(
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

        # --------------------------------------------------
        # Layer 2 - structural UI filtering
        # --------------------------------------------------

        try:

            ui_filtered_regions = (
                self._ui_filter.filter_dirty_regions(
                    dxgi_dirty_regions
                )
            )

        except Exception as error:

            logger.error(
                self.MODULE,
                "UIFilter failed: "
                f"{error}"
            )

            return

        logger.info(
            self.MODULE,
            "Layer 2 UI filtering "
            f"retained {len(ui_filtered_regions)} "
            f"of {len(dxgi_dirty_regions)} "
            "DXGI dirty region(s)."
        )

        # --------------------------------------------------
        # ChangeFilter
        # --------------------------------------------------

        try:

            filtered_regions = (
                self._change_filter.filter_regions(
                    desktop_image=desktop_image,
                    dirty_regions=ui_filtered_regions,
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

            if self.INITIAL_FULL_DESKTOP_OCR:

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
                    desktop_width <= 0
                    or desktop_height <= 0
                ):

                    logger.warning(
                        self.MODULE,
                        "Initial full-desktop OCR skipped "
                        "because virtual desktop bounds are "
                        f"invalid: "
                        f"{(desktop_left, desktop_top, desktop_width, desktop_height)}"
                    )

                    return

                initial_region = DesktopChangeRegion(
                    left=desktop_left,
                    top=desktop_top,
                    right=desktop_right,
                    bottom=desktop_bottom,
                )

                with self._pending_lock:

                    self._generation += 1

                    generation = self._generation

                    self._pending_desktop_state = (
                        desktop_state
                    )

                    self._pending_dirty_regions = [
                        initial_region
                    ]

                logger.info(
                    self.MODULE,
                    "Initial desktop acquisition received. "
                    "ChangeFilter baseline established. "
                    "Queuing COMPLETE virtual desktop for "
                    "initial OCR/translation: "
                    f"bounds={initial_region.bounds}, "
                    f"generation={generation}."
                )

                self._work_event.set()

                return

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

        if move_regions:

            try:

                self._apply_move_regions(move_regions)

            except Exception as error:

                logger.error(
                    self.MODULE,
                    f"Failed to apply move regions: {error}"
                )

        if not filtered_regions:

            if dxgi_dirty_regions:

                logger.info(
                    self.MODULE,
                    "ChangeFilter found no meaningful pixel "
                    "change inside "
                    f"{len(ui_filtered_regions)} "
                    "Layer 2 retained DXGI dirty region(s) "
                    "from "
                    f"{len(dxgi_dirty_regions)} "
                    "original dirty region(s). "
                    "OCR work skipped."
                )

            elif move_regions:

                logger.info(
                    self.MODULE,
                    "Desktop move region(s) applied via "
                    "TranslationMap repositioning; no OCR "
                    "region queued."
                )

            return

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
    # MOVE REGION HANDLING
    # --------------------------------------------------

    def _apply_move_regions(self, move_regions):
        """
        Reposition existing TranslationMap entries for
        scroll/window-move regions, without waiting for OCR.
        """

        for move_region in move_regions:

            dest_left = move_region.destination_left
            dest_top = move_region.destination_top
            dest_right = move_region.destination_right
            dest_bottom = move_region.destination_bottom

            source_x = move_region.source_x
            source_y = move_region.source_y

            dx = dest_left - source_x
            dy = dest_top - source_y

            if dx == 0 and dy == 0:
                continue

            dest_width = dest_right - dest_left
            dest_height = dest_bottom - dest_top

            if dest_width <= 0 or dest_height <= 0:

                logger.warning(
                    self.MODULE,
                    "Skipping invalid move region: "
                    f"destination=({dest_left}, {dest_top}, "
                    f"{dest_right}, {dest_bottom})"
                )

                continue

            source_bounds = (
                source_x,
                source_y,
                dest_width,
                dest_height,
            )

            moved_count = (
                self.controller.translation_map.move_entries_in_region(
                    source_bounds,
                    dx,
                    dy,
                )
            )

            logger.info(
                self.MODULE,
                f"Repositioned {moved_count} TranslationMap "
                f"entr{'y' if moved_count == 1 else 'ies'} "
                f"by (dx={dx}, dy={dy}) for move region "
                f"source={source_bounds}, "
                f"dest=({dest_left}, {dest_top}, {dest_right}, {dest_bottom})."
            )

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

            #
            # Incremental Live OCR/translation is allowed only
            # after the latest meaningful desktop generation has
            # remained unchanged for at least three seconds.
            # The initial full-desktop bootstrap is intentionally
            # excluded from this stability gate.
            #

            is_initial_full_desktop = False

            try:

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

                if len(dirty_regions) == 1:

                    initial_region = dirty_regions[0]

                    is_initial_full_desktop = (
                        initial_region.left == desktop_left
                        and initial_region.top == desktop_top
                        and initial_region.right == desktop_right
                        and initial_region.bottom == desktop_bottom
                    )

            except Exception:

                is_initial_full_desktop = False

            if not is_initial_full_desktop:

                while True:

                    if self._stop_event.wait(3.0):
                        break

                    if self._stop_event.is_set():
                        break

                    with self._pending_lock:
                        latest_generation = self._generation

                    if latest_generation == generation:
                        break

                    logger.info(
                        self.MODULE,
                        "Live generation "
                        f"{generation} changed during the "
                        "3-second stability window. "
                        "Waiting for the newest generation to "
                        "remain stable before OCR/translation."
                    )

                    latest_pending = self._get_pending_work()

                    if latest_pending is None:
                        continue

                    (
                        desktop_state,
                        dirty_regions,
                        generation,
                    ) = latest_pending

                    if not desktop_state:
                        break

                    if not dirty_regions:
                        break

                if self._stop_event.is_set():
                    break

                with self._pending_lock:
                    if self._generation != generation:
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

        This check is intentionally used only between
        dirty regions. A newer generation does not by itself
        invalidate the completed results of a region that
        has already been processed.
        """

        with self._pending_lock:

            return self._generation > generation

    def _get_newer_pending_regions(self):
        """
        Return a snapshot of the currently pending filtered
        dirty regions.

        The caller uses these regions to determine which
        individual OCR entries from a completed batch were
        affected by newer desktop changes.
        """

        with self._pending_lock:

            return list(
                self._pending_dirty_regions
            )

    def _entry_overlaps_pending_change(
        self,
        entry_bounds,
        pending_regions,
    ):
        """
        Return True when an individual OCR result entry
        overlaps or touches any newer pending dirty region.

        Bounds formats:

            entry_bounds:
                (left, top, width, height)

            pending region:
                DesktopChangeRegion
        """

        if not pending_regions:
            return False

        entry_left = entry_bounds[0]
        entry_top = entry_bounds[1]

        entry_right = (
            entry_left
            + entry_bounds[2]
        )

        entry_bottom = (
            entry_top
            + entry_bounds[3]
        )

        entry_rectangle = (
            entry_left,
            entry_top,
            entry_right,
            entry_bottom,
        )

        for pending_region in pending_regions:

            pending_rectangle = (
                pending_region.left,
                pending_region.top,
                pending_region.right,
                pending_region.bottom,
            )

            if self._regions_touch_or_overlap(
                entry_rectangle,
                pending_rectangle,
            ):

                return True

        return False

    # --------------------------------------------------
    # DESKTOP REGION HELPERS
    # --------------------------------------------------

    @staticmethod
    def _bounds_intersect(
        first_bounds,
        second_bounds,
    ):
        """
        Return True when two TranslationMap-style bounds
        rectangles have a positive-area intersection.

        Bounds format:

            (left, top, width, height)

        This helper is diagnostic only. It does not modify
        TranslationMap state.
        """

        first_left = first_bounds[0]
        first_top = first_bounds[1]
        first_right = (
            first_left + first_bounds[2]
        )
        first_bottom = (
            first_top + first_bounds[3]
        )

        second_left = second_bounds[0]
        second_top = second_bounds[1]
        second_right = (
            second_left + second_bounds[2]
        )
        second_bottom = (
            second_top + second_bounds[3]
        )

        return (
            first_left < second_right
            and second_left < first_right
            and first_top < second_bottom
            and second_top < first_bottom
        )

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

        Dirty regions normally have already passed through:

            Layer 2 UIFilter
            Layer 3 ChangeFilter

        The initial Live bootstrap is different:

            Complete desktop
                ↓
            ControllerImagePipeline
                ↓
            Positional OCR
                ↓
            Translation
                ↓
            TranslationMap

        The Live region is handed to the shared
        ControllerImagePipeline, which performs the crop from
        the already captured unified desktop image and then
        runs positional OCR and translation.

        No additional desktop capture is performed here.

        A completed OCR/translation result is discarded only
        when:

            1. Live Mode has stopped, or
            2. an individual returned OCR entry overlaps a
               newer pending dirty region.

        This allows unaffected entries from the same completed
        OCR batch to be retained.
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

            #
            # IMPORTANT:
            #
            # The initial full-desktop bootstrap is not a
            # ChangeFilter dirty region. It is the complete
            # desktop baseline used to populate the initial
            # TranslationMap.
            #
            # Therefore it must not be discarded merely because
            # another normal desktop generation arrived while
            # the initial OCR was running.
            #

            is_initial_full_desktop_region = (
                left == desktop_left
                and top == desktop_top
                and right == desktop_right
                and bottom == desktop_bottom
            )

            if result_status != "success":

                logger.info(
                    self.MODULE,
                    "Live pipeline did not return a successful "
                    f"result for region {dirty_region.bounds}: "
                    f"status={result_status}."
                )

                continue

            entries = result_entries

            if not self._is_processing_allowed():

                logger.info(
                    self.MODULE,
                    "Skipping TranslationMap commit because "
                    "Live Mode stopped."
                )

                return

            # --------------------------------------------------
            # Determine which completed OCR entries are still
            # valid against newer pending desktop changes.
            # --------------------------------------------------

            committable_entries = list(
                entries
            )

            if not is_initial_full_desktop_region:

                pending_regions = (
                    self._get_newer_pending_regions()
                )

                if pending_regions:

                    filtered_entries = []

                    affected_count = 0

                    for entry in entries:

                        entry_bounds = entry.get(
                            "bounds"
                        )

                        if not entry_bounds:

                            filtered_entries.append(
                                entry
                            )

                            continue

                        if self._entry_overlaps_pending_change(
                            entry_bounds,
                            pending_regions,
                        ):

                            affected_count += 1

                            logger.info(
                                self.MODULE,
                                "Excluding completed OCR entry "
                                "from TranslationMap commit because "
                                "it overlaps a newer pending "
                                "desktop change: "
                                f"bounds={entry_bounds}, "
                                f"original="
                                f"{entry.get('original', '')[:120]!r}"
                            )

                            continue

                        filtered_entries.append(
                            entry
                        )

                    committable_entries = (
                        filtered_entries
                    )

                    logger.info(
                        self.MODULE,
                        "Live result reconciliation: "
                        f"original_entries={len(entries)}, "
                        f"affected_entries={affected_count}, "
                        f"committable_entries="
                        f"{len(committable_entries)}, "
                        f"pending_regions={len(pending_regions)}."
                    )

            # --------------------------------------------------
            # IMPORTANT: Final validity check BEFORE any
            # TranslationMap removal.
            #
            # A newer pending desktop change can arrive after
            # the first reconciliation above. If that makes all
            # completed OCR entries stale, leave the existing
            # TranslationMap untouched.
            # --------------------------------------------------

            if not is_initial_full_desktop_region:

                latest_pending_regions = (
                    self._get_newer_pending_regions()
                )

                if latest_pending_regions:

                    final_entries = []

                    final_excluded_count = 0

                    for entry in committable_entries:

                        entry_bounds = entry.get(
                            "bounds"
                        )

                        if not entry_bounds:

                            final_entries.append(
                                entry
                            )

                            continue

                        if self._entry_overlaps_pending_change(
                            entry_bounds,
                            latest_pending_regions,
                        ):

                            final_excluded_count += 1

                            logger.info(
                                self.MODULE,
                                "Final pre-removal validation "
                                "excluded OCR entry because it now "
                                "overlaps a newer pending desktop "
                                "change: "
                                f"bounds={entry_bounds}, "
                                f"original="
                                f"{entry.get('original', '')[:120]!r}"
                            )

                            continue

                        final_entries.append(
                            entry
                        )

                    if final_excluded_count:

                        logger.info(
                            self.MODULE,
                            "Final pre-removal Live result "
                            "reconciliation: "
                            f"excluded={final_excluded_count}, "
                            f"remaining={len(final_entries)}."
                        )

                    committable_entries = final_entries

            if not committable_entries:

                logger.info(
                    self.MODULE,
                    "Skipping TranslationMap commit because "
                    "all completed OCR entries became affected "
                    "by newer pending desktop changes. "
                    "Existing TranslationMap entries were left "
                    "untouched."
                )

                continue

            # --------------------------------------------------
            # Initial full-desktop TranslationMap population
            # --------------------------------------------------

            if is_initial_full_desktop_region:

                logger.info(
                    self.MODULE,
                    "Initial full-desktop OCR completed. "
                    "Populating TranslationMap with "
                    f"{len(committable_entries)} positional entr"
                    f"{'y' if len(committable_entries) == 1 else 'ies'}."
                )

                self.controller.translation_map.clear()

            else:

                # --------------------------------------------------
                # DIAGNOSTIC ONLY
                # --------------------------------------------------
                #
                # Before changing the TranslationMap, inspect the
                # entries that currently occupy the dirty region.
                #
                # This does NOT change application behavior.
                # It is intended to determine whether the returned
                # OCR entries overlap existing map entries before
                # those entries are removed.
                # --------------------------------------------------

                translation_map = (
                    self.controller.translation_map
                )

                existing_entries = (
                    translation_map.get_entries()
                )

                existing_in_region = []

                for existing_entry in existing_entries:

                    if self._bounds_intersect(
                        existing_entry.bounds,
                        dirty_region.bounds,
                    ):

                        existing_in_region.append(
                            existing_entry
                        )

                logger.info(
                    self.MODULE,
                    "TranslationMap diagnostic BEFORE removal: "
                    f"generation={generation}, "
                    f"dirty_region={dirty_region.bounds}, "
                    f"total_map_entries={len(existing_entries)}, "
                    f"entries_intersecting_dirty_region="
                    f"{len(existing_in_region)}."
                )

                for index, existing_entry in enumerate(
                    existing_in_region,
                    start=1,
                ):

                    logger.info(
                        self.MODULE,
                        "TranslationMap existing entry "
                        f"[{index}] before removal: "
                        f"id={existing_entry.id}, "
                        f"bounds={existing_entry.bounds}, "
                        f"state={existing_entry.state.value}, "
                        f"original={existing_entry.original[:120]!r}, "
                        f"translation="
                        f"{existing_entry.translation[:120]!r}"
                    )

                # --------------------------------------------------
                # Diagnostic comparison:
                #
                # Compare every newly returned OCR entry against
                # every existing TranslationMap entry BEFORE the
                # existing entries are removed.
                #
                # This tells us whether the incoming OCR result is
                # spatially overlapping an existing translation.
                # --------------------------------------------------

                for index, new_entry in enumerate(
                    committable_entries,
                    start=1,
                ):

                    overlapping_existing = []

                    for existing_entry in existing_entries:

                        if self._bounds_intersect(
                            new_entry["bounds"],
                            existing_entry.bounds,
                        ):

                            overlapping_existing.append(
                                existing_entry
                            )

                    logger.info(
                        self.MODULE,
                        "TranslationMap incoming entry "
                        f"[{index}] BEFORE removal: "
                        f"bounds={new_entry['bounds']}, "
                        f"original={new_entry['original'][:120]!r}, "
                        f"translation="
                        f"{new_entry['translation'][:120]!r}, "
                        f"overlapping_existing="
                        f"{len(overlapping_existing)}."
                    )

                    for overlap_index, existing_entry in enumerate(
                        overlapping_existing,
                        start=1,
                    ):

                        logger.info(
                            self.MODULE,
                            "TranslationMap overlap detail "
                            f"incoming[{index}] -> "
                            f"existing[{overlap_index}]: "
                            f"id={existing_entry.id}, "
                            f"existing_bounds="
                            f"{existing_entry.bounds}, "
                            f"existing_original="
                            f"{existing_entry.original[:120]!r}"
                        )

                # --------------------------------------------------
                # Existing behavior begins here.
                # --------------------------------------------------

                logger.info(
                    self.MODULE,
                    "TranslationMap diagnostic removal starting: "
                    f"dirty_region={dirty_region.bounds}, "
                    f"map_entries_before="
                    f"{translation_map.entry_count()}."
                )

                self.controller.translation_map.remove_entries_in_region(
                    dirty_region.bounds
                )

                logger.info(
                    self.MODULE,
                    "TranslationMap diagnostic removal completed: "
                    f"dirty_region={dirty_region.bounds}, "
                    f"map_entries_after="
                    f"{translation_map.entry_count()}."
                )

            # --------------------------------------------------
            # Add positional TranslationMap entries
            # --------------------------------------------------

            for entry in committable_entries:

                self.controller.translation_map.add_entry(
                    entry["bounds"],
                    entry["original"],
                    entry["translation"],
                )

            logger.info(
                self.MODULE,
                "TranslationMap updated successfully "
                f"with {len(committable_entries)} entr"
                f"{'y' if len(committable_entries) == 1 else 'ies'} "
                f"for generation {generation}. "
                f"Pipeline_entries={len(entries)}, "
                f"committable_entries={len(committable_entries)}."
            )

            # --------------------------------------------------
            # Diagnostic post-commit map state
            # --------------------------------------------------

            if not is_initial_full_desktop_region:

                logger.info(
                    self.MODULE,
                    "TranslationMap diagnostic AFTER insertion: "
                    f"generation={generation}, "
                    f"map_entries="
                    f"{self.controller.translation_map.entry_count()}."
                )

                #
                # Check whether duplicate/overlapping entries
                # now exist in the affected area.
                #
                # This is diagnostic only and does not modify
                # the TranslationMap.
                #

                affected_entries = []

                for map_entry in (
                    self.controller.translation_map.get_entries()
                ):

                    if self._bounds_intersect(
                        map_entry.bounds,
                        dirty_region.bounds,
                    ):

                        affected_entries.append(
                            map_entry
                        )

                logger.info(
                    self.MODULE,
                    "TranslationMap diagnostic affected-region "
                    "state: "
                    f"dirty_region={dirty_region.bounds}, "
                    f"entries_intersecting_region="
                    f"{len(affected_entries)}."
                )

                for index, affected_entry in enumerate(
                    affected_entries,
                    start=1,
                ):

                    logger.info(
                        self.MODULE,
                        "TranslationMap affected entry "
                        f"[{index}] after insertion: "
                        f"id={affected_entry.id}, "
                        f"bounds={affected_entry.bounds}, "
                        f"original={affected_entry.original[:120]!r}, "
                        f"translation="
                        f"{affected_entry.translation[:120]!r}"
                    )

            # --------------------------------------------------
            # Debug TranslationMap snapshot
            # --------------------------------------------------
            #
            # Render the SAME complete desktop image used by
            # this Live generation together with the current
            # TranslationMap.
            #
            # This is diagnostic only. It does not participate
            # in the Live processing pipeline or Floating Lens.
            #

            try:

                debug_path = (
                    self._translation_map_debug_renderer.render(
                        desktop_image,
                        self.controller.translation_map,
                    )
                )

                logger.info(
                    self.MODULE,
                    "TranslationMap debug snapshot "
                    f"written to: {debug_path}"
                )

            except Exception as error:

                logger.warning(
                    self.MODULE,
                    "TranslationMap debug snapshot failed: "
                    f"{error}"
                )