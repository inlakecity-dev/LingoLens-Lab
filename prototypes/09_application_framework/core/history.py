"""
LingoLens History Engine

Provides reusable functions for saving and loading
translation history.
"""

from datetime import datetime
from pathlib import Path

from config import HISTORY_FOLDER


# Root history directory
HISTORY_FOLDER = Path(HISTORY_FOLDER)


def generate_history_filename():
    """
    Generate a unique history filename.

    Example:
        THD071626T18-30-10.txt
    """
    now = datetime.now()
    return now.strftime("THD%m%d%yT%H-%M-%S.txt")


def get_history_directory():
    """
    Create the history folder structure automatically.

    Structure:
        history/
            2026/
                July/
                    THD071626T18-30-10.txt

    Returns:
        pathlib.Path
    """
    now = datetime.now()

    year = str(now.year)
    month = now.strftime("%B")

    directory = HISTORY_FOLDER / year / month

    directory.mkdir(
        parents=True,
        exist_ok=True
    )

    return directory


def save_translation(
    original_text,
    translated_text,
    source_language,
    target_language,
):
    """
    Save a translation history file.

    Returns:
        pathlib.Path:
            Path of the saved history file.
    """

    now = datetime.now()

    directory = get_history_directory()

    filename = generate_history_filename()

    filepath = directory / filename

    with open(filepath, "w", encoding="utf-8") as file:

        file.write("=" * 60 + "\n")
        file.write("LingoLens Translation History\n")
        file.write("=" * 60 + "\n\n")

        file.write(f"Date            : {now.strftime('%d %B %Y')}\n")
        file.write(f"Time            : {now.strftime('%H:%M:%S')}\n\n")

        file.write(f"Source Language : {source_language}\n")
        file.write(f"Target Language : {target_language}\n\n")

        file.write("-" * 60 + "\n")
        file.write("Original Text\n")
        file.write("-" * 60 + "\n\n")
        file.write(original_text.strip())
        file.write("\n\n")

        file.write("-" * 60 + "\n")
        file.write("Translated Text\n")
        file.write("-" * 60 + "\n\n")
        file.write(translated_text.strip())
        file.write("\n\n")

        file.write("=" * 60 + "\n")

    return filepath


def load_history(filepath):
    """
    Load a history file.

    Args:
        filepath (str | pathlib.Path)

    Returns:
        str
    """

    with open(filepath, "r", encoding="utf-8") as file:
        return file.read()