import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Optional
from fastapi import FastAPI
from app.core.config import get_settings
from app.core.database import init_db, get_db, close_db
from app.infrastructure.storage.rustfs_storage import RustFSStorage
from app.presentation.api.router import router as api_router
from app.presentation.web.router import router as web_router

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
    settings = get_settings()
    await init_db()
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
    except Exception:
        pass  # RustFS may not be available in dev mode

    listener_task: Optional[asyncio.Task] = None
    listener_obj = None

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
    task_queue = get_task_queue()
    await task_queue.start_workers(process_use_case=process_uc, num_workers=2)
    logger.info("Task queue workers started (concurrency: 2)")

    if settings.email_listener_enabled:
        from app.infrastructure.email.imap_client import IMAPClient
        from app.infrastructure.email.email_listener import EmailListener

        imap_client = IMAPClient(
            host=settings.imap_host, port=settings.imap_port,
            username=settings.imap_username, password=settings.imap_password,
            use_ssl=settings.imap_use_ssl,
        )
        listener_obj = EmailListener(imap_client, process_uc, settings.email_poll_interval)
        listener_task = asyncio.create_task(listener_obj.start())
        logger.info("Email listener started (polling every %ds)", settings.email_poll_interval)

    yield

    if listener_obj and listener_task:
        listener_obj.stop()
        listener_task.cancel()
        logger.info("Email listener stopped")

    await task_queue.stop_workers()
    await close_db()


app = FastAPI(title="Thu Hóa Đơn", lifespan=lifespan)
app.include_router(api_router)
app.include_router(web_router)