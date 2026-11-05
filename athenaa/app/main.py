"""
Entrypoint Utama Aplikasi Athenaa (Single-Instance Discord Bot + FastAPI Web Server).
Dirancang untuk hosting Pterodactyl atau VPS dengan sumber daya terbatas:
- Otomatis menambahkan direktori root proyek ke sys.path agar dapat dijalankan dari
  /home/container maupun /home/container/athenaa.
- Menjalankan database schema initialization pada saat startup.
- Menjalankan bot Discord dan server web Uvicorn (Port 10031) dalam satu event loop asyncio.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

# Pastikan direktori induk 'app/' selalu berada di urutan pertama sys.path di Pterodactyl
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.bot.client import build_discord_bot
from app.config import settings
from app.database import db_manager
from app.web.routes.api import create_fastapi_app

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("athenaa.main")


async def run_application() -> None:
    settings.ensure_directories()
    db_manager.initialize_schema()

    readiness = settings.feature_readiness()
    logger.info("Status Kesiapan Subsistem Athenaa: %s", readiness)
    if not readiness["discord_bot"]:
        logger.warning(
            "DISCORD_TOKEN belum diisi di .env. Layanan Web API, Database, Akademik, dan RPG tetap berjalan."
        )

    fastapi_app = create_fastapi_app()
    broadcast_cb = getattr(getattr(fastapi_app, "state", None), "broadcast_guild_state", None)
    bot = build_discord_bot(on_state_change=broadcast_cb) if readiness["discord_bot"] else None
    if fastapi_app is not None and bot is not None:
        fastapi_app.state.bot = bot


    # Gunakan SERVER_PORT dari Pterodactyl jika tersedia, fallback ke WEB_PORT (10031)
    active_port = int(os.environ.get("SERVER_PORT", str(settings.web_port)))

    tasks = []
    if bot and settings.discord_token:
        tasks.append(asyncio.create_task(bot.start(settings.discord_token)))

    if fastapi_app:
        try:
            import uvicorn  # type: ignore

            logger.info("Menjalankan Athenaa Web Dashboard & API pada %s:%d", settings.web_host, active_port)
            uv_config = uvicorn.Config(
                fastapi_app,
                host=settings.web_host,
                port=active_port,
                log_level=settings.log_level.lower(),
                workers=1,  # Wajib 1 worker agar koneksi Discord tidak ganda
                proxy_headers=True,
                forwarded_allow_ips="*",
            )
            server = uvicorn.Server(uv_config)
            tasks.append(asyncio.create_task(server.serve()))
        except ImportError:
            logger.warning("Uvicorn belum terinstal. Jalankan pip install -r requirements.txt pada VPS/Pterodactyl.")

    if not tasks:
        logger.info("Pemeriksaan startup Athenaa selesai dengan sukses.")
        return

    await asyncio.gather(*tasks)


def main() -> None:
    try:
        asyncio.run(run_application())
    except KeyboardInterrupt:
        logger.info("Aplikasi Athenaa dihentikan dengan aman.")
        sys.exit(0)


if __name__ == "__main__":
    main()
