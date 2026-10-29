from datetime import datetime

from contracts.runtime import HealthStatus
from pydantic import BaseModel

from app.api.schemas.camera import CameraRead
from app.api.schemas.runtime import RuntimeRead


class HealthSummaryRead(BaseModel):
    database: HealthStatus
    server_time: datetime
    runtimes: list[RuntimeRead]
    cameras: list[CameraRead]
