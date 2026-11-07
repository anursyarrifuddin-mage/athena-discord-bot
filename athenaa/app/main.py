"""
Entrypoint Utama Aplikasi Athenaa (Single-Instance Discord Bot + FastAPI Web Server).
Dirancang untuk hosting Pterodactyl atau VPS dengan sumber daya terbatas:
- Otomatis menambahkan direktori root proyek ke sys.path agar dapat dijalankan dari
  /home/container maupun /home/container/athenaa.
- Menjalankan database schema initialization pada saat startup.
- Menjalankan bot Discord dan server web Uvicorn (Port 10031) dalam satu event loop asyncio.
- Observability: Structured logging, Prometheus metrics, Distributed tracing, Health checks.
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

# Observability imports
from app.services.observability import (
    setup_structured_logging,
    init_metrics,
    init_default_tracing,
    create_default_health_checker,
    create_health_endpoints,
    update_uptime_metrics,
)

# Initialize observability FIRST (before other imports that might log)
logger = setup_structured_logging(
    level=settings.log_level.upper(),
    service_name="athenaa",
    log_file="logs/athenaa.log",
)

# Initialize metrics
init_metrics(service_name="athenaa", version="1.0.0")

# Initialize distributed tracing
init_default_tracing(service_name="athenaa", version="1.0.0")

logger = logging.getLogger("athenaa.main")


async def run_application() -> None:
    settings.ensure_directories()
    
    # Validasi environment variables wajib - FAIL FAST
    required_env = {
        "DISCORD_TOKEN": settings.discord_token,
        "DISCORD_CLIENT_ID": settings.discord_client_id,
        "DISCORD_CLIENT_SECRET": settings.discord_client_secret,
        "MAIN_GUILD_ID": settings.main_guild_id,
        "OWNER_DISCORD_ID": settings.owner_discord_id,
        "SESSION_SECRET": settings.session_secret,
        "ENCRYPTION_KEY": settings.encryption_key,
        "BACKUP_ENCRYPTION_KEY": settings.backup_encryption_key,
    }
    
    missing = [k for k, v in required_env.items() if not v]
    if missing:
        logger.error(f"Environment variables WAJIB tidak di-set: {', '.join(missing)}")
        logger.error("Salin .env.example ke .env dan isi semua nilai yang diperlukan")
        sys.exit(1)
    
    # Validasi panjang kunci enkripsi (min 32 chars untuk AES-256)
    if len(settings.encryption_key) < 32:
        logger.error("ENCRYPTION_KEY harus minimal 32 karakter (64 hex chars recommended)")
        sys.exit(1)
    if len(settings.backup_encryption_key) < 32:
        logger.error("BACKUP_ENCRYPTION_KEY harus minimal 32 karakter (64 hex chars recommended)")
        sys.exit(1)
    if len(settings.session_secret) < 32:
        logger.error("SESSION_SECRET harus minimal 32 karakter")
        sys.exit(1)

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

    # Initialize health checker with all standard checks
    health_checker = create_default_health_checker(
        service_name="athenaa",
        version="1.0.0",
        db_path=str(settings.sqlite_path),
        bot_getter=lambda: fastapi_app.state.bot if fastapi_app and hasattr(fastapi_app.state, 'bot') else None,
        queue_service_getter=lambda: __import__('app.services.queue', fromlist=['queue_service']).queue_service,
    )
    
    # Add health check endpoints to FastAPI
    create_health_endpoints(fastapi_app, health_checker)

    # Gunakan SERVER_PORT dari Pterodactyl jika tersedia, fallback ke WEB_PORT (10031)
    active_port = int(os.environ.get("SERVER_PORT", str(settings.web_port)))

    tasks = []

    async def run_discord_bot():
        """Run Discord bot with separate login/connect and proper timeout handling."""
        if not bot or not settings.discord_token:
            return

        try:
            # Step 1: Login via HTTP (fast, usually works)
            logger.info("Logging into Discord...")
            await asyncio.wait_for(bot.login(settings.discord_token), timeout=15.0)
            logger.info("Discord login successful")

            # Step 2: Connect to Gateway (WebSocket) - run in background
            # bot.connect() runs the event loop forever, so we don't wait_for it
            # Instead, we wait for bot.wait_until_ready() to confirm connection
            logger.info("Connecting to Discord Gateway...")

            # Start connect in background
            connect_task = asyncio.create_task(bot.connect())

            # Wait for bot to be ready with timeout
            try:
                await asyncio.wait_for(bot.wait_until_ready(), timeout=30.0)
                logger.info("Discord Gateway connected and READY")
            except asyncio.TimeoutError:
                logger.warning("Discord Gateway connection timed out waiting for READY (network restriction?). Web server continues without bot.")
                connect_task.cancel()
                try:
                    await connect_task
                except asyncio.CancelledError:
                    pass
                await bot.close()
                return

            # Bot is connected and ready - let connect_task run forever
            # Wait for connect_task to complete (which happens on disconnect)
            try:
                await connect_task
            except asyncio.CancelledError:
                logger.info("Bot connection task cancelled")
            except Exception as e:
                logger.error(f"Bot connection error: {e}")
            finally:
                await bot.close()

        except asyncio.TimeoutError:
            logger.error("Discord login timed out. Web server continues without bot.")
        except Exception as e:
            logger.error(f"Discord bot failed: {e}. Web server continues without bot.")

    # Track the web server task separately
    web_server_task = None

    # Start bot in background (non-blocking) - web server starts immediately
    bot_task = None
    if bot and settings.discord_token:
        bot_task = asyncio.create_task(run_discord_bot())
        logger.info("Discord bot starting in background (web server starts immediately)")

    # Background task to update uptime metrics
    async def update_metrics_loop():
        while True:
            update_uptime_metrics()
            await asyncio.sleep(30)

    metrics_task = asyncio.create_task(update_metrics_loop())

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
            web_server_task = asyncio.create_task(server.serve())
        except ImportError:
            logger.warning("Uvicorn belum terinstal. Jalankan pip install -r requirements.txt pada VPS/Pterodactyl.")

    if not web_server_task:
        logger.info("Pemeriksaan startup Athenaa selesai dengan sukses.")
        return

    # Wait for bot task to complete (it runs until bot disconnects)
    # Don't use wait_for - bot_task should run forever unless there's an error
    if bot_task:
        try:
            await bot_task
        except asyncio.CancelledError:
            logger.info("Bot task cancelled")
        except Exception as e:
            logger.error(f"Bot task error: {e}")

    # Wait for web server (runs forever)
    try:
        await web_server_task
    except asyncio.CancelledError:
        logger.info("Web server shutting down...")
    except Exception as e:
        logger.error(f"Web server error: {e}")
    finally:
        # Cancel remaining tasks on shutdown
        if bot_task and not bot_task.done():
            bot_task.cancel()
        if not metrics_task.done():
            metrics_task.cancel()


def main() -> None:
    try:
        asyncio.run(run_application())
    except KeyboardInterrupt:
        logger.info("Aplikasi Athenaa dihentikan dengan aman.")
        sys.exit(0)


if __name__ == "__main__":
    main()