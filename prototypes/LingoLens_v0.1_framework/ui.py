import tkinter as tk

import config
print(config.__file__)
print(dir(config))
from helpers import center_window
from menu import MenuBar
from statusbar import StatusBar
from about import AboutWindow
from settings import SettingsWindow

class MainWindow:

    def __init__(self):

        self.root = tk.Tk()
        self.root.iconbitmap(config.APP_ICON)

        self.root.title(config.APP_NAME)
        
        self.menu_bar = MenuBar(
            self.root,
            self
        )
        
        
        self.status_bar = StatusBar(self.root)
        
        self.about_window = AboutWindow(self.root)

        center_window(
            self.root,
            config.WINDOW_WIDTH,
            config.WINDOW_HEIGHT
        )
        
    def show_about(self):

        AboutWindow(self.root).show()   
        
    def show_settings(self):

        SettingsWindow(self.root).show()

    def run(self):
        self.root.mainloop()