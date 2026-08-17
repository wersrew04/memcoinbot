import logging
import sys
from pathlib import Path
from datetime import datetime

Path("logs").mkdir(exist_ok=True)
Path("data").mkdir(exist_ok=True)

log_file = Path("logs") / f"bot_{datetime.now().strftime('%Y%m%d')}.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(log_file, encoding="utf-8"),
    ]
)
logger = logging.getLogger("memebot")
