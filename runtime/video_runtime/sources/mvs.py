"""HIKROBOT MVS SDK source.

The MVS GenTL producer returns device metadata in a non-UTF-8 codepage that
genicam's SWIG bindings cannot decode on CPython 3.12, so the HIKROBOT demo
camera is opened through the vendor SDK instead of harvesters. Standard GenTL
producers keep using `GigEHKSource`.
"""

import ctypes
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

import cv2
import numpy as np
from contracts.runtime import HealthStatus

from video_runtime.config import MvsSourceConfig
from video_runtime.frame import Frame
from video_runtime.sources.base import SourceHealth
from video_runtime.sources.gige import bayer_to_bgr

_EXPOSURE_AUTO_OFF = 0
_GAIN_AUTO_OFF = 0

# GenICam PFNC values reported in MV_FRAME_OUT.stFrameInfo.enPixelType.
_MONO8 = 0x01080001
_BAYER_RG8 = 0x01080009
_YUV422_YUYV_PACKED = 0x02100032
_YUV422_PACKED = 0x0210003F
_RGB8_PACKED = 0x02180014
_BGR8_PACKED = 0x02180015


class CameraKit(Protocol):
    """The SDK adapter the source needs; tests inject a fake."""

    def open(self) -> None: ...

    def grab(self, timeout_ms: int) -> np.ndarray | None: ...

    def close(self) -> None: ...


def load_sdk() -> Any:
    """Import HIKROBOT's ctypes bindings from PATH or the MVS install."""
    try:
        import MvCameraControl_class as sdk
    except ImportError:
        root = os.environ.get("MVCAM_COMMON_RUNENV")
        if not root:
            raise RuntimeError(
                "MVS SDK Python bindings not found; install the HIKROBOT MVS SDK "
                "or set MVCAM_COMMON_RUNENV"
            ) from None
        sys.path.append(str(Path(root) / "Samples" / "Python" / "MvImport"))
        import MvCameraControl_class as sdk
    return sdk


def matches_device(
    config: MvsSourceConfig, *, serial_number: str, current_ip: str
) -> bool:
    if config.serial is not None:
        return serial_number == config.serial
    if config.ip is not None:
        return current_ip == config.ip
    return True


def _text(chars: Any) -> str:
    return "".join(chr(value) for value in chars if value)


def _ipv4(value: int) -> str:
    return ".".join(str((value >> shift) & 0xFF) for shift in (24, 16, 8, 0))


def _check(ret: int, action: str) -> None:
    if ret != 0:
        raise RuntimeError(f"{action} failed: 0x{ret:x}")


def to_bgr(raw: np.ndarray, width: int, height: int, pixel_type: int) -> np.ndarray:
    """Decode one frame using the format the camera is actually streaming."""
    if pixel_type in {_MONO8, _BAYER_RG8}:
        size = width * height
        _require(raw, size, width, height, pixel_type)
        plane = raw[:size].reshape(height, width)
        return bayer_to_bgr(plane, "Mono8" if pixel_type == _MONO8 else "BayerRG8")
    if pixel_type in {_RGB8_PACKED, _BGR8_PACKED}:
        size = width * height * 3
        _require(raw, size, width, height, pixel_type)
        packed = raw[:size].reshape(height, width, 3)
        # These two arrive in the opposite order to their GenICam names.
        return (
            packed
            if pixel_type == _RGB8_PACKED
            else cv2.cvtColor(packed, cv2.COLOR_RGB2BGR)
        )
    if pixel_type in {_YUV422_YUYV_PACKED, _YUV422_PACKED}:
        size = width * height * 2
        _require(raw, size, width, height, pixel_type)
        packed = raw[:size].reshape(height, width, 2)
        code = (
            cv2.COLOR_YUV2BGR_YUYV
            if pixel_type == _YUV422_YUYV_PACKED
            else cv2.COLOR_YUV2BGR_UYVY
        )
        return cv2.cvtColor(packed, code)
    raise RuntimeError(
        f"unsupported camera pixel type 0x{pixel_type:x}; "
        "select an 8-bit colour or BayerRG8 format on the camera"
    )


def _require(
    raw: np.ndarray, size: int, width: int, height: int, pixel_type: int
) -> None:
    if raw.size < size:
        raise RuntimeError(
            f"frame data {raw.size} bytes is smaller than {width}x{height} "
            f"pixel type 0x{pixel_type:x}"
        )


class MvsCameraKit:
    """Opens, configures, and grabs from one camera through the MVS SDK."""

    def __init__(self, config: MvsSourceConfig, *, sdk: Any | None = None) -> None:
        self._config = config
        self._sdk = sdk
        self._camera: Any = None

    def open(self) -> None:
        sdk = self._sdk if self._sdk is not None else load_sdk()
        self._sdk = sdk
        sdk.MvCamera.MV_CC_Initialize()
        try:
            device = self._find_device()
            camera = sdk.MvCamera()
            _check(camera.MV_CC_CreateHandle(device), "create handle")
            self._camera = camera
            _check(camera.MV_CC_OpenDevice(sdk.MV_ACCESS_Exclusive, 0), "open device")
            self._configure()
        except Exception:
            self.close()
            raise

    def grab(self, timeout_ms: int) -> np.ndarray | None:
        if self._camera is None:
            return None
        sdk = self._sdk
        out = sdk.MV_FRAME_OUT()
        ctypes.memset(ctypes.byref(out), 0, ctypes.sizeof(out))
        if self._camera.MV_CC_GetImageBuffer(out, timeout_ms) != 0:
            return None
        try:
            info = out.stFrameInfo
            data = ctypes.string_at(out.pBufAddr, info.nFrameLen)
            width, height = info.nWidth, info.nHeight
            pixel_type = info.enPixelType
        finally:
            self._camera.MV_CC_FreeImageBuffer(out)
        return to_bgr(np.frombuffer(data, dtype=np.uint8), width, height, pixel_type)

    def close(self) -> None:
        camera = self._camera
        sdk = self._sdk
        self._camera = None
        self._sdk = None
        if sdk is None:
            return
        if camera is not None:
            camera.MV_CC_StopGrabbing()
            camera.MV_CC_CloseDevice()
            camera.MV_CC_DestroyHandle()
        sdk.MvCamera.MV_CC_Finalize()

    def _find_device(self) -> Any:
        sdk = self._sdk
        devices = sdk.MV_CC_DEVICE_INFO_LIST()
        _check(
            sdk.MvCamera.MV_CC_EnumDevices(sdk.MV_GIGE_DEVICE, devices),
            "enumerate devices",
        )
        for index in range(devices.nDeviceNum):
            info = ctypes.cast(
                devices.pDeviceInfo[index], ctypes.POINTER(sdk.MV_CC_DEVICE_INFO)
            ).contents
            gig = info.SpecialInfo.stGigEInfo
            if matches_device(
                self._config,
                serial_number=_text(gig.chSerialNumber),
                current_ip=_ipv4(gig.nCurrentIp),
            ):
                return info
        raise RuntimeError(
            "no GigE camera matches "
            f"serial={self._config.serial!r} ip={self._config.ip!r}"
        )

    def _configure(self) -> None:
        """Write exposure and gain only; every other setting comes from MVS."""
        camera = self._camera
        config = self._config
        camera.MV_CC_SetEnumValue("ExposureAuto", _EXPOSURE_AUTO_OFF)
        _check(
            camera.MV_CC_SetFloatValue("ExposureTime", float(config.exposure_us)),
            "set ExposureTime",
        )
        camera.MV_CC_SetEnumValue("GainAuto", _GAIN_AUTO_OFF)
        _check(camera.MV_CC_SetFloatValue("Gain", float(config.gain_db)), "set Gain")
        _check(camera.MV_CC_StartGrabbing(), "start grabbing")


class MvsSource:
    """A `VideoSource` over the MVS SDK."""

    def __init__(
        self,
        config: MvsSourceConfig,
        *,
        camera_id: str,
        kit: CameraKit | None = None,
    ) -> None:
        self._config = config
        self._camera_id = camera_id
        self._kit = kit
        self._frame_seq = 0
        self._last_frame_at: datetime | None = None
        self._error: str | None = None

    def start(self) -> None:
        try:
            if self._kit is None:
                self._kit = MvsCameraKit(self._config)
            self._kit.open()
        except Exception as exc:  # hardware boundary: SDK errors vary
            self._error = str(exc)
            self.stop()
            raise RuntimeError(f"cannot start the MVS camera: {exc}") from exc

    def read(self) -> Frame | None:
        if self._kit is None:
            return None
        try:
            image = self._kit.grab(self._config.timeout_ms)
        except Exception as exc:  # hardware boundary: timeout/unplug/stream errors
            self._error = str(exc)
            return None
        if image is None:
            self._error = "camera acquisition timed out"
            return None
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
        if self._kit is not None:
            try:
                self._kit.close()
            except Exception:  # hardware boundary: already stopping/stopped
                pass
            self._kit = None

    def health(self) -> SourceHealth:
        if self._error is not None:
            return SourceHealth(
                status=HealthStatus.UNAVAILABLE,
                last_frame_at=self._last_frame_at,
                error=self._error,
            )
        if self._kit is None:
            return SourceHealth(HealthStatus.STOPPED, last_frame_at=self._last_frame_at)
        if self._last_frame_at is None:
            return SourceHealth(HealthStatus.STARTING)
        return SourceHealth(HealthStatus.HEALTHY, last_frame_at=self._last_frame_at)
