"""
core/change_filter.py

Desktop Change Filter

Tightens DXGI dirty regions by comparing the current
unified desktop image with the previous unified desktop
image.

Responsibilities
----------------
- Retain the previous complete desktop image.
- Compare the previous and current desktop images.
- Analyze only DXGI-reported dirty regions.
- Determine the actual pixel-change bounds inside each
  dirty region.
- Separate spatially distinct pixel changes into multiple
  tightened desktop change regions.
- Reject obvious non-text visual noise using cluster-shape
  characteristics.
- Reject excessively large individual change clusters.
- Return multiple meaningful desktop change regions.

This class does NOT:
- Capture the desktop.
- Perform OCR.
- Perform Translation.
- Query the TranslationMap.
- Control the Floating Lens.
- Perform debounce or settling logic.

The filter performs pixel-difference tightening,
connected-component style clustering, basic text-like
change filtering, and single-cluster size protection only.
"""

from __future__ import annotations

from PIL import ImageChops

from core.capture_engine import DesktopChangeRegion


class ChangeFilter:
    """
    Tightens desktop dirty regions using pixel differences.

    The filter compares two complete unified desktop images:

        previous desktop image
                    +
        current desktop image
                    ↓
             pixel difference
                    ↓
          changed-pixel mask
                    ↓
       connected change clusters
                    ↓
          noise rejection
                    ↓
       multiple tightened regions

    DXGI dirty regions are used as the search boundaries,
    so the complete desktop does not need to be compared
    when only specific regions changed.
    """

    MODULE = "ChangeFilter"

    # --------------------------------------------------
    # Pixel difference configuration
    # --------------------------------------------------

    #
    # Per-channel difference required for a pixel to be
    # considered meaningfully changed.
    #
    PIXEL_DIFF_THRESHOLD = 8

    #
    # Minimum number of changed pixels required before
    # a cluster is considered meaningful.
    #
    MIN_CHANGED_PIXELS = 8

    #
    # Minimum bounding-box area required for a cluster.
    #
    # This prevents tiny isolated rendering artifacts from
    # becoming OCR work.
    #
    MIN_CLUSTER_AREA = 20

    #
    # Maximum size of one individual pixel-change cluster
    # relative to the complete virtual desktop.
    #
    # This is intentionally separate from the coalescing
    # limits because a single connected pixel cluster can
    # become very large without ever being produced by
    # region merging.
    #
    # Example:
    #
    #     desktop = 3840 x 1080
    #     desktop area = 4,147,200 pixels
    #     maximum single cluster = 829,440 pixels
    #
    # A cluster larger than this is considered too large
    # to send directly into OCR.
    #
    MAX_SINGLE_CLUSTER_AREA_RATIO = 0.20

    #
    # Small expansion used while clustering nearby changed
    # pixels.
    #
    # This allows characters and nearby portions of the same
    # text line to remain part of one change cluster.
    #
    CLUSTER_DILATION = 2

    #
    # Small padding around the final detected changed bounds.
    #
    DIFF_PADDING = 4

    # --------------------------------------------------
    # Text-like change filtering
    # --------------------------------------------------

    #
    # A text change normally contains gaps between strokes
    # and therefore does not fill its entire bounding box.
    #
    # Clusters above this value are treated as too solid
    # to be considered text-like.
    #
    MAX_TEXT_FILL_RATIO = 0.75

    #
    # Extremely narrow/tall changes are commonly caret,
    # cursor, or indicator changes rather than text.
    #
    MAX_TEXT_ASPECT_RATIO = 4.0

    #
    # A complete text line can naturally be wider than the
    # per-cluster aspect-ratio limit. This higher limit is used
    # only after multiple compatible clusters have been grouped.
    # Solid or narrow UI changes must still pass the fill-ratio,
    # width, and grouping geometry checks.
    #
    MAX_GROUPED_TEXT_ASPECT_RATIO = 12.0

    #
    # A meaningful text change should have at least enough
    # horizontal width to represent a plausible character
    # or short text run.
    #
    MIN_TEXT_WIDTH = 8

    # --------------------------------------------------
    # Scroll-change detection
    # --------------------------------------------------

    SCROLL_MIN_REGION_WIDTH = 300
    SCROLL_MIN_REGION_HEIGHT = 150
    SCROLL_MIN_REGION_AREA_RATIO = 0.12
    SCROLL_MIN_CHANGED_PIXEL_RATIO = 0.08
    SCROLL_MAX_ASPECT_RATIO = 12.0

    # --------------------------------------------------
    # Text-change grouping configuration
    # --------------------------------------------------

    #
    # Nearby pixel-change clusters are grouped only when their
    # geometry is compatible with one text line. These limits
    # are intentionally small so grouping does not become a
    # replacement for UI filtering.
    #
    TEXT_GROUP_MAX_HORIZONTAL_GAP = 12
    TEXT_GROUP_HORIZONTAL_SCALE = 1.5
    TEXT_GROUP_MAX_VERTICAL_GAP = 4
    TEXT_GROUP_VERTICAL_SCALE = 0.75
    TEXT_GROUP_MAX_CENTER_DELTA = 5
    TEXT_GROUP_CENTER_SCALE = 0.75

    def __init__(self):
        """
        Initialize the ChangeFilter.

        No desktop capture is performed here.
        """

        self._previous_image = None

        #
        # Deferred scroll state. A scroll-like frame is not sent
        # to OCR immediately. Instead, the union of the scroll
        # dirty regions is retained until the scroll activity stops.
        #
        self._scroll_active = False
        self._scroll_region = None
        self._scroll_detected_this_filter_call = False

    # --------------------------------------------------
    # BASELINE
    # --------------------------------------------------

    def set_baseline(
        self,
        desktop_image,
    ):
        """
        Store a complete desktop image as the comparison
        baseline.
        """

        if desktop_image is None:
            raise ValueError(
                "Desktop baseline image cannot be None."
            )

        self._validate_image(
            desktop_image
        )

        self._previous_image = (
            desktop_image.copy()
        )

        self._clear_scroll_state()

    def reset(self):
        """
        Clear the stored comparison baseline.
        """

        self._previous_image = None

        self._clear_scroll_state()

    def has_baseline(self) -> bool:
        """
        Return True when a previous desktop image exists.
        """

        return self._previous_image is not None

    # --------------------------------------------------
    # FILTER
    # --------------------------------------------------

    def filter_regions(
        self,
        desktop_image,
        dirty_regions,
        desktop_bounds,
    ):
        """
        Tighten DXGI dirty regions using pixel differences.

        Returns
        -------
        list[DesktopChangeRegion]
            Multiple tightened regions containing actual
            pixel changes.

        The first image establishes the baseline and produces
        no OCR regions.

        The current complete desktop image always becomes the
        new comparison baseline.

        Scroll-like viewport changes are handled differently
        from ordinary text changes:

            scrolling starts
                ↓
            accumulate scroll dirty regions
                ↓
            suppress transient OCR work
                ↓
            scrolling stops
                ↓
            release accumulated region
                ↓
            ControllerLive 3-second stability gate
                ↓
            OCR / Translation

        This prevents every intermediate scroll frame from
        continuously restarting Live OCR work.
        """

        if desktop_image is None:
            raise ValueError(
                "Current desktop image cannot be None."
            )

        self._validate_image(
            desktop_image
        )

        if not desktop_bounds:
            raise ValueError(
                "Desktop bounds cannot be empty."
            )

        if len(desktop_bounds) != 4:
            raise ValueError(
                "Desktop bounds must contain "
                "(left, top, width, height)."
            )

        (
            desktop_left,
            desktop_top,
            desktop_width,
            desktop_height,
        ) = desktop_bounds

        if desktop_width <= 0:
            raise ValueError(
                "Desktop width must be greater "
                "than zero."
            )

        if desktop_height <= 0:
            raise ValueError(
                "Desktop height must be greater "
                "than zero."
            )

        #
        # No dirty regions means there is nothing to analyze.
        #
        # If a deferred scroll is active, however, the absence
        # of a new dirty region is a useful indication that the
        # transient scroll activity has stopped.
        #

        if not dirty_regions:

            deferred_scroll_region = (
                self._finalize_deferred_scroll()
            )

            self._previous_image = (
                desktop_image.copy()
            )

            if deferred_scroll_region is not None:

                print(
                    "[ChangeFilter] "
                    "Scroll activity stopped; releasing "
                    "deferred scroll region for stable OCR: "
                    f"{deferred_scroll_region.bounds}"
                )

                return [
                    deferred_scroll_region
                ]

            return []

        #
        # First acquisition establishes the baseline.
        #

        if self._previous_image is None:

            self._previous_image = (
                desktop_image.copy()
            )

            return []

        #
        # The previous and current images must represent
        # the same virtual desktop dimensions.
        #

        if (
            self._previous_image.size
            != desktop_image.size
        ):

            self._previous_image = (
                desktop_image.copy()
            )

            self._clear_scroll_state()

            return []

        filtered_regions = []

        #
        # This flag is reset for every complete desktop
        # acquisition.
        #
        # If at least one dirty region is identified as
        # scroll-like, the deferred scroll remains active.
        #
        self._scroll_detected_this_filter_call = False

        for dirty_region in dirty_regions:

            regions = self._filter_region(
                previous_image=self._previous_image,
                current_image=desktop_image,
                dirty_region=dirty_region,
                desktop_left=desktop_left,
                desktop_top=desktop_top,
                desktop_width=desktop_width,
                desktop_height=desktop_height,
            )

            if regions:

                filtered_regions.extend(
                    regions
                )

        #
        # If we were already tracking a scroll and this frame did
        # not contain another scroll-like change, the scroll has
        # stopped.
        #
        # Release the accumulated region now. It will then pass
        # through ControllerLive's existing 3-second stability
        # gate before OCR/translation starts.
        #

        if (
            self._scroll_active
            and not self._scroll_detected_this_filter_call
        ):

            deferred_scroll_region = (
                self._finalize_deferred_scroll()
            )

            if deferred_scroll_region is not None:

                print(
                    "[ChangeFilter] "
                    "Scroll activity stopped; releasing "
                    "deferred scroll region for stable OCR: "
                    f"{deferred_scroll_region.bounds}"
                )

                filtered_regions.insert(
                    0,
                    deferred_scroll_region,
                )

        #
        # The current complete desktop becomes the baseline
        # for the next acquisition.
        #

        self._previous_image = (
            desktop_image.copy()
        )

        return filtered_regions

    # --------------------------------------------------
    # REGION PROCESSING
    # --------------------------------------------------

    def _filter_region(
        self,
        previous_image,
        current_image,
        dirty_region,
        desktop_left,
        desktop_top,
        desktop_width,
        desktop_height,
    ):
        """
        Compare one DXGI dirty region between two complete
        desktop images.

        Returns
        -------
        list[DesktopChangeRegion]
            One or more tightened regions containing actual
            spatially separated changes.

        Nearby compatible text-change clusters are grouped
        before the final text-like shape test. This allows
        characters or short fragments produced by one typing
        event to reach OCR as a useful text region without
        increasing DIFF_PADDING.
        """

        left = dirty_region.left
        top = dirty_region.top
        right = dirty_region.right
        bottom = dirty_region.bottom

        #
        # Diagnostic information.
        #

        print(
            "[ChangeFilter] "
            f"DXGI dirty region: "
            f"({left}, {top}) -> ({right}, {bottom})"
        )

        #
        # Validate the DXGI region against the virtual desktop.
        #

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

            print(
                "[ChangeFilter] "
                "Dirty region rejected: outside desktop bounds."
            )

            return []

        #
        # Convert Windows virtual-desktop coordinates into
        # image-local coordinates.
        #

        crop_left = (
            left
            - desktop_left
        )

        crop_top = (
            top
            - desktop_top
        )

        crop_right = (
            right
            - desktop_left
        )

        crop_bottom = (
            bottom
            - desktop_top
        )

        previous_crop = (
            previous_image.crop(
                (
                    crop_left,
                    crop_top,
                    crop_right,
                    crop_bottom,
                )
            )
        )

        current_crop = (
            current_image.crop(
                (
                    crop_left,
                    crop_top,
                    crop_right,
                    crop_bottom,
                )
            )
        )

        #
        # Calculate absolute pixel difference.
        #

        difference = ImageChops.difference(
            previous_crop,
            current_crop,
        )

        #
        # Convert the difference into grayscale.
        #

        difference_rgb = (
            difference.convert("RGB")
        )

        grayscale = (
            difference_rgb.convert("L")
        )

        #
        # Apply the configured pixel-difference threshold.
        #

        threshold = (
            self.PIXEL_DIFF_THRESHOLD
        )

        changed_mask = grayscale.point(
            lambda value:
                255
                if value >= threshold
                else 0
        )

        #
        # Find connected change clusters.
        #

        clusters = (
            self._find_change_clusters(
                changed_mask
            )
        )

        #
        # Diagnostic raw cluster information.
        #
        # These are the actual bounds produced by the
        # clustering algorithm BEFORE:
        #
        #     - MIN_CHANGED_PIXELS filtering
        #     - single-cluster size filtering
        #     - text-cluster grouping
        #     - text-like filtering
        #     - DIFF_PADDING
        #

        print(
            "[ChangeFilter] "
            f"Raw clusters found: {len(clusters)}"
        )

        for index, cluster in enumerate(
            clusters,
            start=1,
        ):

            metrics = (
                self._cluster_shape_metrics(
                    cluster
                )
            )

            cluster_left = cluster["left"]
            cluster_top = cluster["top"]
            cluster_right = cluster["right"]
            cluster_bottom = cluster["bottom"]

            absolute_left = (
                left
                + cluster_left
            )

            absolute_top = (
                top
                + cluster_top
            )

            absolute_right = (
                left
                + cluster_right
            )

            absolute_bottom = (
                top
                + cluster_bottom
            )

            print(
                "[ChangeFilter] "
                f"RAW CLUSTER[{index}] "
                f"local=("
                f"{cluster_left}, "
                f"{cluster_top}, "
                f"{cluster_right}, "
                f"{cluster_bottom}"
                f") "
                f"absolute=("
                f"{absolute_left}, "
                f"{absolute_top}, "
                f"{absolute_right}, "
                f"{absolute_bottom}"
                f") "
                f"size={metrics['width']}x"
                f"{metrics['height']} "
                f"area={metrics['area']} "
                f"changed_pixels="
                f"{cluster['changed_pixels']} "
                f"run_count="
                f"{metrics['run_count']} "
                f"fill_ratio="
                f"{metrics['fill_ratio']:.3f} "
                f"aspect_ratio="
                f"{metrics['aspect_ratio']:.2f}"
            )

        if not clusters:

            print(
                "[ChangeFilter] "
                "No raw pixel-change clusters found."
            )

            return []

        #
        # Scroll/reflow changes are fundamentally different from
        # ordinary text edits.
        #
        # Detect them before the text-shape gate.
        #

        scroll_region = self._detect_scroll_like_change(
            dirty_region=dirty_region,
            clusters=clusters,
            changed_mask=changed_mask,
            desktop_width=desktop_width,
            desktop_height=desktop_height,
        )

        if scroll_region is not None:

            self._begin_or_extend_deferred_scroll(
                scroll_region=scroll_region,
            )

            self._scroll_detected_this_filter_call = True

            print(
                "[ChangeFilter] "
                "SCROLL-LIKE CHANGE detected; "
                "deferring viewport change until scrolling stops."
            )

            #
            # Do not send the transient scroll frame to OCR.
            #
            # The accumulated dirty region is retained until
            # a later desktop acquisition no longer looks like
            # another scroll frame.
            #
            return []

        #
        # Calculate the maximum allowed area for one raw
        # connected cluster.
        #
        # This uses the complete virtual desktop dimensions,
        # not the current DXGI dirty-region dimensions.
        #

        desktop_area = (
            desktop_width
            * desktop_height
        )

        max_single_cluster_area = int(
            desktop_area
            * self.MAX_SINGLE_CLUSTER_AREA_RATIO
        )

        #
        # Discard clusters that are too small in terms of
        # actual changed pixels or too large in terms of
        # their complete bounding-box area.
        #
        # The large-cluster gate is intentionally applied
        # BEFORE text grouping so that a naturally huge
        # connected component cannot enter the grouping
        # stage and eventually become an OCR region.
        #

        candidate_clusters = []

        for index, cluster in enumerate(
            clusters,
            start=1,
        ):

            changed_pixel_count = (
                cluster["changed_pixels"]
            )

            if (
                changed_pixel_count
                < self.MIN_CHANGED_PIXELS
            ):

                print(
                    "[ChangeFilter] "
                    f"CLUSTER[{index}] rejected before grouping: "
                    f"changed_pixels="
                    f"{changed_pixel_count} "
                    f"< minimum="
                    f"{self.MIN_CHANGED_PIXELS}"
                )

                continue

            metrics = (
                self._cluster_shape_metrics(
                    cluster
                )
            )

            cluster_area = (
                metrics["area"]
            )

            if (
                cluster_area
                > max_single_cluster_area
            ):

                print(
                    "[ChangeFilter] "
                    f"CLUSTER[{index}] rejected before grouping: "
                    f"area="
                    f"{cluster_area} "
                    f"> maximum="
                    f"{max_single_cluster_area} "
                    f"("
                    f"{self.MAX_SINGLE_CLUSTER_AREA_RATIO:.2f}"
                    f" of desktop area)"
                )

                continue

            candidate_clusters.append(
                cluster
            )

        if not candidate_clusters:

            print(
                "[ChangeFilter] "
                "No clusters survived the "
                "pre-grouping gates."
            )

            return []

        #
        # Group nearby compatible clusters before applying the
        # final text-like shape gate.
        #

        grouped_clusters = (
            self._group_text_change_clusters(
                candidate_clusters
            )
        )

        print(
            "[ChangeFilter] "
            f"Grouped clusters: "
            f"{len(grouped_clusters)}"
        )

        for index, cluster in enumerate(
            grouped_clusters,
            start=1,
        ):

            metrics = (
                self._cluster_shape_metrics(
                    cluster
                )
            )

            print(
                "[ChangeFilter] "
                f"GROUP[{index}] "
                f"local=("
                f"{cluster['left']}, "
                f"{cluster['top']}, "
                f"{cluster['right']}, "
                f"{cluster['bottom']}"
                f") "
                f"size={metrics['width']}x"
                f"{metrics['height']} "
                f"area={metrics['area']} "
                f"changed_pixels="
                f"{cluster['changed_pixels']} "
                f"run_count="
                f"{metrics['run_count']} "
                f"fill_ratio="
                f"{metrics['fill_ratio']:.3f} "
                f"aspect_ratio="
                f"{metrics['aspect_ratio']:.2f}"
            )

        result_regions = []

        for index, cluster in enumerate(
            grouped_clusters,
            start=1,
        ):

            metrics = (
                self._cluster_shape_metrics(
                    cluster
                )
            )

            if not self._is_text_like_cluster(
                metrics,
                grouped=cluster.get(
                    "cluster_count",
                    1,
                ) > 1,
            ):

                print(
                    "[ChangeFilter] "
                    f"GROUP[{index}] rejected: "
                    f"not text-like "
                    f"(fill_ratio="
                    f"{metrics['fill_ratio']:.3f}, "
                    f"aspect_ratio="
                    f"{metrics['aspect_ratio']:.2f}, "
                    f"width="
                    f"{metrics['width']}, "
                    f"height="
                    f"{metrics['height']})"
                )

                continue

            cluster_area = (
                metrics["area"]
            )

            if (
                cluster_area
                < self.MIN_CLUSTER_AREA
            ):

                print(
                    "[ChangeFilter] "
                    f"GROUP[{index}] rejected: "
                    f"area={cluster_area} "
                    f"< minimum="
                    f"{self.MIN_CLUSTER_AREA}"
                )

                continue

            #
            # Add safety padding around the detected
            # changed pixels.
            #

            result_left = max(
                0,
                cluster["left"]
                - self.DIFF_PADDING,
            )

            result_top = max(
                0,
                cluster["top"]
                - self.DIFF_PADDING,
            )

            result_right = min(
                current_crop.width,
                cluster["right"]
                + self.DIFF_PADDING,
            )

            result_bottom = min(
                current_crop.height,
                cluster["bottom"]
                + self.DIFF_PADDING,
            )

            #
            # Convert the tightened region back into
            # Windows virtual-desktop coordinates.
            #

            desktop_result_left = (
                left
                + result_left
            )

            desktop_result_top = (
                top
                + result_top
            )

            desktop_result_right = (
                left
                + result_right
            )

            desktop_result_bottom = (
                top
                + result_bottom
            )

            print(
                "[ChangeFilter] "
                f"FINAL REGION[{index}] "
                f"bounds=("
                f"{desktop_result_left}, "
                f"{desktop_result_top}, "
                f"{desktop_result_right}, "
                f"{desktop_result_bottom}"
                f")"
            )

            result_regions.append(
                DesktopChangeRegion(
                    left=desktop_result_left,
                    top=desktop_result_top,
                    right=desktop_result_right,
                    bottom=desktop_result_bottom,
                )
            )

        print(
            "[ChangeFilter] "
            f"Filtered regions returned: "
            f"{len(result_regions)}"
        )

        return result_regions

    # --------------------------------------------------
    # DEFERRED SCROLL STATE
    # --------------------------------------------------

    def _clear_scroll_state(self):
        """
        Clear any deferred scroll-tracking state.
        """

        self._scroll_active = False
        self._scroll_region = None
        self._scroll_detected_this_filter_call = False

    def _begin_or_extend_deferred_scroll(
        self,
        scroll_region,
    ):
        """
        Start or extend a deferred scroll operation.

        Subsequent scroll-like frames extend only the accumulated
        dirty bounds. ``_previous_image`` continues advancing
        frame-by-frame so normal change detection remains intact.
        """

        if not self._scroll_active:

            self._scroll_active = True

            self._scroll_region = (
                scroll_region.left,
                scroll_region.top,
                scroll_region.right,
                scroll_region.bottom,
            )

            print(
                "[ChangeFilter] "
                "Started deferred scroll tracking: "
                f"region={scroll_region.bounds}"
            )

            return

        if self._scroll_region is None:

            self._scroll_region = (
                scroll_region.left,
                scroll_region.top,
                scroll_region.right,
                scroll_region.bottom,
            )

            return

        left, top, right, bottom = (
            self._scroll_region
        )

        self._scroll_region = (
            min(
                left,
                scroll_region.left,
            ),
            min(
                top,
                scroll_region.top,
            ),
            max(
                right,
                scroll_region.right,
            ),
            max(
                bottom,
                scroll_region.bottom,
            ),
        )

    def _finalize_deferred_scroll(self):
        """
        Return the accumulated scroll region and clear deferred
        state.

        OCR is intentionally NOT performed here. The returned
        region is handed to ControllerLive, which still applies
        its existing 3-second stability requirement before
        starting OCR/translation.
        """

        if not self._scroll_active:

            return None

        if self._scroll_region is None:

            self._clear_scroll_state()

            return None

        left, top, right, bottom = (
            self._scroll_region
        )

        region = DesktopChangeRegion(
            left=left,
            top=top,
            right=right,
            bottom=bottom,
        )

        self._clear_scroll_state()

        return region

    # --------------------------------------------------
    # SCROLL CHANGE DETECTION
    # --------------------------------------------------

    def _detect_scroll_like_change(
        self,
        dirty_region,
        clusters,
        changed_mask,
        desktop_width,
        desktop_height,
    ):
        """
        Return the dirty region when it strongly resembles
        a viewport change.
        """

        left = dirty_region.left
        top = dirty_region.top
        right = dirty_region.right
        bottom = dirty_region.bottom

        width = right - left
        height = bottom - top

        if width <= 0 or height <= 0:

            return None

        region_area = (
            width
            * height
        )

        desktop_area = (
            desktop_width
            * desktop_height
        )

        if desktop_area <= 0:

            return None

        if (
            width
            < self.SCROLL_MIN_REGION_WIDTH
            or height
            < self.SCROLL_MIN_REGION_HEIGHT
        ):

            return None

        region_area_ratio = (
            region_area
            / desktop_area
        )

        if (
            region_area_ratio
            < self.SCROLL_MIN_REGION_AREA_RATIO
        ):

            return None

        changed_pixels = sum(
            1
            for value
            in changed_mask.tobytes()
            if value
        )

        changed_pixel_ratio = (
            changed_pixels
            / region_area
        )

        if (
            changed_pixel_ratio
            < self.SCROLL_MIN_CHANGED_PIXEL_RATIO
        ):

            return None

        shortest_dimension = min(
            width,
            height,
        )

        longest_dimension = max(
            width,
            height,
        )

        aspect_ratio = (
            longest_dimension
            / shortest_dimension
        )

        if (
            aspect_ratio
            > self.SCROLL_MAX_ASPECT_RATIO
        ):

            return None

        print(
            "[ChangeFilter] "
            f"Scroll candidate metrics: "
            f"region={width}x{height} "
            f"area_ratio={region_area_ratio:.3f} "
            f"changed_ratio={changed_pixel_ratio:.3f} "
            f"clusters={len(clusters)} "
            f"aspect_ratio={aspect_ratio:.2f}"
        )

        return DesktopChangeRegion(
            left=left,
            top=top,
            right=right,
            bottom=bottom,
        )

    # --------------------------------------------------
    # TEXT CHANGE GROUPING
    # --------------------------------------------------

    def _group_text_change_clusters(
        self,
        clusters,
    ):
        """
        Group nearby compatible pixel-change clusters that
        are likely parts of the same text line.

        Grouping is deliberately conservative:

        - horizontal separation must be small relative to
          the cluster height
        - vertical positions must overlap or remain close
        - grouping is based on geometry, not large padding
        - final text-like filtering is still applied to the
          combined region

        This allows fragmented changes such as individual
        characters from a typing event to become one OCR
        region while avoiding broad desktop-wide grouping.

        Returns
        -------
        list[dict]
            Grouped spatial change clusters.
        """

        if not clusters:

            return []

        grouped = []

        #
        # Process clusters in stable reading order.
        #

        ordered_clusters = sorted(
            clusters,
            key=lambda cluster: (
                cluster["top"],
                cluster["left"],
            ),
        )

        for cluster in ordered_clusters:

            merged = False

            #
            # Compare against existing groups.
            #
            # Iterate from the most recently created group
            # because text fragments on the same line are
            # normally spatially close.
            #

            for group in reversed(
                grouped
            ):

                if not self._text_clusters_are_compatible(
                    group,
                    cluster,
                ):

                    continue

                self._merge_cluster_into_group(
                    group,
                    cluster,
                )

                merged = True

                #
                # A cluster belongs to one spatial text group.
                #

                break

            if not merged:

                grouped.append(
                    {
                        "left": cluster["left"],
                        "top": cluster["top"],
                        "right": cluster["right"],
                        "bottom": cluster["bottom"],
                        "changed_pixels": (
                            cluster["changed_pixels"]
                        ),
                        "run_count": (
                            cluster.get(
                                "run_count",
                                0,
                            )
                        ),
                        "cluster_count": 1,
                    }
                )

        #
        # One pass can leave a group that has become compatible
        # with an earlier group after it expanded. Repeatedly
        # merge compatible groups until stable.
        #
        # This is still controlled because every merge must
        # satisfy the same text-line geometry rules.
        #

        changed = True

        while changed:

            changed = False

            merged_groups = []

            for group in grouped:

                merged = False

                for existing in merged_groups:

                    if not self._text_clusters_are_compatible(
                        existing,
                        group,
                    ):

                        continue

                    self._merge_cluster_into_group(
                        existing,
                        group,
                    )

                    merged = True
                    changed = True

                    break

                if not merged:

                    merged_groups.append(
                        group
                    )

            grouped = merged_groups

        grouped.sort(
            key=lambda cluster: (
                cluster["top"],
                cluster["left"],
            )
        )

        return grouped

    def _text_clusters_are_compatible(
        self,
        first,
        second,
    ) -> bool:
        """
        Determine whether two change clusters are close enough
        and aligned enough to plausibly belong to the same text
        line.

        The test intentionally uses the cluster geometry rather
        than DIFF_PADDING. It therefore does not enlarge every
        dirty region indiscriminately.
        """

        first_width = (
            first["right"]
            - first["left"]
        )

        first_height = (
            first["bottom"]
            - first["top"]
        )

        second_width = (
            second["right"]
            - second["left"]
        )

        second_height = (
            second["bottom"]
            - second["top"]
        )

        if (
            first_width <= 0
            or first_height <= 0
        ):

            return False

        if (
            second_width <= 0
            or second_height <= 0
        ):

            return False

        #
        # Use the smaller cluster height to keep the grouping
        # conservative when a large UI redraw is near a text
        # fragment.
        #

        reference_height = min(
            first_height,
            second_height,
        )

        #
        # Horizontal gap between the two bounding boxes.
        #
        # Negative values mean the boxes overlap horizontally.
        #

        if first["right"] < second["left"]:

            horizontal_gap = (
                second["left"]
                - first["right"]
            )

        elif second["right"] < first["left"]:

            horizontal_gap = (
                first["left"]
                - second["right"]
            )

        else:

            horizontal_gap = 0

        #
        # Vertical gap between the two bounding boxes.
        #
        # Negative values mean the boxes overlap vertically.
        #

        if first["bottom"] < second["top"]:

            vertical_gap = (
                second["top"]
                - first["bottom"]
            )

        elif second["bottom"] < first["top"]:

            vertical_gap = (
                first["top"]
                - second["bottom"]
            )

        else:

            vertical_gap = 0

        #
        # Text characters normally have a small horizontal gap.
        # The limit scales modestly with character height rather
        # than using a large fixed padding.
        #

        max_horizontal_gap = max(
            self.TEXT_GROUP_MAX_HORIZONTAL_GAP,
            int(
                reference_height
                * self.TEXT_GROUP_HORIZONTAL_SCALE
            ),
        )

        if (
            horizontal_gap
            > max_horizontal_gap
        ):

            return False

        #
        # Text on the same line should vertically overlap or
        # remain close. This prevents separate lines and distant
        # UI elements from being joined.
        #

        max_vertical_gap = max(
            self.TEXT_GROUP_MAX_VERTICAL_GAP,
            int(
                reference_height
                * self.TEXT_GROUP_VERTICAL_SCALE
            ),
        )

        if (
            vertical_gap
            > max_vertical_gap
        ):

            return False

        #
        # Require meaningful vertical alignment.
        #
        # A pure vertical proximity check is not sufficient for
        # UI elements stacked near one another.
        #

        first_center_y = (
            first["top"]
            + first["bottom"]
        ) / 2.0

        second_center_y = (
            second["top"]
            + second["bottom"]
        ) / 2.0

        center_delta = abs(
            first_center_y
            - second_center_y
        )

        max_center_delta = max(
            self.TEXT_GROUP_MAX_CENTER_DELTA,
            reference_height
            * self.TEXT_GROUP_CENTER_SCALE,
        )

        if (
            center_delta
            > max_center_delta
        ):

            return False

        return True

    @staticmethod
    def _merge_cluster_into_group(
        group,
        cluster,
    ):
        """
        Merge one change cluster into an existing spatial group.
        """

        group["left"] = min(
            group["left"],
            cluster["left"],
        )

        group["top"] = min(
            group["top"],
            cluster["top"],
        )

        group["right"] = max(
            group["right"],
            cluster["right"],
        )

        group["bottom"] = max(
            group["bottom"],
            cluster["bottom"],
        )

        group["changed_pixels"] += (
            cluster["changed_pixels"]
        )

        group["run_count"] += (
            cluster.get(
                "run_count",
                0,
            )
        )

        group["cluster_count"] = (
            group.get(
                "cluster_count",
                1,
            )
            + cluster.get(
                "cluster_count",
                1,
            )
        )

    # --------------------------------------------------
    # CLUSTER METRICS
    # --------------------------------------------------

    @staticmethod
    def _cluster_shape_metrics(
        cluster,
    ):
        """
        Calculate shape metrics for a change cluster.

        These metrics are used to distinguish text-like
        changes from obvious visual noise such as carets,
        narrow indicators, and solid UI redraws.

        Returns
        -------
        dict
            {
                "width": int,
                "height": int,
                "area": int,
                "fill_ratio": float,
                "aspect_ratio": float,
                "run_count": int,
            }
        """

        width = (
            cluster["right"]
            - cluster["left"]
        )

        height = (
            cluster["bottom"]
            - cluster["top"]
        )

        area = (
            width
            * height
        )

        fill_ratio = (
            cluster["changed_pixels"]
            / area
            if area > 0
            else 0.0
        )

        shortest_dimension = min(
            width,
            height,
        )

        longest_dimension = max(
            width,
            height,
        )

        aspect_ratio = (
            longest_dimension
            / shortest_dimension
            if shortest_dimension > 0
            else float("inf")
        )

        return {
            "width": width,
            "height": height,
            "area": area,
            "fill_ratio": fill_ratio,
            "aspect_ratio": aspect_ratio,
            "run_count": cluster.get(
                "run_count",
                0,
            ),
        }

    def _is_text_like_cluster(
        self,
        metrics,
        grouped=False,
    ) -> bool:
        """
        Determine whether a change cluster has a basic
        text-like shape.

        This is intentionally a conservative visual gate.

        It does NOT claim that the cluster contains text.
        OCR remains responsible for determining whether
        actual text is present.

        Returns
        -------
        bool
            True when the cluster passes the basic
            text-like shape requirements.
        """

        if (
            metrics["fill_ratio"]
            > self.MAX_TEXT_FILL_RATIO
        ):

            return False

        max_aspect_ratio = (
            self.MAX_GROUPED_TEXT_ASPECT_RATIO
            if grouped
            else self.MAX_TEXT_ASPECT_RATIO
        )

        if (
            metrics["aspect_ratio"]
            > max_aspect_ratio
        ):

            return False

        if (
            metrics["width"]
            < self.MIN_TEXT_WIDTH
        ):

            return False

        return True

    # --------------------------------------------------
    # CHANGE CLUSTERING
    # --------------------------------------------------

    def _find_change_clusters(
        self,
        changed_mask,
    ):
        """
        Find spatially connected changed-pixel clusters.

        The implementation intentionally avoids SciPy,
        OpenCV, or another third-party dependency.

        Changed pixels are converted into horizontal runs.

        A run is connected ONLY to runs from the immediately
        previous image row. CLUSTER_DILATION expands the
        current and previous runs only for the purpose of
        determining whether those two rows are connected.

        IMPORTANT
        ---------
        Component-wide bounding boxes are never used to
        establish connectivity with a later row.

        This prevents a large component from progressively
        "reaching" unrelated pixels and becoming an
        incorrectly huge cluster.

        Returns
        -------
        list[dict]
            Each dictionary contains:

                {
                    "left": int,
                    "top": int,
                    "right": int,
                    "bottom": int,
                    "changed_pixels": int,
                    "run_count": int,
                }
        """

        width, height = (
            changed_mask.size
        )

        if width <= 0 or height <= 0:

            return []

        mask_bytes = (
            changed_mask.tobytes()
        )

        dilation = max(
            0,
            int(
                self.CLUSTER_DILATION
            ),
        )

        components = []

        #
        # Each item is:
        #
        #     (run_left, run_right, component_root)
        #
        # and represents one run from the immediately
        # previous image row.
        #
        # This is intentionally different from storing
        # component bounding boxes. Only adjacent rows
        # participate in connectivity.
        #

        previous_runs = []

        for y in range(height):

            row_start = (
                y * width
            )

            current_runs = []

            x = 0

            #
            # Find horizontal runs of changed pixels.
            #

            while x < width:

                while (
                    x < width
                    and mask_bytes[
                        row_start + x
                    ] == 0
                ):

                    x += 1

                if x >= width:

                    break

                run_left = x

                while (
                    x < width
                    and mask_bytes[
                        row_start + x
                    ] != 0
                ):

                    x += 1

                run_right = x

                current_runs.append(
                    (
                        run_left,
                        run_right,
                    )
                )

            current_previous_links = []

            #
            # Process every changed run on this row.
            #

            for (
                run_left,
                run_right,
            ) in current_runs:

                expanded_left = max(
                    0,
                    run_left
                    - dilation,
                )

                expanded_right = min(
                    width,
                    run_right
                    + dilation,
                )

                matching_roots = []

                #
                # Connect ONLY against runs from the
                # immediately previous row.
                #

                for (
                    previous_left,
                    previous_right,
                    previous_root,
                ) in previous_runs:

                    previous_expanded_left = max(
                        0,
                        previous_left
                        - dilation,
                    )

                    previous_expanded_right = min(
                        width,
                        previous_right
                        + dilation,
                    )

                    if (
                        expanded_right
                        <= previous_expanded_left
                        or expanded_left
                        >= previous_expanded_right
                    ):

                        continue

                    root = (
                        self._find_component_root(
                            components,
                            previous_root,
                        )
                    )

                    if root not in matching_roots:

                        matching_roots.append(
                            root
                        )

                #
                # No previous-row connection:
                # create a new component.
                #

                if not matching_roots:

                    component_index = (
                        len(components)
                    )

                    components.append(
                        {
                            "left": run_left,
                            "top": y,
                            "right": run_right,
                            "bottom": y + 1,
                            "changed_pixels": (
                                run_right
                                - run_left
                            ),
                            "run_count": 1,
                            "parent": component_index,
                        }
                    )

                    current_previous_links.append(
                        (
                            run_left,
                            run_right,
                            component_index,
                        )
                    )

                    continue

                #
                # Attach the current run to the first
                # matching component.
                #

                current_root = (
                    matching_roots[0]
                )

                current_root = (
                    self._find_component_root(
                        components,
                        current_root,
                    )
                )

                component = (
                    components[current_root]
                )

                component["left"] = min(
                    component["left"],
                    run_left,
                )

                component["top"] = min(
                    component["top"],
                    y,
                )

                component["right"] = max(
                    component["right"],
                    run_right,
                )

                component["bottom"] = max(
                    component["bottom"],
                    y + 1,
                )

                component["changed_pixels"] += (
                    run_right
                    - run_left
                )

                component["run_count"] += 1

                #
                # If the current run touches multiple
                # previous components, those components
                # become one connected component.
                #

                for other_root in (
                    matching_roots[1:]
                ):

                    current_root = (
                        self._merge_components(
                            components,
                            current_root,
                            other_root,
                        )
                    )

                current_root = (
                    self._find_component_root(
                        components,
                        current_root,
                    )
                )

                current_previous_links.append(
                    (
                        run_left,
                        run_right,
                        current_root,
                    )
                )

            #
            # The next row must see ONLY the runs from
            # this row.
            #
            # No component-wide bounding boxes are carried
            # forward.
            #

            previous_runs = []

            for (
                run_left,
                run_right,
                component_index,
            ) in current_previous_links:

                root = (
                    self._find_component_root(
                        components,
                        component_index,
                    )
                )

                previous_runs.append(
                    (
                        run_left,
                        run_right,
                        root,
                    )
                )

        #
        # Resolve merged components.
        #

        final_components = []

        seen_roots = set()

        for index in range(
            len(components)
        ):

            root = (
                self._find_component_root(
                    components,
                    index,
                )
            )

            if root in seen_roots:

                continue

            seen_roots.add(
                root
            )

            root_component = (
                components[root]
            )

            final_components.append(
                {
                    "left": root_component["left"],
                    "top": root_component["top"],
                    "right": root_component["right"],
                    "bottom": root_component["bottom"],
                    "changed_pixels": (
                        root_component[
                            "changed_pixels"
                        ]
                    ),
                    "run_count": (
                        root_component.get(
                            "run_count",
                            0,
                        )
                    ),
                }
            )

        #
        # Sort spatially so ControllerLive receives regions
        # in predictable desktop order.
        #

        final_components.sort(
            key=lambda component: (
                component["top"],
                component["left"],
            )
        )

        return final_components

    # --------------------------------------------------
    # COMPONENT UNION
    # --------------------------------------------------

    @staticmethod
    def _find_component_root(
        components,
        index,
    ):
        """
        Return the root component index using path
        compression.
        """

        root = index

        while (
            components[root]["parent"]
            != root
        ):

            root = (
                components[root]["parent"]
            )

        while (
            components[index]["parent"]
            != index
        ):

            parent = (
                components[index]["parent"]
            )

            components[index]["parent"] = root

            index = parent

        return root

    @classmethod
    def _merge_components(
        cls,
        components,
        first_index,
        second_index,
    ):
        """
        Merge two connected components.
        """

        first_root = (
            cls._find_component_root(
                components,
                first_index,
            )
        )

        second_root = (
            cls._find_component_root(
                components,
                second_index,
            )
        )

        if first_root == second_root:

            return first_root

        first = (
            components[first_root]
        )

        second = (
            components[second_root]
        )

        second["parent"] = first_root

        first["left"] = min(
            first["left"],
            second["left"],
        )

        first["top"] = min(
            first["top"],
            second["top"],
        )

        first["right"] = max(
            first["right"],
            second["right"],
        )

        first["bottom"] = max(
            first["bottom"],
            second["bottom"],
        )

        first["changed_pixels"] += (
            second["changed_pixels"]
        )

        first["run_count"] += (
            second.get(
                "run_count",
                0,
            )
        )

        return first_root

    # --------------------------------------------------
    # VALIDATION
    # --------------------------------------------------

    @staticmethod
    def _validate_image(
        image,
    ):
        """
        Validate that the supplied object is a usable
        PIL image.
        """

        if not hasattr(
            image,
            "size",
        ):

            raise TypeError(
                "Desktop image must be a PIL Image."
            )

        width, height = image.size

        if width <= 0:

            raise ValueError(
                "Desktop image width must be "
                "greater than zero."
            )

        if height <= 0:

            raise ValueError(
                "Desktop image height must be "
                "greater than zero."
            )