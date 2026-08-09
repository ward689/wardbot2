import asyncio

from bot_final import run_all

if __name__ == "__main__":
    try:
        asyncio.run(run_all())
    except (KeyboardInterrupt, RuntimeError):
        pass
