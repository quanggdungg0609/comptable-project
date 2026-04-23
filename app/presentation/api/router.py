from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from app.presentation.api.schemas import JobResponse, ReviewRequest, InvoiceItemSchema
from app.core.dependencies import (
    get_process_invoice_uc, get_review_confirm_uc, get_export_excel_uc, get_job_repo,
)

router = APIRouter(prefix="/api/v1")

@router.post("/jobs", response_model=list[JobResponse])
async def upload_invoices(
    files: list[UploadFile] = File(...),
    process_uc=Depends(get_process_invoice_uc),
    repo=Depends(get_job_repo),
):
    # Pair XML + PDF by base filename
    file_map: dict[str, dict] = {}
    for f in files:
        base = f.filename.rsplit(".", 1)[0].lower()
        ext = f.filename.rsplit(".", 1)[-1].lower()
        if base not in file_map:
            file_map[base] = {}
        file_map[base][ext] = (f.filename, await f.read())

    jobs = []
    for base, exts in file_map.items():
        if "xml" in exts:
            filename, data = exts["xml"]
            paired_pdf = exts.get("pdf", (None, None))[1]
        else:
            filename, data = exts["pdf"]
            paired_pdf = None
        job = await process_uc.execute(filename=filename, file_data=data, paired_pdf=paired_pdf)
        jobs.append(_job_to_response(job))
    return jobs

@router.get("/jobs", response_model=list[JobResponse])
async def list_jobs(status: str | None = None, repo=Depends(get_job_repo)):
    from app.domain.value_objects.invoice_status import InvoiceStatus
    status_filter = InvoiceStatus(status) if status else None
    jobs = await repo.list_all(status=status_filter)
    return [_job_to_response(j) for j in jobs]

@router.get("/jobs/{job_id}", response_model=JobResponse)
async def get_job(job_id: str, repo=Depends(get_job_repo)):
    job = await repo.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return _job_to_response(job)

@router.patch("/jobs/{job_id}/review", response_model=JobResponse)
async def update_review(job_id: str, body: ReviewRequest, repo=Depends(get_job_repo)):
    from app.domain.entities.invoice_item import InvoiceItem
    from decimal import Decimal
    items = [InvoiceItem(**i.model_dump()) for i in body.items]
    await repo.update_items(job_id, items)
    job = await repo.get(job_id)
    return _job_to_response(job)

@router.post("/jobs/{job_id}/confirm", response_model=JobResponse)
async def confirm_job(
    job_id: str,
    repo=Depends(get_job_repo),
    confirm_uc=Depends(get_review_confirm_uc),
):
    job = await repo.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    # First, quickly prepare the confirmation (update status to CONFIRMING)
    result = await confirm_uc.prepare_confirm(
        job_id=job_id,
        updated_items=job.extracted_items,
        updated_line_items=job.extracted_line_items,
    )

    # Fire-and-forget finalization using cached singletons + bg DB connection.
    from app.application.services.bg_finalize import spawn_finalize
    spawn_finalize(job_id, job.extracted_items, job.extracted_line_items)

    return _job_to_response(result)

@router.post("/jobs/{job_id}/reject", response_model=JobResponse)
async def reject_job(job_id: str, confirm_uc=Depends(get_review_confirm_uc)):
    result = await confirm_uc.reject(job_id=job_id)
    return _job_to_response(result)

@router.get("/exports/{year}/{month}")
async def download_export(year: int, month: int, export_uc=Depends(get_export_excel_uc)):
    try:
        data, filename = await export_uc.execute(year=year, month=month)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

def _job_to_response(job) -> JobResponse:
    from app.presentation.api.schemas import InvoiceItemSchema
    return JobResponse(
        id=job.id, filename=job.filename, file_type=job.file_type.value,
        status=job.status.value, created_at=job.created_at,
        extracted_items=[InvoiceItemSchema(**{
            "id": i.id, "invoice_symbol": i.invoice_symbol, "invoice_number": i.invoice_number,
            "invoice_date": i.invoice_date, "seller_name": i.seller_name, "seller_address": i.seller_address, "seller_tax_code": i.seller_tax_code,
            "description": i.description, "price_before_tax": i.price_before_tax, "tax_rate": i.tax_rate, "price_after_tax": i.price_after_tax,
        }) for i in job.extracted_items],
        source_paths=job.source_paths, error=job.error,
    )