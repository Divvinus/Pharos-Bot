import asyncio

from src.utils import load_config

config = load_config()
semaphore = asyncio.Semaphore(config.threads)