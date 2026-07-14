import tkinter as tk

import config
from helpers import center_window
from menu import MenuBar


class MainWindow:

    def __init__(self):

        self.root = tk.Tk()

        self.root.title(config.APP_NAME)
        
        MenuBar(self.root)

        center_window(
            self.root,
            config.WINDOW_WIDTH,
            config.WINDOW_HEIGHT
        )

    def run(self):
        self.root.mainloop()