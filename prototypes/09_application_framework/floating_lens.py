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
- Renders the appropriate translation.
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
            "380x260+250+200"
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

            #
            # Tkinter's HWND.
            #

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

            #
            # Resolve the native top-level/root HWND.
            #

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
                    "unable to resolve native root HWND."
                )

                return

            #
            # Verify the root HWND.
            #

            is_window = user32.IsWindow

            is_window.argtypes = [
                ctypes.c_void_p,
            ]

            is_window.restype = ctypes.c_int

            valid = bool(
                is_window(
                    ctypes.c_void_p(root_hwnd)
                )
            )

            logger.info(
                self.MODULE,
                "Floating Lens root HWND IsWindow: "
                f"{valid}"
            )

            if not valid:

                logger.error(
                    self.MODULE,
                    "Desktop Duplication exclusion failed: "
                    "resolved root HWND is invalid."
                )

                return

            #
            # WCA_EXCLUDED_FROM_DDA
            #

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

        self.translation_label = tk.Label(
            self.content,
            text="Waiting for translation...",
            font=("Segoe UI", 12),
            justify="center",
            wraplength=320
        )

        self.translation_label.pack(
            expand=True,
            padx=20,
            pady=20
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

        #
        # IMPORTANT:
        #
        # Apply Desktop Duplication exclusion only
        # after the Floating Lens is actually visible.
        #

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

    def render_entries(self, entries):

        if not entries:

            self.set_translation(
                ""
            )

            self.set_status(
                "No translation in view",
                "gray",
            )

            return

        translations = []

        for entry in entries:

            if entry.translation:

                translations.append(
                    entry.translation
                )

        if not translations:

            self.set_translation(
                ""
            )

            self.set_status(
                "No translation in view",
                "gray",
            )

            return

        self.set_translation(
            "\n\n".join(
                translations
            )
        )

        self.set_status(
            "Translation Available",
            "green",
        )

    # --------------------------------------------------
    # Translation Display
    # --------------------------------------------------

    def set_translation(
        self,
        text,
    ):

        if not text:

            text = "No translation in view."

        self.translation_label.config(
            text=text
        )

    def clear_translation(self):

        self.translation_label.config(
            text="Waiting for translation..."
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

        #
        # Tkinter-reported content coordinates.
        #

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

        #
        # Tkinter-reported top-level coordinates.
        #

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

        #
        # Native HWND diagnostics.
        #

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

            get_window_rect = (
                user32.GetWindowRect
            )

            get_window_rect.argtypes = [
                ctypes.c_void_p,
                ctypes.POINTER(RECT),
            ]

            get_window_rect.restype = (
                ctypes.c_bool
            )

            native_success = (
                get_window_rect(
                    ctypes.c_void_p(hwnd),
                    ctypes.byref(rect),
                )
            )

            if native_success:

                native_left = int(
                    rect.left
                )

                native_top = int(
                    rect.top
                )

                native_right = int(
                    rect.right
                )

                native_bottom = int(
                    rect.bottom
                )

        except Exception as error:

            logger.warning(
                self.MODULE,
                "Native Floating Lens coordinate "
                f"diagnostic failed: {error}"
            )

        #
        # Windows virtual desktop diagnostics.
        #

        virtual_left = 0
        virtual_top = 0
        virtual_width = 0
        virtual_height = 0

        try:

            user32 = ctypes.WinDLL(
                "user32",
                use_last_error=True,
            )

            #
            # SM_XVIRTUALSCREEN = 76
            # SM_YVIRTUALSCREEN = 77
            # SM_CXVIRTUALSCREEN = 78
            # SM_CYVIRTUALSCREEN = 79
            #

            virtual_left = int(
                user32.GetSystemMetrics(76)
            )

            virtual_top = int(
                user32.GetSystemMetrics(77)
            )

            virtual_width = int(
                user32.GetSystemMetrics(78)
            )

            virtual_height = int(
                user32.GetSystemMetrics(79)
            )

        except Exception as error:

            logger.warning(
                self.MODULE,
                "Windows virtual desktop coordinate "
                f"diagnostic failed: {error}"
            )

        logger.info(
            self.MODULE,
            "Floating Lens coordinate diagnostic: "
            f"tk_content=({tk_left}, {tk_top}, "
            f"{tk_width}, {tk_height}), "
            f"tk_window=({window_x}, {window_y}, "
            f"{window_width}, {window_height}), "
            f"hwnd={hwnd}, "
            f"native_window_rect=({native_left}, "
            f"{native_top}, {native_right}, "
            f"{native_bottom}), "
            f"windows_virtual_desktop=("
            f"{virtual_left}, {virtual_top}, "
            f"{virtual_width}, {virtual_height})"
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

        self.translation_label.configure(
            bg="#2B2B2B",
            fg="white"
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