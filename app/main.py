import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Optional
from fastapi import FastAPI
from app.core.config import get_settings
from app.core.database import init_db, get_db, close_db
from app.core.logging_config import setup_logging
from app.infrastructure.storage.rustfs_storage import RustFSStorage
from app.presentation.api.router import router as api_router
from app.presentation.web.router import router as web_router

# Setup logging configuration
setup_logging(logging.INFO)

logger = logging.getLogger(__name__)


def _build_notifier(settings):
    if settings.notification_type == "telegram" and settings.telegram_bot_token:
        from app.infrastructure.notifications.telegram_notifier import TelegramNotifier
        return TelegramNotifier(settings.telegram_bot_token, settings.telegram_chat_id, settings.app_base_url)
    if settings.notification_type == "slack" and settings.slack_webhook_url:
        from app.infrastructure.notifications.slack_notifier import SlackNotifier
        return SlackNotifier(settings.slack_webhook_url, settings.app_base_url)
    from app.infrastructure.notifications.console_notifier import ConsoleNotifier
    return ConsoleNotifier()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("[App Startup] Initializing application")
    settings = get_settings()
    logger.info(f"[App Startup] Configuration: LLM={settings.llm_provider}, Email Listener={'Enabled' if settings.email_listener_enabled else 'Disabled'}")

    logger.debug("[App Startup] Initializing database")
    await init_db()
    logger.info("[App Startup] Database initialized")

    logger.debug("[App Startup] Initializing RustFS storage")
    storage = RustFSStorage(
        endpoint=settings.rustfs_endpoint,
        access_key=settings.rustfs_access_key,
        secret_key=settings.rustfs_secret_key,
    )
    try:
        await storage.ensure_buckets(
            settings.rustfs_bucket_invoices,
            settings.rustfs_bucket_exports,
        )
        logger.info("[App Startup] RustFS storage initialized")
    except Exception as e:
        logger.warning(f"[App Startup] RustFS may not be available in dev mode: {e}")

    listener_task: Optional[asyncio.Task] = None
    listener_obj = None
    retry_scheduler = None

    # Common setup for Background Queue and Email Listener
    from app.infrastructure.repositories.sqlite_job_repo import SQLiteJobRepository
    from app.infrastructure.llm.ollama_client import OllamaLLMClient
    from app.infrastructure.llm.gemini_client import GeminiLLMClient
    from app.infrastructure.llm.fallback_client import FallbackLLMClient
    from app.application.use_cases.process_invoice import ProcessInvoiceUseCase
    from app.core.dependencies import get_task_queue

    db = await get_db()
    repo = SQLiteJobRepository(db)
    
    ollama = OllamaLLMClient(settings.llm_base_url, settings.llm_model)
    gemini = GeminiLLMClient(settings.gemini_api_key, settings.gemini_model)
    if settings.llm_provider == "gemini":
        llm = gemini
    elif settings.llm_provider == "gemini+ollama":
        llm = FallbackLLMClient(primary=gemini, secondary=ollama)
    elif settings.llm_provider == "ollama+gemini":
        llm = FallbackLLMClient(primary=ollama, secondary=gemini)
    else:
        llm = ollama

    notification = _build_notifier(settings)
    process_uc = ProcessInvoiceUseCase(repo=repo, llm=llm, notification=notification)

    # Start Task Queue Workers
    logger.debug("[App Startup] Starting task queue workers")
    task_queue = get_task_queue()
    await task_queue.start_workers(process_use_case=process_uc, num_workers=1)
    logger.info("[App Startup] Task queue workers started (concurrency: 1)")

    # Recover jobs stuck in PROCESSING from a previous crash
    from app.domain.value_objects.invoice_status import InvoiceStatus
    stuck = await repo.list_all(status=InvoiceStatus.PROCESSING)
    for job in stuck:
        await repo.update_status(job.id, InvoiceStatus.FAILED, error="App restarted while processing")
    if stuck:
        logger.warning("[App Startup] Reset %d stuck PROCESSING job(s) to FAILED for retry", len(stuck))

    # Start retry scheduler — auto-retries FAILED jobs every 5 minutes
    from app.infrastructure.queue.retry_scheduler import RetryScheduler
    retry_scheduler = RetryScheduler(repo=repo, process_use_case=process_uc)
    await retry_scheduler.start()
    logger.info("[App Startup] Retry scheduler started")

    # Pre-warm background finalize singletons (XLSX templates, boto3 client,
    # bg DB connection) off the event loop so the first invoice confirm is
    # instant and doesn't stall other HTTP requests.
    logger.debug("[App Startup] Pre-warming background finalize singletons")
    from app.application.services.bg_finalize import prewarm as prewarm_bg_finalize
    from app.core.dependencies import (
        get_excel_detail_singleton,
        get_excel_singleton,
        get_storage_singleton,
    )
    await asyncio.to_thread(get_storage_singleton)
    await asyncio.to_thread(get_excel_singleton)
    await asyncio.to_thread(get_excel_detail_singleton)
    await prewarm_bg_finalize()
    logger.info("[App Startup] Background finalize singletons ready")

    if settings.email_listener_enabled:
        logger.debug("[App Startup] Email listener enabled, starting IMAP client")
        from app.infrastructure.email.imap_client import IMAPClient
        from app.infrastructure.email.email_listener import EmailListener

        imap_client = IMAPClient(
            host=settings.imap_host, port=settings.imap_port,
            username=settings.imap_username, password=settings.imap_password,
            use_ssl=settings.imap_use_ssl,
        )
        listener_obj = EmailListener(imap_client, process_uc, settings.email_poll_interval)
        listener_task = asyncio.create_task(listener_obj.start())
        logger.info(f"[App Startup] Email listener started (polling every {settings.email_poll_interval}s)")
    else:
        logger.info("[App Startup] Email listener disabled")

    logger.info("[App Startup] Application ready to receive requests")
    yield

    logger.info("[App Shutdown] Shutting down application")

    if listener_obj and listener_task:
        logger.debug("[App Shutdown] Stopping email listener")
        listener_obj.stop()
        listener_task.cancel()
        try:
            await asyncio.wait_for(listener_task, timeout=5)
        except asyncio.CancelledError:
            pass
        except asyncio.TimeoutError:
            logger.warning("[App Shutdown] Email listener did not stop within timeout")
        logger.info("[App Shutdown] Email listener stopped")

    if retry_scheduler:
        await retry_scheduler.stop()
        logger.info("[App Shutdown] Retry scheduler stopped")

    logger.debug("[App Shutdown] Stopping task queue workers")
    await task_queue.stop_workers()
    logger.info("[App Shutdown] Task queue workers stopped")

    logger.debug("[App Shutdown] Closing database")
    await close_db()
    logger.info("[App Shutdown] Database closed")
    logger.info("[App Shutdown] Application shutdown complete")


app = FastAPI(title="Thu Hóa Đơn", lifespan=lifespan)
app.include_router(api_router)
app.include_router(web_router)