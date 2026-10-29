from datetime import UTC, datetime
from typing import Any

import cv2
import numpy as np
from contracts.runtime import HealthStatus

from video_runtime.config import GigESourceConfig
from video_runtime.frame import Frame
from video_runtime.sources.base import SourceHealth

try:
    from harvesters.core import Harvester

    HARVESTERS_AVAILABLE = True
except ImportError:  # the gige extra is optional; file replay must still work
    Harvester = None
    HARVESTERS_AVAILABLE = False


def bayer_to_bgr(data: Any, pixel_format: str) -> Any:
    if pixel_format == "BGR8":
        return data
    if pixel_format == "Mono8":
        return cv2.cvtColor(data, cv2.COLOR_GRAY2BGR)
    if pixel_format == "BayerRG8":
        return cv2.cvtColor(data, cv2.COLOR_BayerRG2BGR)
    raise ValueError(f"unsupported pixel format: {pixel_format}")


class GigEHKSource:
    """Hikvision GigE Vision source through the MVS GenTL producer."""

    def __init__(
        self,
        config: GigESourceConfig,
        *,
        camera_id: str,
        acquirer: Any = None,
    ) -> None:
        self._config = config
        self._camera_id = camera_id
        self._harvester: Any = None
        self._acquirer: Any = acquirer
        self._frame_seq = 0
        self._last_frame_at: datetime | None = None
        self._error: str | None = None

    def start(self) -> None:
        if not HARVESTERS_AVAILABLE:
            raise RuntimeError(
                "harvesters is not installed; run `uv sync --extra gige` "
                "and check the MVS GenTL producer path"
            )
        try:
            harvester = Harvester()
            harvester.add_file(str(self._config.cti_path))
            harvester.update()
            self._acquirer = self._create_acquirer(harvester)
            self._configure(self._acquirer.remote_device.node_map)
        except Exception as exc:  # hardware boundary: producer errors vary by SDK
            self._error = str(exc)
            self.stop()
            raise RuntimeError(f"cannot start the GigE camera: {exc}") from exc
        self._harvester = harvester

    def read(self) -> Frame | None:
        if self._acquirer is None:
            return None
        try:
            # harvesters' fetch timeout is in seconds; the config is in ms
            buffer = self._acquirer.fetch(timeout=self._config.timeout_ms / 1000)
        except Exception as exc:  # hardware boundary: timeout/unplug/stream errors
            self._error = str(exc)
            return None
        if buffer is None:
            self._error = "camera acquisition timed out"
            return None

        try:
            component = buffer.payload.components[0]
            channels = component.num_components_per_pixel
            data = np.array(component.data).reshape(
                component.height, component.width, channels
            )
            if channels == 1:
                data = data[:, :, 0]
            image = bayer_to_bgr(data, self._config.pixel_format)
        finally:
            buffer.queue()

        height, width = image.shape[:2]
        captured_at = datetime.now(UTC)
        frame = Frame(
            camera_id=self._camera_id,
            frame_seq=self._frame_seq,
            captured_at=captured_at,
            width=width,
            height=height,
            pixel_format="BGR8",
            data=image,
        )
        self._frame_seq += 1
        self._last_frame_at = captured_at
        self._error = None
        return frame

    def stop(self) -> None:
        if self._acquirer is not None:
            try:
                self._acquirer.stop()
                self._acquirer.destroy()
            except Exception:  # hardware boundary: already stopping/stopped
                pass
            self._acquirer = None
        if self._harvester is not None:
            self._harvester.reset()
            self._harvester = None

    def health(self) -> SourceHealth:
        if self._error is not None:
            return SourceHealth(
                status=HealthStatus.UNAVAILABLE,
                last_frame_at=self._last_frame_at,
                error=self._error,
            )
        if self._acquirer is None:
            return SourceHealth(HealthStatus.STOPPED, last_frame_at=self._last_frame_at)
        if self._last_frame_at is None:
            return SourceHealth(HealthStatus.STARTING)
        return SourceHealth(HealthStatus.HEALTHY, last_frame_at=self._last_frame_at)

    def _create_acquirer(self, harvester: Any) -> Any:
        if self._config.serial:
            return harvester.create_image_acquirer(serial_number=self._config.serial)
        if self._config.ip:
            raise ValueError(
                "camera selection by IP is unsupported by the GenTL producer; "
                f"set serial instead of ip={self._config.ip}"
            )
        return harvester.create_image_acquirer()

    def _configure(self, node_map: Any) -> None:
        config = self._config
        # offsets first: many producers reject them once the full ROI is set
        node_map.OffsetX.value = config.offset_x
        node_map.OffsetY.value = config.offset_y
        node_map.Width.value = config.width
        node_map.Height.value = config.height
        node_map.PixelFormat.value = config.pixel_format
        _disable_auto(node_map, "ExposureAuto")
        node_map.ExposureTime.value = config.exposure_us
        _disable_auto(node_map, "GainAuto")
        node_map.Gain.value = config.gain_db
        node_map.GevSCPSPacketSize.value = config.packet_size


def _disable_auto(node_map: Any, node_name: str) -> None:
    node = getattr(node_map, node_name, None)
    if node is not None:
        node.value = "Off"
