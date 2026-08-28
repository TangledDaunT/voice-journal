"""
Logging utilities for Voice Journal.
Provides structured logging with loguru.
"""

import sys
from loguru import logger

# Remove default handler
logger.remove()

# Add custom format
def setup_logging(log_level: str = "INFO", log_file: str | None = None):
    """Configure logging with loguru."""

    # Console handler with colors
    logger.add(
        sys.stderr,
        level=log_level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
               "<level>{level: <8}</level> | "
               "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
               "<level>{message}</level>",
        colorize=True,
    )

    # File handler (if specified)
    if log_file:
        logger.add(
            log_file,
            level=log_level,
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
            rotation="10 MB",
            retention="7 days",
            compression="gz",
        )

    return logger


# Stage-specific logging helpers
def log_stage(stage: str, message: str, **kwargs):
    """Log a stage-specific message."""
    logger.info(f"[{stage}] {message}", **kwargs)


def log_metric(stage: str, metric: str, value: float, unit: str = ""):
    """Log a performance metric."""
    logger.debug(f"[{stage}] {metric}: {value:.2f}{unit}")


def log_error(stage: str, error: Exception, context: str = ""):
    """Log an error with context."""
    logger.error(f"[{stage}] Error in {context}: {type(error).__name__}: {error}")


# Export configured logger
__all__ = ["logger", "setup_logging", "log_stage", "log_metric", "log_error"]
