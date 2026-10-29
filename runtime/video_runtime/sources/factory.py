from video_runtime.config import (
    FileSourceConfig,
    GigESourceConfig,
    MvsSourceConfig,
    SourceConfig,
)
from video_runtime.sources.base import VideoSource
from video_runtime.sources.file import FileSource
from video_runtime.sources.gige import GigEHKSource
from video_runtime.sources.mvs import MvsSource


def build_source(source: SourceConfig, camera_id: str) -> VideoSource:
    if isinstance(source, FileSourceConfig):
        return FileSource(source.path, camera_id=camera_id, loop=source.loop)
    if isinstance(source, GigESourceConfig):
        return GigEHKSource(source, camera_id=camera_id)
    if isinstance(source, MvsSourceConfig):
        return MvsSource(source, camera_id=camera_id)
    raise SystemExit(f"unsupported source kind: {source.kind}")
