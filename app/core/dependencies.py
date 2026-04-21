from functools import lru_cache
import aiosqlite
from fastapi import Depends
from app.core.config import get_settings, Settings
from app.core.database import get_db
from app.infrastructure.repositories.sqlite_job_repo import SQLiteJobRepository
from app.infrastructure.llm.ollama_client import OllamaLLMClient
from app.infrastructure.llm.gemini_client import GeminiLLMClient
from app.infrastructure.llm.fallback_client import FallbackLLMClient
from app.infrastructure.storage.rustfs_storage import RustFSStorage
from app.infrastructure.excel.openpyxl_writer import OpenpyxlWriter
from app.application.use_cases.process_invoice import ProcessInvoiceUseCase
from app.application.use_cases.review_and_confirm import ReviewAndConfirmUseCase
from app.application.use_cases.export_excel import ExportExcelUseCase

async def get_db_conn() -> aiosqlite.Connection:
    db = await get_db()
    yield db

def get_job_repo(db: aiosqlite.Connection = Depends(get_db_conn)) -> SQLiteJobRepository:
    return SQLiteJobRepository(db)

def get_llm(settings: Settings = Depends(get_settings)):
    ollama = OllamaLLMClient(base_url=settings.llm_base_url, model=settings.llm_model)
    gemini = GeminiLLMClient(api_key=settings.gemini_api_key, model=settings.gemini_model)
    if settings.llm_provider == "gemini":
        return gemini
    if settings.llm_provider == "gemini+ollama":
        return FallbackLLMClient(primary=gemini, secondary=ollama)
    if settings.llm_provider == "ollama+gemini":
        return FallbackLLMClient(primary=ollama, secondary=gemini)
    return ollama  # default

def get_storage(settings: Settings = Depends(get_settings)) -> RustFSStorage:
    return RustFSStorage(
        endpoint=settings.rustfs_endpoint,
        access_key=settings.rustfs_access_key,
        secret_key=settings.rustfs_secret_key,
    )

def get_excel() -> OpenpyxlWriter:
    return OpenpyxlWriter(template_path="Mau_xuat_du_lieu.xlsx")

def get_notifier():
    from app.core.config import get_settings
    settings = get_settings()
    if settings.notification_type == "telegram" and settings.telegram_bot_token:
        from app.infrastructure.notifications.telegram_notifier import TelegramNotifier
        return TelegramNotifier(settings.telegram_bot_token, settings.telegram_chat_id, settings.app_base_url)
    if settings.notification_type == "slack" and settings.slack_webhook_url:
        from app.infrastructure.notifications.slack_notifier import SlackNotifier
        return SlackNotifier(settings.slack_webhook_url, settings.app_base_url)
    from app.infrastructure.notifications.console_notifier import ConsoleNotifier
    return ConsoleNotifier()

def get_process_invoice_uc(
    repo=Depends(get_job_repo), llm=Depends(get_llm)
) -> ProcessInvoiceUseCase:
    return ProcessInvoiceUseCase(repo=repo, llm=llm, notification=get_notifier())

def get_review_confirm_uc(
    repo=Depends(get_job_repo),
    storage=Depends(get_storage),
    excel=Depends(get_excel),
    settings: Settings = Depends(get_settings),
) -> ReviewAndConfirmUseCase:
    return ReviewAndConfirmUseCase(
        repo=repo, storage=storage, excel=excel,
        bucket_invoices=settings.rustfs_bucket_invoices,
        bucket_exports=settings.rustfs_bucket_exports,
    )

def get_export_excel_uc(
    storage=Depends(get_storage), settings: Settings = Depends(get_settings)
) -> ExportExcelUseCase:
    return ExportExcelUseCase(storage=storage, bucket_exports=settings.rustfs_bucket_exports)