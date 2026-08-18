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
- Return multiple meaningful desktop change regions.

This class does NOT:
- Capture the desktop.
- Perform OCR.
- Perform Translation.
- Query the TranslationMap.
- Control the Floating Lens.
- Perform debounce or settling logic.

The filter performs pixel-difference tightening,
connected-component style clustering, and basic
text-like change filtering only.
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
    MAX_TEXT_FILL_RATIO = 0.60

    #
    # Extremely narrow/tall changes are commonly caret,
    # cursor, or indicator changes rather than text.
    #
    MAX_TEXT_ASPECT_RATIO = 4.0

    #
    # A meaningful text change should have at least enough
    # horizontal width to represent a plausible character
    # or short text run.
    #
    MIN_TEXT_WIDTH = 8

    def __init__(self):
        """
        Initialize the ChangeFilter.

        No desktop capture is performed here.
        """

        self._previous_image = None

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

    def reset(self):
        """
        Clear the stored comparison baseline.
        """

        self._previous_image = None

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
        # Still update the baseline because this image is
        # the newest complete desktop state.
        #

        if not dirty_regions:

            self._previous_image = (
                desktop_image.copy()
            )

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

            return []

        filtered_regions = []

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
        #     - MIN_CLUSTER_AREA filtering
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

        result_regions = []

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
                    f"CLUSTER[{index}] rejected: "
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

            if not self._is_text_like_cluster(
                metrics
            ):

                print(
                    "[ChangeFilter] "
                    f"CLUSTER[{index}] rejected: "
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

            cluster_left = cluster["left"]
            cluster_top = cluster["top"]
            cluster_right = cluster["right"]
            cluster_bottom = cluster["bottom"]

            cluster_area = (
                metrics["area"]
            )

            if (
                cluster_area
                < self.MIN_CLUSTER_AREA
            ):

                print(
                    "[ChangeFilter] "
                    f"CLUSTER[{index}] rejected: "
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
                cluster_left
                - self.DIFF_PADDING,
            )

            result_top = max(
                0,
                cluster_top
                - self.DIFF_PADDING,
            )

            result_right = min(
                current_crop.width,
                cluster_right
                + self.DIFF_PADDING,
            )

            result_bottom = min(
                current_crop.height,
                cluster_bottom
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

        if (
            metrics["aspect_ratio"]
            > self.MAX_TEXT_ASPECT_RATIO
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

        Nearby runs on neighboring rows are connected using
        CLUSTER_DILATION.

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
        # IMPORTANT:
        #
        # previous_runs contains ONLY component IDs.
        #
        # current_runs contains ONLY coordinate tuples.
        #
        # current_component_ids contains ONLY component IDs.
        #
        # Keeping these separate prevents an integer component
        # ID from being accidentally processed as a run tuple.
        #

        previous_component_ids = []

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
                        y,
                    )
                )

            current_component_ids = []

            #
            # Process each run from the current row.
            #

            for (
                run_left,
                run_right,
                run_y,
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

                matching_components = []

                #
                # Compare against components active on
                # the previous row.
                #

                for component_index in (
                    previous_component_ids
                ):

                    root_index = (
                        self._find_component_root(
                            components,
                            component_index,
                        )
                    )

                    component = (
                        components[root_index]
                    )

                    component_left = (
                        component["left"]
                    )

                    component_right = (
                        component["right"]
                    )

                    #
                    # Only the horizontal extent of the
                    # component on the previous row is
                    # relevant here.
                    #
                    # Because components retain their overall
                    # bounds, use the previous-row run extents
                    # stored by the active component.
                    #

                    active_left = (
                        component.get(
                            "active_left",
                            component_left,
                        )
                    )

                    active_right = (
                        component.get(
                            "active_right",
                            component_right,
                        )
                    )

                    if (
                        expanded_right
                        < active_left
                        or expanded_left
                        > active_right
                    ):
                        continue

                    if (
                        root_index
                        not in matching_components
                    ):

                        matching_components.append(
                            root_index
                        )

                #
                # No matching previous component:
                # create a new component.
                #

                if not matching_components:

                    component_index = (
                        len(components)
                    )

                    components.append(
                        {
                            "left": run_left,
                            "top": run_y,
                            "right": run_right,
                            "bottom": run_y + 1,
                            "changed_pixels": (
                                run_right
                                - run_left
                            ),
                            "run_count": 1,
                            "active_left": run_left,
                            "active_right": run_right,
                            "parent": component_index,
                        }
                    )

                    current_component_ids.append(
                        component_index
                    )

                    continue

                #
                # Attach the run to the first matching
                # component.
                #

                current_component_index = (
                    matching_components[0]
                )

                component = (
                    components[
                        current_component_index
                    ]
                )

                component["left"] = min(
                    component["left"],
                    run_left,
                )

                component["top"] = min(
                    component["top"],
                    run_y,
                )

                component["right"] = max(
                    component["right"],
                    run_right,
                )

                component["bottom"] = max(
                    component["bottom"],
                    run_y + 1,
                )

                component["changed_pixels"] += (
                    run_right
                    - run_left
                )

                component["run_count"] += 1

                #
                # If the run connects multiple previous
                # components, merge them.
                #

                for other_index in (
                    matching_components[1:]
                ):

                    current_component_index = (
                        self._merge_components(
                            components,
                            current_component_index,
                            other_index,
                        )
                    )

                current_component_index = (
                    self._find_component_root(
                        components,
                        current_component_index,
                    )
                )

                #
                # The active horizontal extent for the
                # current row is the current run, not the
                # complete component bounds.
                #

                root_component = (
                    components[
                        current_component_index
                    ]
                )

                root_component["active_left"] = (
                    min(
                        root_component.get(
                            "active_left",
                            run_left,
                        ),
                        run_left,
                    )
                )

                root_component["active_right"] = (
                    max(
                        root_component.get(
                            "active_right",
                            run_right,
                        ),
                        run_right,
                    )
                )

                current_component_ids.append(
                    current_component_index
                )

            #
            # Prepare only the unique component IDs that
            # actually participated in this row.
            #

            previous_component_ids = list(
                dict.fromkeys(
                    current_component_ids
                )
            )

            #
            # Reset active extents for the next row.
            #
            # They will be replaced by the actual runs
            # belonging to that next row.
            #

            for component_index in (
                previous_component_ids
            ):

                root_index = (
                    self._find_component_root(
                        components,
                        component_index,
                    )
                )

                component = (
                    components[root_index]
                )

                component["active_left"] = (
                    component.get(
                        "_next_active_left",
                        component["active_left"],
                    )
                )

                component["active_right"] = (
                    component.get(
                        "_next_active_right",
                        component["active_right"],
                    )
                )

                component.pop(
                    "_next_active_left",
                    None,
                )

                component.pop(
                    "_next_active_right",
                    None,
                )

        #
        # Resolve merged components.
        #

        final_components = []

        seen_roots = set()

        for index, component in enumerate(
            components
        ):

            root = (
                self._find_component_root(
                    components,
                    index,
                )
            )

            if root in seen_roots:
                continue

            seen_roots.add(root)

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