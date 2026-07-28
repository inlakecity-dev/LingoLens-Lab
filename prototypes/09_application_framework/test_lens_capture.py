from core.lens_capture import LensCapture

capture = LensCapture()

image = capture.capture(
    left=100,
    top=100,
    width=400,
    height=200,
)

image.show()