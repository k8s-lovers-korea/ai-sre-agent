#!/usr/bin/env python3
"""
Development runner for SRE Agent.

Quick script to start the agent with development settings.
"""

import os
import sys
from pathlib import Path

# Add src to Python path
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

# Load environment variables early
from dotenv import load_dotenv

load_dotenv()

# Configure development logging
import structlog

structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer(),
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)


def main():
    """Run the development server."""
    import uvicorn
    from src.config import get_settings

    settings = get_settings()

    # Override settings for development
    settings.api.reload = True
    settings.development.debug = True
    settings.development.enable_debug_logs = True

    logger = structlog.get_logger()
    logger.info(
        "Starting SRE Agent in development mode",
        host=settings.api.host,
        port=settings.api.port,
    )

    # Start the server
    uvicorn.run(
        "src.api.main:app",
        host=settings.api.host,
        port=settings.api.port,
        reload=settings.api.reload,
        reload_dirs=["src"],
        log_level=settings.api.log_level.lower(),
    )


if __name__ == "__main__":
    main()
