"""
core/desktop_observer.py

Observes the Windows desktop while Live Mode is active.

The native DesktopVisionEngine provides one unified desktop
acquisition containing:

    - complete desktop image
    - dirty regions
    - move regions

This observer retrieves that unified state and notifies the
Controller about desktop changes.

This class does NOT:

- Perform OCR.
- Perform Translation.
- Update the TranslationMap.
- Control the Floating Lens.
"""

import threading
import time

from core.capture_engine import capture_desktop_state

from logger import logger


class DesktopObserver:
    """
    Observes the Windows desktop.

    Responsibilities
    ----------------
    - Start desktop observation.
    - Stop desktop observation.
    - Poll DesktopVisionEngine for unified desktop state.
    - Notify the Controller when desktop changes occur.

    This class does NOT:
        - Perform OCR.
        - Perform Translation.
        - Update the TranslationMap.
        - Control the Floating Lens.
    """

    MODULE = "DESKTOP"

    # --------------------------------------------------
    # Polling configuration
    # --------------------------------------------------

    POLL_INTERVAL = 0.5

    def __init__(self, controller):
        """
        Initialize the Desktop Observer.

        Parameters
        ----------
        controller
            Application controller that receives
            unified desktop state notifications.
        """

        self.controller = controller

        self.running = False

        self._stop_event = threading.Event()

        self._poll_thread = None

        logger.info(
            self.MODULE,
            "DesktopObserver initialized."
        )

    # --------------------------------------------------
    # LIFECYCLE
    # --------------------------------------------------

    def start(self):
        """
        Start observing the desktop.

        A background polling thread is created so
        desktop observation does not block the Tkinter
        application thread.
        """

        if self.running:
            return

        self.running = True

        self._stop_event.clear()

        self._poll_thread = threading.Thread(
            target=self._poll_loop,
            name="DesktopObserver",
            daemon=True,
        )

        self._poll_thread.start()

        logger.info(
            self.MODULE,
            "DesktopObserver started."
        )

    def stop(self):
        """
        Stop observing the desktop.

        The stop event is signaled first so the polling
        thread will finish as soon as the current native
        desktop acquisition completes.
        """

        if not self.running:
            return

        logger.info(
            self.MODULE,
            "Stopping DesktopObserver."
        )

        self.running = False

        self._stop_event.set()

        poll_thread = self._poll_thread

        self._poll_thread = None

        if (
            poll_thread is not None
            and poll_thread is not threading.current_thread()
        ):

            poll_thread.join(
                timeout=3.0
            )

        logger.info(
            self.MODULE,
            "DesktopObserver stopped."
        )

    def is_running(self):
        """
        Return whether the observer is currently active.
        """

        return self.running

    # --------------------------------------------------
    # POLLING LOOP
    # --------------------------------------------------

    def _poll_loop(self):
        """
        Continuously poll DesktopVisionEngine while
        Live Mode is active.
        """

        logger.info(
            self.MODULE,
            "Desktop polling loop started."
        )

        while not self._stop_event.is_set():

            if not self.running:
                break

            self.poll()

            self._stop_event.wait(
                self.POLL_INTERVAL
            )

        logger.info(
            self.MODULE,
            "Desktop polling loop stopped."
        )

    # --------------------------------------------------
    # DESKTOP POLLING
    # --------------------------------------------------

    def poll(self):
        """
        Perform one unified desktop observation cycle.

        DesktopVisionEngine performs one native desktop
        acquisition and returns:

            - complete desktop image
            - dirty regions
            - move regions

        The image and change metadata therefore originate
        from the same native acquisition cycle.

        Returns
        -------
        bool
            True when observation was performed while the
            observer was running.

        Notes
        -----
        This method intentionally performs no OCR,
        Translation or TranslationMap updates.
        """

        if (
            not self.running
            or self._stop_event.is_set()
        ):
            return False

        poll_start = time.perf_counter()

        try:

            # --------------------------------------------------
            # Unified native acquisition.
            #
            # The image and change metadata come from the
            # SAME Desktop Duplication acquisition.
            # --------------------------------------------------

            desktop_state = (
                capture_desktop_state()
            )

        except Exception as error:

            if self._stop_event.is_set():

                logger.info(
                    self.MODULE,
                    "Desktop polling interrupted during shutdown."
                )

                return False

            logger.error(
                self.MODULE,
                "Desktop polling failed: "
                f"{error}"
            )

            return False

        #
        # The native capture may have completed after
        # stop() was called.
        #
        # Never forward stale desktop state.
        #

        if (
            not self.running
            or self._stop_event.is_set()
        ):
            return False

        dirty_regions = desktop_state.get(
            "dirty_regions",
            [],
        )

        move_regions = desktop_state.get(
            "move_regions",
            [],
        )

        # --------------------------------------------------
        # No desktop change.
        # --------------------------------------------------

        if not dirty_regions and not move_regions:
            return True

        poll_time = (
            time.perf_counter()
            - poll_start
        )

        # --------------------------------------------------
        # Desktop changed.
        # --------------------------------------------------

        logger.info(
            self.MODULE,
            "Desktop changed "
            f"({len(dirty_regions)} dirty region(s), "
            f"{len(move_regions)} move region(s), "
            f"{poll_time:.3f}s)."
        )

        # --------------------------------------------------
        # Diagnostic region logging
        # --------------------------------------------------

        for index, region in enumerate(
            dirty_regions,
            start=1,
        ):

            logger.info(
                self.MODULE,
                f"Dirty region [{index}] bounds: "
                f"{region.bounds}"
            )

        for index, region in enumerate(
            move_regions,
            start=1,
        ):

            logger.info(
                self.MODULE,
                f"Move region [{index}] bounds: "
                f"{region.bounds}"
            )

        #
        # Check one final time before notifying the
        # application Controller.
        #

        if (
            not self.running
            or self._stop_event.is_set()
        ):
            return False

        # --------------------------------------------------
        # IMPORTANT
        #
        # Pass the COMPLETE unified desktop acquisition.
        #
        # Do NOT extract only dirty_regions here.
        #
        # The next stages need access to:
        #
        #     desktop_state["image"]
        #     desktop_state["dirty_regions"]
        #     desktop_state["move_regions"]
        #
        # All three belong to the same native acquisition.
        # --------------------------------------------------

        self.controller.on_desktop_state_changed(
            desktop_state
        )

        return True

    # --------------------------------------------------
    # MANUAL NOTIFICATION
    # --------------------------------------------------

    def notify_desktop_changed(
        self,
        dirty_regions,
    ):
        """
        Notify the Controller that desktop regions changed.

        This method is retained for compatibility with the
        existing observer interface.

        Parameters
        ----------
        dirty_regions : list[tuple]
            List of changed desktop regions.

            Format:
                (left, top, width, height)
        """

        if (
            not self.running
            or self._stop_event.is_set()
        ):
            return

        logger.info(
            self.MODULE,
            "Desktop changed "
            f"({len(dirty_regions)} dirty region(s))."
        )

        if (
            not self.running
            or self._stop_event.is_set()
        ):
            return

        #
        # Compatibility notification.
        #
        # This method does not have a complete desktop image,
        # therefore it is intentionally separate from the
        # unified Live acquisition path.
        #

        self.controller.on_desktop_changed(
            dirty_regions
        )