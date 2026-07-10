"""
Enterprise Logging Configuration

Author:
Edith Stark

Project:
AI-Powered Mainframe Modernization Assistant
"""

from pathlib import Path

from loguru import logger

from app.core.config import settings

# Create logs directory if it doesn't exist
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)

# Remove default logger
logger.remove()

# Console logging
logger.add(
    sink=lambda msg: print(msg, end=""),
    level=settings.log_level,
    colorize=True,
    format=(
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
        "<level>{message}</level>"
    ),
)

# File logging
logger.add(
    LOG_DIR / "application.log",
    rotation="10 MB",
    retention="30 days",
    compression="zip",
    level=settings.log_level,
    enqueue=True,
)

__all__ = ["logger"]
