"""
floating_lens.py

Floating Lens window.

The Floating Lens is a viewport over the TranslationMap.

It does NOT:
- Capture the desktop.
- Perform OCR.
- Perform Translation.
- Create TranslationMap entries.

It only:
- Determines its current desktop position and dimensions.
- Queries the TranslationMap for visible translations.
- Renders each translation at its source-relative position.
- Uses a fixed readable font size for Lens rendering.
- Refreshes when the TranslationMap actually changes.
"""

import ctypes
import tkinter as tk

from theme import (
    register_widget,
    unregister_widget,
)

from logger import logger


class FloatingLensWindow:
    """
    Floating Lens overlay window.

    The lens acts only as a viewport over the
    TranslationMap.
    """

    MODULE = "LENS"

    # --------------------------------------------------
    # Translation Rendering
    # --------------------------------------------------

    TRANSLATION_FONT_FAMILY = "Segoe UI"

    #
    # Fixed display font size for the Floating Lens.
    #
    # This is intentionally independent of OCR/source
    # geometry. TranslationMap entry bounds continue to
    # represent the original source geometry and are not
    # used to scale the rendered translation text.
    #

    DEFAULT_LENS_FONT_SIZE = 12

    TRANSLATION_TEXT_COLOR = "white"

    # --------------------------------------------------
    # Font Grouping
    # --------------------------------------------------

    #
    # Maximum vertical separation allowed between adjacent
    # OCR entries before they are considered separate
    # visual groups.
    #

    FONT_GROUP_MAX_GAP = 12

    #
    # Allows OCR boxes belonging to the same visual text
    # block to have slightly different horizontal positions.
    #

    FONT_GROUP_HORIZONTAL_TOLERANCE = 30

    # --------------------------------------------------
    # Window
    # --------------------------------------------------

    def __init__(
        self,
        parent,
        app_settings,
        lens_controller,
    ):

        self.parent = parent
        self.app_settings = app_settings
        self.lens_controller = lens_controller

        self.is_open = False

        self.window = None

        self._drag_x = 0
        self._drag_y = 0

        self._map_listener_registered = False
        self._map_refresh_pending = False

        self.create_window()
        self.create_widgets()

        register_widget(self)

        self.apply_theme()

    # --------------------------------------------------
    # Window
    # --------------------------------------------------

    def create_window(self):

        self.window = tk.Toplevel(
            self.parent
        )

        self.window.withdraw()

        self.window.overrideredirect(True)

        self.window.attributes(
            "-topmost",
            True
        )

        self.window.geometry(
            "700x500+250+200"
        )

        self.window.protocol(
            "WM_DELETE_WINDOW",
            self.close
        )

    # --------------------------------------------------
    # Desktop Duplication Exclusion
    # --------------------------------------------------

    def _exclude_from_desktop_duplication(self):
        """
        Exclude the visible Floating Lens top-level
        window from Windows Desktop Duplication.

        The exclusion is intentionally applied only
        after the Floating Lens has been made visible.

        The desktop underneath the Floating Lens remains
        part of the observable desktop source.
        """

        if self.window is None:
            return

        try:

            self.window.update_idletasks()
            self.window.update()

            tk_hwnd = int(
                self.window.winfo_id()
            )

            logger.info(
                self.MODULE,
                "Floating Lens Tk HWND: "
                f"{tk_hwnd}"
            )

            if not tk_hwnd:

                logger.error(
                    self.MODULE,
                    "Desktop Duplication exclusion failed: "
                    "invalid Tk HWND."
                )

                return

            user32 = ctypes.WinDLL(
                "user32",
                use_last_error=True,
            )

            get_ancestor = user32.GetAncestor

            get_ancestor.argtypes = [
                ctypes.c_void_p,
                ctypes.c_uint,
            ]

            get_ancestor.restype = ctypes.c_void_p

            GA_ROOT = 2

            root_hwnd_raw = get_ancestor(
                ctypes.c_void_p(tk_hwnd),
                GA_ROOT,
            )

            root_hwnd = (
                int(root_hwnd_raw)
                if root_hwnd_raw
                else 0
            )

            logger.info(
                self.MODULE,
                "Floating Lens root HWND: "
                f"{root_hwnd}"
            )

            if not root_hwnd:

                logger.error(
                    self.MODULE,
                    "Desktop Duplication exclusion failed: "
                    "invalid root HWND."
                )

                return

            WCA_EXCLUDED_FROM_DDA = 24

            class WINDOWCOMPOSITIONATTRIBDATA(
                ctypes.Structure
            ):
                _fields_ = [
                    (
                        "Attrib",
                        ctypes.c_uint32,
                    ),
                    (
                        "pvData",
                        ctypes.c_void_p,
                    ),
                    (
                        "cbData",
                        ctypes.c_size_t,
                    ),
                ]

            excluded = ctypes.c_int(1)

            data = WINDOWCOMPOSITIONATTRIBDATA(
                Attrib=WCA_EXCLUDED_FROM_DDA,
                pvData=ctypes.cast(
                    ctypes.pointer(excluded),
                    ctypes.c_void_p,
                ),
                cbData=ctypes.sizeof(
                    excluded
                ),
            )

            try:

                set_window_composition_attribute = (
                    user32.SetWindowCompositionAttribute
                )

            except AttributeError:

                logger.error(
                    self.MODULE,
                    "Desktop Duplication exclusion failed: "
                    "SetWindowCompositionAttribute is "
                    "not available."
                )

                return

            set_window_composition_attribute.argtypes = [
                ctypes.c_void_p,
                ctypes.POINTER(
                    WINDOWCOMPOSITIONATTRIBDATA
                ),
            ]

            set_window_composition_attribute.restype = (
                ctypes.c_int
            )

            ctypes.set_last_error(0)

            result = set_window_composition_attribute(
                ctypes.c_void_p(root_hwnd),
                ctypes.byref(data),
            )

            error_code = ctypes.get_last_error()

            logger.info(
                self.MODULE,
                "Desktop Duplication exclusion request: "
                f"HWND={root_hwnd}, "
                f"attribute={WCA_EXCLUDED_FROM_DDA}, "
                f"result={result}, "
                f"last_error={error_code}"
            )

            if result:

                logger.info(
                    self.MODULE,
                    "Floating Lens successfully configured "
                    "for Desktop Duplication exclusion."
                )

            else:

                logger.error(
                    self.MODULE,
                    "Windows rejected the Floating Lens "
                    "Desktop Duplication exclusion request. "
                    f"last_error={error_code}"
                )

        except Exception as error:

            logger.error(
                self.MODULE,
                "Desktop Duplication exclusion "
                f"configuration failed: {error}"
            )

    # --------------------------------------------------
    # Widgets
    # --------------------------------------------------

    def create_widgets(self):

        self.title_bar = tk.Frame(
            self.window,
            height=34,
            cursor="fleur"
        )

        self.title_bar.pack(
            fill="x"
        )

        self.title_label = tk.Label(
            self.title_bar,
            text="🔍 LingoLens",
            font=("Segoe UI", 10, "bold")
        )

        self.title_label.pack(
            side="left",
            padx=10,
            pady=6
        )

        self.close_button = tk.Button(
            self.title_bar,
            text="✕",
            bd=0,
            relief="flat",
            padx=8,
            command=self.close
        )

        self.close_button.pack(
            side="right",
            padx=6,
            pady=4
        )

        self.content = tk.Frame(
            self.window
        )

        self.content.pack(
            fill="both",
            expand=True
        )

        self.translation_canvas = tk.Canvas(
            self.content,
            bd=0,
            highlightthickness=0,
            relief="flat",
        )

        self.translation_canvas.pack(
            fill="both",
            expand=True
        )

        self.status_bar = tk.Frame(
            self.window,
            height=24
        )

        self.status_bar.pack(
            fill="x",
            side="bottom"
        )

        self.status_indicator = tk.Label(
            self.status_bar,
            text="●",
            font=("Segoe UI", 10)
        )

        self.status_indicator.pack(
            side="left",
            padx=(8, 4)
        )

        self.status_label = tk.Label(
            self.status_bar,
            text="Ready",
            anchor="w",
            font=("Segoe UI", 9)
        )

        self.status_label.pack(
            side="left"
        )

        self.title_bar.bind(
            "<ButtonPress-1>",
            self.start_move
        )

        self.title_bar.bind(
            "<B1-Motion>",
            self.on_move
        )

        self.title_label.bind(
            "<ButtonPress-1>",
            self.start_move
        )

        self.title_label.bind(
            "<B1-Motion>",
            self.on_move
        )

    # --------------------------------------------------
    # Window Controls
    # --------------------------------------------------

    def show(self):

        if self.is_open:
            return

        self.is_open = True

        logger.info(
            self.MODULE,
            "Floating Lens opening."
        )

        self.lens_controller.start()

        self.register_translation_map_listener()

        self.window.deiconify()

        self.window.update_idletasks()
        self.window.update()

        self._exclude_from_desktop_duplication()

        self.update_viewport()

    def hide(self):

        self.is_open = False

        self.unregister_translation_map_listener()

        self.lens_controller.stop()

        self.window.withdraw()

        logger.info(
            self.MODULE,
            "Floating Lens hidden."
        )

    def toggle(self):

        if self.is_open:
            self.hide()
        else:
            self.show()

    def close(self):

        self.hide()

    # --------------------------------------------------
    # TranslationMap Listener
    # --------------------------------------------------

    def get_translation_map(self):

        controller = getattr(
            self.lens_controller,
            "controller",
            None,
        )

        if controller is None:

            logger.warning(
                self.MODULE,
                "TranslationMap lookup failed: "
                "Lens controller has no controller."
            )

            return None

        translation_map = getattr(
            controller,
            "translation_map",
            None,
        )

        if translation_map is None:

            logger.warning(
                self.MODULE,
                "TranslationMap lookup failed: "
                "controller.translation_map is None."
            )

        return translation_map

    def register_translation_map_listener(self):

        if self._map_listener_registered:
            return

        translation_map = (
            self.get_translation_map()
        )

        if translation_map is None:
            return

        translation_map.add_change_listener(
            self.on_translation_map_changed
        )

        self._map_listener_registered = True

        logger.info(
            self.MODULE,
            "TranslationMap change listener registered."
        )

    def unregister_translation_map_listener(self):

        if not self._map_listener_registered:
            return

        translation_map = (
            self.get_translation_map()
        )

        if translation_map is not None:

            translation_map.remove_change_listener(
                self.on_translation_map_changed
            )

        self._map_listener_registered = False
        self._map_refresh_pending = False

        logger.info(
            self.MODULE,
            "TranslationMap change listener unregistered."
        )

    def on_translation_map_changed(self):

        if not self.is_open:
            return

        if self._map_refresh_pending:
            return

        self._map_refresh_pending = True

        logger.info(
            self.MODULE,
            "TranslationMap changed. "
            "Scheduling Floating Lens refresh."
        )

        try:

            self.window.after(
                0,
                self._refresh_after_map_change
            )

        except tk.TclError:

            self._map_refresh_pending = False

    def _refresh_after_map_change(self):

        self._map_refresh_pending = False

        if not self.is_open:
            return

        logger.info(
            self.MODULE,
            "Refreshing Floating Lens after "
            "TranslationMap change."
        )

        self.update_viewport()

    # --------------------------------------------------
    # TranslationMap Viewport
    # --------------------------------------------------

    def update_viewport(self):

        if not self.is_open:
            return

        bounds = self.get_viewport_bounds()

        logger.info(
            self.MODULE,
            "Floating Lens viewport query: "
            f"bounds={bounds}"
        )

        entries = (
            self.lens_controller.get_visible_translations(
                bounds
            )
        )

        entry_count = (
            len(entries)
            if entries is not None
            else 0
        )

        logger.info(
            self.MODULE,
            "Floating Lens viewport result: "
            f"entries={entry_count}"
        )

        if entries:

            for index, entry in enumerate(
                entries,
                start=1
            ):

                entry_bounds = getattr(
                    entry,
                    "bounds",
                    None
                )

                translation = getattr(
                    entry,
                    "translation",
                    ""
                )

                logger.info(
                    self.MODULE,
                    "Visible entry "
                    f"[{index}]: "
                    f"bounds={entry_bounds}, "
                    f"translation_length="
                    f"{len(translation)}"
                )

        self.render_entries(
            entries
        )

    # --------------------------------------------------
    # Font Grouping Helpers
    # --------------------------------------------------

    def _get_entry_bounds(
        self,
        entry,
    ):
        """
        Return valid TranslationMap bounds or None.
        """

        bounds = getattr(
            entry,
            "bounds",
            None
        )

        if not bounds or len(bounds) != 4:

            return None

        try:

            left = float(bounds[0])
            top = float(bounds[1])
            width = float(bounds[2])
            height = float(bounds[3])

        except (
            TypeError,
            ValueError,
        ):

            return None

        if width <= 0 or height <= 0:

            return None

        return (
            left,
            top,
            width,
            height,
        )

    def _entries_are_same_font_group(
        self,
        entry,
        group,
    ):
        """
        Determine whether an entry belongs to the same
        visual text group as the existing group.

        Grouping uses only source geometry.

        It does not modify TranslationMap entries or
        their positions.

        The grouping is retained for future Lens layout
        work, but it no longer determines font size.
        """

        entry_bounds = self._get_entry_bounds(
            entry
        )

        if entry_bounds is None:
            return False

        if not group:
            return True

        (
            entry_left,
            entry_top,
            entry_width,
            entry_height,
        ) = entry_bounds

        group_bounds = [
            self._get_entry_bounds(
                item
            )
            for item in group
        ]

        group_bounds = [
            bounds
            for bounds in group_bounds
            if bounds is not None
        ]

        if not group_bounds:
            return False

        group_left = min(
            bounds[0]
            for bounds in group_bounds
        )

        group_right = max(
            bounds[0] + bounds[2]
            for bounds in group_bounds
        )

        group_top = min(
            bounds[1]
            for bounds in group_bounds
        )

        group_bottom = max(
            bounds[1] + bounds[3]
            for bounds in group_bounds
        )

        #
        # Vertical relationship.
        #

        entry_bottom = (
            entry_top
            + entry_height
        )

        if entry_top >= group_bottom:

            vertical_gap = (
                entry_top
                - group_bottom
            )

        elif group_top >= entry_bottom:

            vertical_gap = (
                group_top
                - entry_bottom
            )

        else:

            vertical_gap = 0

        if vertical_gap > max(
            self.FONT_GROUP_MAX_GAP,
            min(
                entry_height,
                max(
                    bounds[3]
                    for bounds in group_bounds
                ),
            ) * 0.75,
        ):

            return False

        #
        # Horizontal relationship.
        #

        entry_right = (
            entry_left
            + entry_width
        )

        horizontal_overlap = (
            min(
                entry_right,
                group_right,
            )
            - max(
                entry_left,
                group_left,
            )
        )

        left_alignment = abs(
            entry_left
            - group_left
        )

        if (
            horizontal_overlap <= 0
            and left_alignment
            > self.FONT_GROUP_HORIZONTAL_TOLERANCE
        ):

            return False

        return True

    def _group_entries_for_font_sizing(
        self,
        entries,
    ):
        """
        Group visually related TranslationMap entries.

        Grouping is retained as a source-geometry helper,
        but representative OCR height no longer controls
        Lens font size.
        """

        groups = []

        current_group = []

        sorted_entries = (
            self._sort_entries_for_rendering(
                entries
            )
        )

        for entry in sorted_entries:

            if not self._get_entry_bounds(
                entry
            ):

                if current_group:

                    groups.append(
                        current_group
                    )

                    current_group = []

                continue

            if not current_group:

                current_group = [
                    entry
                ]

                continue

            if self._entries_are_same_font_group(
                entry,
                current_group,
            ):

                current_group.append(
                    entry
                )

            else:

                groups.append(
                    current_group
                )

                current_group = [
                    entry
                ]

        if current_group:

            groups.append(
                current_group
            )

        logger.info(
            self.MODULE,
            "Floating Lens visual grouping: "
            f"groups={len(groups)}, "
            f"entries={len(sorted_entries)}, "
            f"font_size="
            f"{self.DEFAULT_LENS_FONT_SIZE}"
        )

        return groups

    # --------------------------------------------------
    # Entry Sorting
    # --------------------------------------------------

    def _sort_entries_for_rendering(
        self,
        entries,
    ):
        """
        Sort TranslationMap entries in normal reading order.

        Entries are ordered from top to bottom and then
        left to right.
        """

        def sort_key(entry):

            bounds = getattr(
                entry,
                "bounds",
                None
            )

            if not bounds or len(bounds) != 4:

                return (
                    float("inf"),
                    float("inf"),
                )

            return (
                bounds[1],
                bounds[0],
            )

        return sorted(
            entries,
            key=sort_key,
        )

    # --------------------------------------------------
    # Entry Rendering
    # --------------------------------------------------

    def _render_translation_entry(
        self,
        entry,
        viewport_bounds,
        font_size,
    ):
        """
        Render one TranslationMap entry.

        The original source-relative position is preserved.

        The font size is controlled independently from
        source OCR geometry.
        """

        translation = getattr(
            entry,
            "translation",
            ""
        )

        if not translation:

            return None

        entry_bounds = self._get_entry_bounds(
            entry
        )

        if entry_bounds is None:

            logger.warning(
                self.MODULE,
                "Skipping TranslationMap entry because "
                "bounds are invalid."
            )

            return None

        (
            entry_left,
            entry_top,
            entry_width,
            entry_height,
        ) = entry_bounds

        (
            viewport_left,
            viewport_top,
            viewport_width,
            viewport_height,
        ) = viewport_bounds

        #
        # Preserve exact source-relative position.
        #

        relative_left = (
            entry_left
            - viewport_left
        )

        relative_top = (
            entry_top
            - viewport_top
        )

        font = (
            self.TRANSLATION_FONT_FAMILY,
            font_size,
        )

        logger.info(
            self.MODULE,
            "Rendering translation entry: "
            f"source_bounds={entry.bounds}, "
            f"viewport={viewport_bounds}, "
            f"relative_position=("
            f"{relative_left}, "
            f"{relative_top}), "
            f"font_size={font_size}, "
            f"clamped=False"
        )

        return self.translation_canvas.create_text(
            relative_left,
            relative_top,
            anchor="nw",
            text=translation,
            font=font,
            fill=self.TRANSLATION_TEXT_COLOR,
        )

    # --------------------------------------------------
    # Render Entries
    # --------------------------------------------------

    def render_entries(
        self,
        entries,
    ):

        self.translation_canvas.delete(
            "all"
        )

        if not entries:

            self.set_translation(
                ""
            )

            self.set_status(
                "No translation in view",
                "gray",
            )

            return

        viewport_bounds = (
            self.get_viewport_bounds()
        )

        entries = (
            self._sort_entries_for_rendering(
                entries
            )
        )

        #
        # Source geometry is used only for positioning
        # and visual ordering.
        #
        # Lens display font size is fixed independently.
        #

        font_size = (
            self.DEFAULT_LENS_FONT_SIZE
        )

        rendered_count = 0

        for entry in entries:

            item_id = (
                self._render_translation_entry(
                    entry,
                    viewport_bounds,
                    font_size,
                )
            )

            if item_id is not None:

                rendered_count += 1

        if rendered_count == 0:

            self.set_translation(
                ""
            )

            self.set_status(
                "No translation in view",
                "gray",
            )

            return

        self.set_status(
            "Translation Available",
            "green",
        )

        logger.info(
            self.MODULE,
            "Floating Lens rendered "
            f"{rendered_count} translation entry(ies) "
            f"at font_size={font_size}."
        )

    # --------------------------------------------------
    # Translation Display
    # --------------------------------------------------

    def set_translation(
        self,
        text,
    ):

        self.translation_canvas.delete(
            "all"
        )

        if not text:

            text = "No translation in view."

        self.translation_canvas.create_text(
            self.translation_canvas.winfo_width() // 2,
            self.translation_canvas.winfo_height() // 2,
            anchor="center",
            text=text,
            font=(
                self.TRANSLATION_FONT_FAMILY,
                12,
            ),
            fill=self.TRANSLATION_TEXT_COLOR,
        )

    def clear_translation(self):

        self.translation_canvas.delete(
            "all"
        )

        self.translation_canvas.create_text(
            self.translation_canvas.winfo_width() // 2,
            self.translation_canvas.winfo_height() // 2,
            anchor="center",
            text="Waiting for translation...",
            font=(
                self.TRANSLATION_FONT_FAMILY,
                12,
            ),
            fill=self.TRANSLATION_TEXT_COLOR,
        )

    def set_status(
        self,
        status,
        color="green",
    ):

        self.status_label.config(
            text=status
        )

        self.status_indicator.config(
            fg=color
        )

    # --------------------------------------------------
    # Dragging
    # --------------------------------------------------

    def start_move(
        self,
        event,
    ):

        self._drag_x = event.x
        self._drag_y = event.y

    def on_move(
        self,
        event,
    ):

        x = (
            self.window.winfo_x()
            + event.x
            - self._drag_x
        )

        y = (
            self.window.winfo_y()
            + event.y
            - self._drag_y
        )

        self.window.geometry(
            f"+{x}+{y}"
        )

        self.window.update_idletasks()

        logger.info(
            self.MODULE,
            "Floating Lens moved: "
            f"window_position=({x}, {y})"
        )

        self.update_viewport()

    # --------------------------------------------------
    # Viewport Bounds
    # --------------------------------------------------

    def get_viewport_bounds(
        self,
    ) -> tuple[int, int, int, int]:

        self.window.update_idletasks()

        tk_left = (
            self.content.winfo_rootx()
        )

        tk_top = (
            self.content.winfo_rooty()
        )

        tk_width = (
            self.content.winfo_width()
        )

        tk_height = (
            self.content.winfo_height()
        )

        window_x = (
            self.window.winfo_x()
        )

        window_y = (
            self.window.winfo_y()
        )

        window_width = (
            self.window.winfo_width()
        )

        window_height = (
            self.window.winfo_height()
        )

        hwnd = 0
        native_left = 0
        native_top = 0
        native_right = 0
        native_bottom = 0

        try:

            hwnd = int(
                self.window.winfo_id()
            )

            user32 = ctypes.WinDLL(
                "user32",
                use_last_error=True,
            )

            class RECT(
                ctypes.Structure
            ):
                _fields_ = [
                    (
                        "left",
                        ctypes.c_long,
                    ),
                    (
                        "top",
                        ctypes.c_long,
                    ),
                    (
                        "right",
                        ctypes.c_long,
                    ),
                    (
                        "bottom",
                        ctypes.c_long,
                    ),
                ]

            rect = RECT()

            result = user32.GetWindowRect(
                ctypes.c_void_p(hwnd),
                ctypes.byref(rect),
            )

            if result:

                native_left = rect.left
                native_top = rect.top
                native_right = rect.right
                native_bottom = rect.bottom

        except Exception as error:

            logger.warning(
                self.MODULE,
                "Native Floating Lens coordinate "
                f"diagnostic failed: {error}"
            )

        native_window_rect = (
            native_left,
            native_top,
            native_right,
            native_bottom,
        )

        virtual_left = 0
        virtual_top = 0
        virtual_right = 0
        virtual_bottom = 0

        try:

            user32 = ctypes.WinDLL(
                "user32",
                use_last_error=True,
            )

            SM_XVIRTUALSCREEN = 76
            SM_YVIRTUALSCREEN = 77
            SM_CXVIRTUALSCREEN = 78
            SM_CYVIRTUALSCREEN = 79

            virtual_left = user32.GetSystemMetrics(
                SM_XVIRTUALSCREEN
            )

            virtual_top = user32.GetSystemMetrics(
                SM_YVIRTUALSCREEN
            )

            virtual_width = user32.GetSystemMetrics(
                SM_CXVIRTUALSCREEN
            )

            virtual_height = user32.GetSystemMetrics(
                SM_CYVIRTUALSCREEN
            )

            virtual_right = (
                virtual_left
                + virtual_width
            )

            virtual_bottom = (
                virtual_top
                + virtual_height
            )

        except Exception as error:

            logger.warning(
                self.MODULE,
                "Windows virtual desktop diagnostic "
                f"failed: {error}"
            )

        windows_virtual_desktop = (
            virtual_left,
            virtual_top,
            virtual_right,
            virtual_bottom,
        )

        logger.info(
            self.MODULE,
            "Floating Lens coordinate diagnostic: "
            f"tk_content=("
            f"{tk_left}, "
            f"{tk_top}, "
            f"{tk_width}, "
            f"{tk_height}), "
            f"tk_window=("
            f"{window_x}, "
            f"{window_y}, "
            f"{window_width}, "
            f"{window_height}), "
            f"hwnd={hwnd}, "
            f"native_window_rect="
            f"{native_window_rect}, "
            f"windows_virtual_desktop="
            f"{windows_virtual_desktop}"
        )

        bounds = (
            tk_left,
            tk_top,
            tk_width,
            tk_height,
        )

        logger.info(
            self.MODULE,
            "Floating Lens content bounds: "
            f"{bounds}"
        )

        return bounds

    # --------------------------------------------------
    # Theme
    # --------------------------------------------------

    def apply_theme(self):

        self.window.configure(
            bg="#2B2B2B"
        )

        self.title_bar.configure(
            bg="#202020"
        )

        self.title_label.configure(
            bg="#202020",
            fg="white"
        )

        self.close_button.configure(
            bg="#202020",
            fg="white",
            activebackground="#404040",
            activeforeground="white"
        )

        self.content.configure(
            bg="#2B2B2B"
        )

        self.translation_canvas.configure(
            bg="#2B2B2B"
        )

        self.status_bar.configure(
            bg="#202020"
        )

        self.status_label.configure(
            bg="#202020",
            fg="#DDDDDD"
        )

        self.status_indicator.configure(
            bg="#202020",
            fg="green"
        )

    # --------------------------------------------------
    # Cleanup
    # --------------------------------------------------

    def destroy(self):

        self.unregister_translation_map_listener()

        unregister_widget(self)

        if self.window is not None:

            self.window.destroy()