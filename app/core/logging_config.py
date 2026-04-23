import logging
import logging.handlers
import os
from datetime import datetime

# Create logs directory if it doesn't exist
LOGS_DIR = "logs"
os.makedirs(LOGS_DIR, exist_ok=True)

# Log file paths
LOG_FILE = os.path.join(LOGS_DIR, "app.log")
ERROR_LOG_FILE = os.path.join(LOGS_DIR, "error.log")

# Log format with detailed information
DETAILED_FORMAT = "[%(asctime)s] %(levelname)-8s [%(name)s:%(funcName)s:%(lineno)d] %(message)s"
SIMPLE_FORMAT = "[%(asctime)s] %(levelname)-8s %(message)s"

def setup_logging(level=logging.INFO):
    """Configure logging for the application"""

    # Root logger configuration
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Remove any existing handlers to avoid duplicates
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Console handler (INFO level)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter(SIMPLE_FORMAT)
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)

    # File handler for all logs (DEBUG level)
    try:
        file_handler = logging.handlers.RotatingFileHandler(
            LOG_FILE,
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5,
        )
        file_handler.setLevel(logging.DEBUG)
        file_formatter = logging.Formatter(DETAILED_FORMAT)
        file_handler.setFormatter(file_formatter)
        root_logger.addHandler(file_handler)
    except Exception as e:
        console_handler.emit(
            logging.LogRecord(
                name="logging_config",
                level=logging.WARNING,
                pathname="",
                lineno=0,
                msg=f"Failed to setup file handler: {e}",
                args=(),
                exc_info=None,
            )
        )

    # File handler for errors only (ERROR level)
    try:
        error_handler = logging.handlers.RotatingFileHandler(
            ERROR_LOG_FILE,
            maxBytes=5 * 1024 * 1024,  # 5MB
            backupCount=3,
        )
        error_handler.setLevel(logging.ERROR)
        error_formatter = logging.Formatter(DETAILED_FORMAT)
        error_handler.setFormatter(error_formatter)
        root_logger.addHandler(error_handler)
    except Exception as e:
        console_handler.emit(
            logging.LogRecord(
                name="logging_config",
                level=logging.WARNING,
                pathname="",
                lineno=0,
                msg=f"Failed to setup error handler: {e}",
                args=(),
                exc_info=None,
            )
        )

    root_logger.info("=" * 80)
    root_logger.info(f"Application started at {datetime.now().isoformat()}")
    root_logger.info(f"Logging configuration: Level={logging.getLevelName(level)}, File={LOG_FILE}")
    root_logger.info("=" * 80)
