import time
from collections.abc import Iterator

from video_runtime.state import RuntimeState


def mjpeg_chunks(
    state: RuntimeState,
    camera_id: str,
    *,
    fps: int = 10,
    max_chunks: int | None = None,
) -> Iterator[bytes]:
    """Yields multipart JPEG parts; `max_chunks` is the test seam only."""
    interval = 1.0 / fps
    sent = 0
    while max_chunks is None or sent < max_chunks:
        jpeg = state.jpeg(camera_id)
        if jpeg is None:
            if max_chunks is not None:
                return
            time.sleep(interval)
            continue
        yield (
            b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
            + str(len(jpeg)).encode()
            + b"\r\n\r\n"
            + jpeg
            + b"\r\n"
        )
        sent += 1
        time.sleep(interval)
