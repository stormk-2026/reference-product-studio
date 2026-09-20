from typing import Literal

CanvasRatio = Literal["1:1", "3:4", "4:3", "4:5", "5:4", "2:3", "3:2", "9:16", "16:9"]

# Exact export dimensions; model output is fitted without stretching or cropping.
CANVAS_SIZES = {
    "1:1": (2048, 2048),
    "3:4": (1536, 2048),
    "4:3": (2048, 1536),
    "4:5": (2048, 2560),
    "5:4": (2560, 2048),
    "2:3": (1536, 2304),
    "3:2": (2304, 1536),
    "9:16": (1440, 2560),
    "16:9": (2560, 1440),
}


def canvas_size(ratio: CanvasRatio, *, fixture: bool = False) -> tuple[int, int]:
    width, height = CANVAS_SIZES[ratio]
    if fixture:
        # Retain legacy fixture sizes while supporting the same ratio catalog.
        factor = 0.4 if ratio in {"9:16", "16:9"} else 0.375
        return round(width * factor), round(height * factor)
    return width, height
