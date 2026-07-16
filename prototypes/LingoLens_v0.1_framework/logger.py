"""
logger.py

Central logging system for LingoLens.
"""

from pathlib import Path
from datetime import datetime


class Logger:
    """
    Handles application logging.
    """

    def __init__(self):

        # Create logs folder if it doesn't exist
        self.log_folder = Path("logs")
        self.log_folder.mkdir(exist_ok=True)

        # Create today's log file
        today = datetime.now().strftime("%Y-%m-%d")
        self.log_file = self.log_folder / f"{today}.log"

        # Session start time
        self.session_start = None

    def start_session(self):
        """
        Starts a new application session.
        """

        self.session_start = datetime.now()

        header = (
            "\n"
            + "=" * 60 + "\n"
            + "LingoLens v0.9\n"
            + f"Session Started : {self.session_start.strftime('%Y-%m-%d %H:%M:%S')}\n"
            + "=" * 60
        )

        print(header)

        with open(self.log_file, "a", encoding="utf-8") as file:
            file.write(header + "\n")

    def end_session(self):
        """
        Ends the current application session.
        """

        end_time = datetime.now()

        duration = end_time - self.session_start

        footer = (
            "=" * 60 + "\n"
            + f"Session Ended   : {end_time.strftime('%Y-%m-%d %H:%M:%S')}\n"
            + f"Duration        : {duration}\n"
            + "=" * 60 + "\n"
        )

        print(footer)

        with open(self.log_file, "a", encoding="utf-8") as file:
            file.write(footer)

    def _write(self, level, module, message):
        """
        Writes a formatted log entry.
        """

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        line = (
            f"{timestamp} | "
            f"{level:<7} | "
            f"[{module}] "
            f"{message}"
        )

        print(line)

        with open(self.log_file, "a", encoding="utf-8") as file:
            file.write(line + "\n")

    def info(self, module, message):
        self._write("INFO", module, message)

    def warning(self, module, message):
        self._write("WARNING", module, message)

    def error(self, module, message):
        self._write("ERROR", module, message)

    def user(self, message):
        self._write("USER", "USER", message)


logger = Logger()