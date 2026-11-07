"""
Entrypoint Utama Aplikasi Athenaa (Single-Process Asyncio: Discord Bot + FastAPI Web Server).
Dirancang khusus untuk VPS / Pterodactyl Hosting:
- Menginisialisasi skema SQLite secara aman saat startup.
- Menjalankan FastAPI/Uvicorn dan Discord Bot secara konkuren di satu event loop asyncio.
- Menggunakan sistem hak akses Per-Server: Admin Server, DJ, dan Member (tanpa OWNER_DISCORD_ID).
- Menangani sinyal SIGINT/SIGTERM untuk graceful shutdown tanpa memutus proses backup.
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

from app.config import settings
from app.database import db_manager

from app.services.observability import (
    setup_structured_logging,
    get_logger,
    init_metrics,
    init_default_tracing,
    create_default_health_checker,
    create_health_endpoints,
    create_tracing_middleware,
)

# Setup structured JSON logging
setup_structured_logging(
    level=getattr(logging, settings.log_level, logging.INFO),
    service_name="athenaa",
    output="both",
    log_file=str(settings.logs_dir / "athenaa.log"),
)
logger = get_logger("athenaa.main")

# Initialize metrics and tracing
init_metrics(service_name="athenaa", version="1.0.0")
init_default_tracing(service_name="athenaa", version="1.0.0")


async def run_application() -> None:
    """Menjalankan Web Server FastAPI dan Discord Bot secara bersamaan dalam satu event loop."""
    logger.info("Memulai inisialisasi Athenaa (Discord Bot + Web Dashboard)...")
    db_manager.initialize_schema()

    for warn in settings.validate_startup():
        logger.warning(warn)

    from app.services.academy_service import AcademyService
    from app.services.leveling_service import LevelingService
    from app.services.queue_service import queue_service
    from app.web.routes.api import build_fastapi_app, notify_guild_state_updated

    academy_service = AcademyService(db_manager)
    leveling_service = LevelingService(db_manager)

    fastapi_app = build_fastapi_app()

    health_checker = create_default_health_checker(
        service_name="athenaa",
        version="1.0.0",
        db_path=str(settings.sqlite_path),
        bot_getter=lambda: getattr(fastapi_app.state, "discord_bot", None),
        queue_service_getter=lambda: queue_service,
    )
    create_health_endpoints(fastapi_app, health_checker)

    try:
        TracingMiddleware = create_tracing_middleware("athenaa")
        fastapi_app.add_middleware(TracingMiddleware)
    except Exception as e:
        logger.warning("Failed to add tracing middleware: %s", e)

    async def run_web_server() -> None:
        try:
            import uvicorn  # type: ignore

            config = uvicorn.Config(
                fastapi_app,
                host=settings.web_host,
                port=settings.web_port,
                log_level=settings.log_level.lower(),
                access_log=False,
            )
            server = uvicorn.Server(config)
            logger.info("Web Dashboard & API aktif di http://%s:%s", settings.web_host, settings.web_port)
            await server.serve()
        except ImportError:
            logger.error("Paket uvicorn belum terinstal. Jalankan: pip install -r requirements.txt")

    web_server_task = asyncio.create_task(run_web_server(), name="athenaa-web-server")

    if settings.discord_token:
        from app.bot.client import build_discord_bot

        bot = build_discord_bot(
            queue_service=queue_service,
            academy_service=academy_service,
            leveling_service=leveling_service,
            on_state_change=notify_guild_state_updated,
        )
        if bot is not None:
            if fastapi_app is not None:
                fastapi_app.state.bot = bot
                fastapi_app.state.discord_bot = bot

            async def run_discord_bot() -> None:
                while True:
                    try:
                        logger.info("Menghubungkan bot ke Discord Gateway...")
                        await bot.start(settings.discord_token)
                        break
                    except Exception as exc:
                        logger.error("Koneksi Discord Bot terputus atau gagal: %s", exc)
                        try:
                            if not bot.is_closed():
                                await bot.close()
                        except Exception:
                            pass
                        # Jika token tidak valid, jangan loop tanpa henti
                        if "Improper token" in str(exc) or "LoginFailure" in type(exc).__name__:
                            logger.error("Token Discord tidak valid. Web Server tetap berjalan.")
                            break
                        await asyncio.sleep(10)

            bot_task = asyncio.create_task(run_discord_bot(), name="athenaa-discord-bot")
            await asyncio.gather(web_server_task, bot_task, return_exceptions=True)
            return

    await web_server_task


def main() -> None:
    try:
        asyncio.run(run_application())
    except KeyboardInterrupt:
        logger.info("Menerima sinyal penghentian (SIGINT). Menutup Athenaa dengan aman...")


if __name__ == "__main__":
    main()