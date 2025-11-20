import logging
import os
from datetime import datetime


class DualLogger:
    """
    A utility class to set up logging to both console and a timestamped file.
    """

    def __init__(
        self,
        log_dir: str = "logs",
        log_prefix: str = "process",
        level: int = logging.INFO,
    ):
        self.log_dir = log_dir
        self.log_prefix = log_prefix
        self.level = level
        self.log_file = None
        self.logger = None
        self._configure_logger()

    def _configure_logger(self):
        # Ensure the directory exists
        os.makedirs(self.log_dir, exist_ok=True)

        # Build a timestamped log file name
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_file = os.path.join(self.log_dir, f"{self.log_prefix}_{timestamp}.txt")

        # Get root logger or a named logger (optional: use log_prefix)
        self.logger = logging.getLogger(self.log_prefix)
        self.logger.setLevel(self.level)

        # Remove any existing handlers to avoid duplicate logs
        for handler in self.logger.handlers[:]:
            self.logger.removeHandler(handler)

        # IMPORTANT: prevent log propagation to root
        self.logger.propagate = False

        # Define formatter
        formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(self.level)
        console_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)

        # File handler
        file_handler = logging.FileHandler(self.log_file, mode="w")
        file_handler.setLevel(self.level)
        file_handler.setFormatter(formatter)
        self.logger.addHandler(file_handler)

        # Initial log
        self.logger.info(
            f"✅ Logging initialized. Logs will be written to {self.log_file}"
        )

    def get_logger(self) -> logging.Logger:
        """Return the configured logger."""
        return self.logger

    def get_log_file(self) -> str:
        """Return the path of the log file being written to."""
        return self.log_file
