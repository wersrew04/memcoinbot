from loguru import logger
import sys
from pathlib import Path

LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)

logger.remove()
logger.add(
    sys.stdout,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>",
    level="INFO",
)
logger.add(
    LOG_DIR / "bot_{time:YYYY-MM-DD}.log",
    rotation="00:00",
    retention="14 days",
    level="DEBUG",
    encoding="utf-8",
)
logger.add(
    LOG_DIR / "errors_{time:YYYY-MM-DD}.log",
    rotation="00:00",
    retention="30 days",
    level="ERROR",
    encoding="utf-8",
)
