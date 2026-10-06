"""quest：纯内存的任务链状态机内核。

对外入口：
    QuestLog    任务链状态机：登记、接取、推进、完成、失败与超时
    Quest       一个任务的静态定义与运行时状态
    Clock       可注入的逻辑时钟
"""

from .core import (
    STATUS_ACTIVE,
    STATUS_AVAILABLE,
    STATUS_COMPLETED,
    STATUS_LOCKED,
    Clock,
    Quest,
    QuestLog,
)

__all__ = [
    "STATUS_ACTIVE",
    "STATUS_AVAILABLE",
    "STATUS_COMPLETED",
    "STATUS_LOCKED",
    "Clock",
    "Quest",
    "QuestLog",
]
