import tkinter as tk

import config
from helpers import center_window
from menu import MenuBar
from statusbar import StatusBar
from about import AboutWindow
from settings_window import SettingsWindow
from controller import translate_region
from core.region_selector import select_region
from core.display import enable_dpi_awareness
from translation_view import TranslationView
from app_settings import AppSettings


class MainWindow:

    def __init__(self):
        
        self.app_settings = AppSettings()
        
        enable_dpi_awareness()
        
        self.root = tk.Tk()
        self.root.iconbitmap(config.APP_ICON)

        self.root.title(config.APP_NAME)
       
        
        self.menu_bar = MenuBar(
            self.root,
            self
        )
        
        
        self.status_bar = StatusBar(self.root)
        self.translation_view = TranslationView(self.root)
        self.translation_view.pack(fill="both", expand=True)
        

        center_window(
            self.root,
            config.WINDOW_WIDTH,
            config.WINDOW_HEIGHT
        )
      # Current session state
        self.ocr_language =  None
        
    def show_about(self):

        AboutWindow(self.root).show()   
        
    def show_settings(self):

        SettingsWindow(
            self.root,
            self.app_settings
        ).show()
        
    def start_rectangle_translation(self):

        selection = select_region(self.root)

        if selection is None:
            return

        x1, y1, x2, y2 = selection

        result = translate_region(
            x1,
            y1,
            x2,
            y2,
        )

        self.translation_view.update(result)   

    def run(self):
        self.root.mainloop()