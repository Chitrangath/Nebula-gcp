"""Nebula AI Cloud Worker - Main Entry Point"""

import asyncio
import logging

from config import settings
from core.executor import JobExecutor
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def main():
    logger.info(f"Worker started: {settings.NODE_ID}")
    logger.info(f"Backend: {settings.BACKEND_URL}")

    executor = JobExecutor(settings)
    await executor.run()


if __name__ == "__main__":
    asyncio.run(main())
