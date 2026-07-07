"""
Logging test.
"""

from app.core.logging import logger

logger.debug("Debug message")

logger.info("Application started successfully.")

logger.warning("This is a warning.")

logger.error("Example error.")

logger.success("Logging system operational.")