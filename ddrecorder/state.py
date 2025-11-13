from __future__ import annotations

import enum


class RunnerState(enum.Enum):
    IDLE = "空闲"
    RECORDING = "录制中"
    PROCESSING = "处理视频"
    UPLOADING = "上传至Bilibili"
    ERROR = "异常"

    def __str__(self) -> str:
        return self.value
