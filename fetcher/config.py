import os
import sys
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from dotenv import load_dotenv

# These paths are assuming the container's file structure.
LOG_DIR = Path("/app/logs")
DATA_DIR = Path("/app/data")
DB_FILE = DATA_DIR / "cmma.db"

class AppConfig:
    def __init__(self, dotenv_path=None):
        if dotenv_path:
            load_dotenv(dotenv_path)
        else:
            load_dotenv()

        self.exchange = os.getenv("EXCHANGE", "bybit").lower()
        self.log_max_size_mb = int(os.getenv("LOG_MAX_SIZE_MB", "10"))
        self.concurrency_limit = int(os.getenv("CONCURRENCY_LIMIT", "60"))
        self.fetch_interval_seconds = int(os.getenv("FETCH_INTERVAL_SECONDS", "300"))
        self.bitget_product_type = os.getenv("BITGET_PRODUCT_TYPE", "usdt-futures")
        self.base_url = self._get_base_url()

        # Funding Rate Specific Settings
        self.funding_rate_threshold = float(os.getenv("FUNDING_RATE_THRESHOLD", "0.001")) # 0.1% = 0.001
        self.funding_rate_history_limit = int(os.getenv("FUNDING_RATE_HISTORY_LIMIT", "10"))
        self.max_notifications = int(os.getenv("MAX_NOTIFICATIONS", "30"))

    def _get_base_url(self) -> str:
        if self.exchange == "bybit":
            return os.getenv("BYBIT_BASE_URL", "https://api.bybit.com")
        if self.exchange == "bitget":
            return os.getenv("BITGET_BASE_URL", "https://api.bitget.com")
        raise ValueError("EXCHANGE must be either 'bybit' or 'bitget'")

def setup_logging(config: AppConfig) -> logging.Logger:
    LOG_DIR.mkdir(exist_ok=True)
    log_file = LOG_DIR / "fetcher.log"
    formatter = logging.Formatter(
        "%(asctime)s - %(levelname)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )

    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=config.log_max_size_mb * 1024 * 1024,
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)

    logger = logging.getLogger(f"{config.exchange.capitalize()}Fetcher")
    logger.setLevel(logging.INFO)
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    logger.propagate = False
    return logger
