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
from app.infrastructure.excel.openpyxl_detail_writer import OpenpyxlDetailWriter
from app.domain.ports.job_repository import IJobRepository
from app.domain.ports.storage_port import IStoragePort
from app.domain.ports.llm_port import ILLMPort
from app.domain.ports.excel_port import IExcelPort
from app.domain.ports.excel_detail_port import IExcelDetailPort
from app.application.use_cases.process_invoice import ProcessInvoiceUseCase
from app.application.use_cases.review_and_confirm import ReviewAndConfirmUseCase
from app.application.use_cases.export_excel import ExportExcelUseCase
from app.domain.ports.task_queue_port import ITaskQueue
from app.infrastructure.queue.async_task_queue import AsyncTaskQueue

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

_storage_singleton: RustFSStorage | None = None
_notifier_singleton = None
_excel_singleton: OpenpyxlWriter | None = None
_excel_detail_singleton: OpenpyxlDetailWriter | None = None


def get_storage_singleton() -> RustFSStorage:
    global _storage_singleton
    if _storage_singleton is None:
        s = get_settings()
        _storage_singleton = RustFSStorage(
            endpoint=s.rustfs_endpoint,
            access_key=s.rustfs_access_key,
            secret_key=s.rustfs_secret_key,
            public_endpoint=s.rustfs_public_endpoint,
        )
    return _storage_singleton


def get_excel_singleton() -> OpenpyxlWriter:
    global _excel_singleton
    if _excel_singleton is None:
        _excel_singleton = OpenpyxlWriter(template_path="Mau_xuat_du_lieu.xlsx")
    return _excel_singleton


def get_excel_detail_singleton() -> OpenpyxlDetailWriter:
    global _excel_detail_singleton
    if _excel_detail_singleton is None:
        _excel_detail_singleton = OpenpyxlDetailWriter(template_path="Mau_xuat_du_lieu_chi_tiet.xlsx")
    return _excel_detail_singleton


def get_storage(settings: Settings = Depends(get_settings)) -> RustFSStorage:
    return get_storage_singleton()

def get_excel() -> OpenpyxlWriter:
    return get_excel_singleton()

def get_excel_detail() -> OpenpyxlDetailWriter:
    return get_excel_detail_singleton()

def get_notifier():
    global _notifier_singleton
    if _notifier_singleton is None:
        from app.core.config import get_settings
        settings = get_settings()
        if settings.notification_type == "telegram" and settings.telegram_bot_token:
            from app.infrastructure.notifications.telegram_notifier import TelegramNotifier
            _notifier_singleton = TelegramNotifier(settings.telegram_bot_token, settings.telegram_chat_id, settings.app_base_url)
        elif settings.notification_type == "slack" and settings.slack_webhook_url:
            from app.infrastructure.notifications.slack_notifier import SlackNotifier
            _notifier_singleton = SlackNotifier(settings.slack_webhook_url, settings.app_base_url)
        else:
            from app.infrastructure.notifications.console_notifier import ConsoleNotifier
            _notifier_singleton = ConsoleNotifier()
    return _notifier_singleton

def get_process_invoice_uc(
    repo=Depends(get_job_repo), llm=Depends(get_llm)
) -> ProcessInvoiceUseCase:
    return ProcessInvoiceUseCase(repo=repo, llm=llm, notification=get_notifier())

def get_review_confirm_uc(
    repo=Depends(get_job_repo),
    storage=Depends(get_storage),
    excel=Depends(get_excel),
    excel_detail=Depends(get_excel_detail),
    settings: Settings = Depends(get_settings),
) -> ReviewAndConfirmUseCase:
    return ReviewAndConfirmUseCase(
        repo=repo, storage=storage, excel=excel, excel_detail=excel_detail,
        bucket_invoices=settings.rustfs_bucket_invoices,
        bucket_exports=settings.rustfs_bucket_exports,
        notification=get_notifier(),
    )

def get_export_excel_uc(
    storage=Depends(get_storage), settings: Settings = Depends(get_settings)
) -> ExportExcelUseCase:
    return ExportExcelUseCase(storage=storage, bucket_exports=settings.rustfs_bucket_exports)

def get_exports_uc(
    storage=Depends(get_storage),
    settings: Settings = Depends(get_settings),
    repo=Depends(get_job_repo),
):
    from app.application.use_cases.get_exports import GetExportsUseCase
    return GetExportsUseCase(
        storage=storage,
        bucket_exports=settings.rustfs_bucket_exports,
        template_aggregate="Mau_xuat_du_lieu.xlsx",
        template_detail="Mau_xuat_du_lieu_chi_tiet.xlsx",
        repo=repo,
    )

_task_queue = AsyncTaskQueue()

def get_task_queue() -> ITaskQueue:
    return _task_queue

# ── Excel-CR ──────────────────────────────────────────────────────────────────
from app.infrastructure.rules.rustfs_rules_manager import RustfsRulesManager
from app.infrastructure.repositories.sqlite_excel_cr_repo import SQLiteExcelCrRepository
from app.infrastructure.llm.excel_cr_classifier import ExcelCrClassifier
from app.application.use_cases.excel_cr.upload_source import UploadSourceUseCase
from app.application.use_cases.excel_cr.aggregate_and_match_uc import AggregateAndMatchUseCase
from app.application.use_cases.excel_cr.llm_classify import LlmClassifyUseCase
from app.application.use_cases.excel_cr.confirm_mappings import ConfirmMappingsUseCase
from app.application.use_cases.excel_cr.download_result import DownloadResultUseCase

_rules_manager_singleton: RustfsRulesManager | None = None
_excel_cr_classifier_singleton: ExcelCrClassifier | None = None

def get_excel_cr_rules_manager() -> RustfsRulesManager:
    global _rules_manager_singleton
    if _rules_manager_singleton is None:
        s = get_settings()
        _rules_manager_singleton = RustfsRulesManager(get_storage_singleton(), s.excel_cr_bucket)
    return _rules_manager_singleton

def get_excel_cr_classifier() -> ExcelCrClassifier:
    global _excel_cr_classifier_singleton
    if _excel_cr_classifier_singleton is None:
        s = get_settings()
        _excel_cr_classifier_singleton = ExcelCrClassifier(
            api_key=s.gemini_api_key, model=s.gemini_model
        )
    return _excel_cr_classifier_singleton

def get_excel_cr_repo(db: aiosqlite.Connection = Depends(get_db_conn)) -> SQLiteExcelCrRepository:
    return SQLiteExcelCrRepository(db)

def get_excel_cr_upload_uc(
    repo=Depends(get_excel_cr_repo),
    storage=Depends(get_storage),
) -> UploadSourceUseCase:
    return UploadSourceUseCase(repo=repo, storage=storage)

def get_excel_cr_aggregate_uc(
    repo=Depends(get_excel_cr_repo),
    storage=Depends(get_storage),
) -> AggregateAndMatchUseCase:
    return AggregateAndMatchUseCase(
        repo=repo, storage=storage, rules_manager=get_excel_cr_rules_manager()
    )

def get_excel_cr_llm_classify_uc(
    repo=Depends(get_excel_cr_repo),
) -> LlmClassifyUseCase:
    return LlmClassifyUseCase(repo=repo, classifier=get_excel_cr_classifier())

def get_excel_cr_confirm_uc(
    repo=Depends(get_excel_cr_repo),
) -> ConfirmMappingsUseCase:
    return ConfirmMappingsUseCase(repo=repo, rules_manager=get_excel_cr_rules_manager())

def get_excel_cr_download_uc(
    repo=Depends(get_excel_cr_repo),
    storage=Depends(get_storage),
) -> DownloadResultUseCase:
    return DownloadResultUseCase(repo=repo, storage=storage)