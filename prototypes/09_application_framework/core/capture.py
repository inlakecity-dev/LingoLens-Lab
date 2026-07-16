from PIL import ImageGrab

def capture_fullscreen():
    """
    Capture the entire screen.

    Returns:
        PIL.Image: Screenshot of the full screen.
    """
    return ImageGrab.grab()
    
    
def capture_region(x1, y1, x2, y2):
    """
    Capture a selected screen region.

    Args:
        x1, y1: Top-left coordinates.
        x2, y2: Bottom-right coordinates.

    Returns:
        PIL.Image: Screenshot of the selected region.
    """
    return ImageGrab.grab(
        bbox=(x1, y1, x2, y2)
    )
    
