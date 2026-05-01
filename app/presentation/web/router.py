from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
from io import BytesIO
from app.core.dependencies import get_process_invoice_uc, get_review_confirm_uc, get_job_repo, get_task_queue, get_exports_uc, get_storage
from app.core.config import get_settings
from fastapi.responses import Response

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

def format_number(value):
    if value is None or value == "":
        return ""
    try:
        num = float(str(value).replace(",", "").replace(".", ""))
        return f"{int(num):,}".replace(",", ".")
    except (ValueError, AttributeError):
        return value

templates.env.filters["format_number"] = format_number
router = APIRouter()

@router.get("/", response_class=HTMLResponse)
async def upload_page(request: Request):
    return templates.TemplateResponse(request=request, name="index.html", context={})

@router.post("/upload")
async def handle_upload(
    request: Request,
    files: list[UploadFile] = File(...),
    task_queue=Depends(get_task_queue),
):
    file_map: dict[str, dict] = {}
    for f in files:
        base = f.filename.rsplit(".", 1)[0].lower()
        ext = f.filename.rsplit(".", 1)[-1].lower()
        if base not in file_map:
            file_map[base] = {}
        file_map[base][ext] = (f.filename, await f.read())

    for base, exts in file_map.items():
        if "xml" in exts:
            filename, data = exts["xml"]
            paired_pdf = exts.get("pdf", (None, None))[1]
        else:
            filename, data = exts["pdf"]
            paired_pdf = None
        
        await task_queue.enqueue(filename=filename, file_data=data, paired_pdf=paired_pdf)

    return RedirectResponse("/jobs", status_code=303)

@router.get("/jobs", response_class=HTMLResponse)
async def jobs_page(request: Request, repo=Depends(get_job_repo)):
    jobs = await repo.list_all()
    return templates.TemplateResponse(request=request, name="jobs.html", context={"jobs": jobs})

@router.get("/jobs/{job_id}/review", response_class=HTMLResponse)
async def review_page(job_id: str, request: Request, repo=Depends(get_job_repo)):
    job = await repo.get(job_id)
    return templates.TemplateResponse(request=request, name="review.html", context={"job": job})

@router.get("/jobs/{job_id}/preview")
async def preview_file(job_id: str, repo=Depends(get_job_repo), storage=Depends(get_storage), settings=Depends(get_settings)):
    job = await repo.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job không tồn tại")
    content_type = "application/xml" if job.file_type.value == "XML" else "application/pdf"
    
    path = job.pending_file_path
    if not path or not Path(path).is_file():
        if job.source_paths:
            try:
                bucket = settings.rustfs_bucket_invoices
                storage_key = job.source_paths[0]
                file_bytes = await storage.download_file(bucket, storage_key)
                return Response(content=file_bytes, media_type=content_type)
            except Exception as e:
                import logging
                logging.error(f"Failed to download from storage: {e}")
        raise HTTPException(status_code=404, detail="File không còn khả dụng")
        
    return FileResponse(path, media_type=content_type)

@router.post("/jobs/{job_id}/confirm")
async def web_confirm(job_id: str, request: Request,
                      repo=Depends(get_job_repo)):
    from starlette.requests import ClientDisconnect
    try:
        form = await request.form()
    except ClientDisconnect:
        return RedirectResponse("/jobs", status_code=303)
    job = await repo.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job không tồn tại")
    if job.status.value == "DUPLICATE":
        raise HTTPException(status_code=400, detail="Hóa đơn trùng lặp, không thể xác nhận")
    from app.domain.entities.invoice_item import InvoiceItem
    from app.domain.entities.invoice_line_item import InvoiceLineItem
    from app.domain.value_objects.invoice_status import InvoiceStatus
    from decimal import Decimal
    from datetime import datetime

    def clean_num(val: str) -> str:
        if not val: return "0"
        return val.replace(".", "").replace(",", "").replace(" ", "")

    # Parse invoice items
    items = []
    for item in job.extracted_items:
        items.append(InvoiceItem(
            id=item.id,
            invoice_symbol=form.get(f"invoice_symbol_{item.id}", item.invoice_symbol),
            invoice_number=form.get(f"invoice_number_{item.id}", item.invoice_number),
            invoice_date=datetime.strptime(form.get(f"invoice_date_{item.id}", item.invoice_date.strftime('%d/%m/%Y')), '%d/%m/%Y').date(),
            seller_name=form.get(f"seller_name_{item.id}", item.seller_name),
            seller_address=form.get(f"seller_address_{item.id}", item.seller_address),
            seller_tax_code=form.get(f"seller_tax_code_{item.id}", item.seller_tax_code),
            description=form.get(f"description_{item.id}", item.description),
            price_before_tax=Decimal(clean_num(form.get(f"price_before_tax_{item.id}", str(item.price_before_tax)))),
            tax_rate=Decimal(clean_num(form.get(f"tax_rate_{item.id}", str(item.tax_rate * 100)))) / 100,
            price_after_tax=Decimal(clean_num(form.get(f"price_after_tax_{item.id}", str(item.price_after_tax)))),
        ))

    # Parse line items
    line_items = []
    for li in job.extracted_line_items:
        line_items.append(InvoiceLineItem(
            id=li.id,
            invoice_symbol=li.invoice_symbol,
            invoice_number=li.invoice_number,
            invoice_date=li.invoice_date,
            seller_name=li.seller_name,
            seller_address=li.seller_address,
            seller_tax_code=li.seller_tax_code,
            ten_hang_hoa=form.get(f"li_ten_hang_hoa_{li.id}", li.ten_hang_hoa),
            don_vi_tinh=form.get(f"li_don_vi_tinh_{li.id}", li.don_vi_tinh),
            so_luong=Decimal(clean_num(form.get(f"li_so_luong_{li.id}", str(li.so_luong)))),
            don_gia=Decimal(clean_num(form.get(f"li_don_gia_{li.id}", str(li.don_gia)))),
            thanh_tien=Decimal(clean_num(form.get(f"li_thanh_tien_{li.id}", str(li.thanh_tien)))),
            tax_rate=Decimal(clean_num(form.get(f"li_tax_rate_{li.id}", str(li.tax_rate * 100)))) / 100,
            tax_amount=Decimal(clean_num(form.get(f"li_tax_amount_{li.id}", str(li.tax_amount)))),
        ))

    # Set status immediately so UI shows "Đang lưu Excel..." right away
    await repo.update_status(job_id, InvoiceStatus.CONFIRMING)

    # Fire-and-forget: reuse cached singletons + bg DB connection so
    # the event loop is not blocked by XLSX parsing / boto3 init.
    from app.application.services.bg_finalize import spawn_finalize
    spawn_finalize(job_id, items, line_items)

    return RedirectResponse("/jobs", status_code=303)

@router.get("/exports", response_class=HTMLResponse)
async def exports_page(request: Request):
    from datetime import date
    today = date.today()
    return templates.TemplateResponse(
        request=request, name="exports.html",
        context={"current_year": today.year, "current_month": today.month},
    )

@router.get("/exports/preview", response_class=HTMLResponse)
async def exports_preview(
    request: Request,
    year: int = Query(...),
    month: int = Query(...),
    exports_uc=Depends(get_exports_uc),
):
    data = await exports_uc.get_preview(year=year, month=month)
    return templates.TemplateResponse(
        request=request, name="exports_preview.html", context=data
    )

@router.get("/exports/download")
async def exports_download(
    year: int = Query(...),
    month: int = Query(...),
    type: str = Query(...),
    exports_uc=Depends(get_exports_uc),
):
    file_bytes, filename = await exports_uc.get_download(year=year, month=month, file_type=type)
    return StreamingResponse(
        BytesIO(file_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

@router.get("/jobs/{job_id}/reject")
async def web_reject(job_id: str, repo=Depends(get_job_repo)):
    from app.domain.value_objects.invoice_status import InvoiceStatus
    await repo.update_status(job_id, InvoiceStatus.REJECTED)
    return RedirectResponse("/jobs", status_code=303)

@router.post("/jobs/{job_id}/retry")
async def web_retry(
    job_id: str,
    repo=Depends(get_job_repo),
    process_uc=Depends(get_process_invoice_uc),
):
    import os
    from app.domain.value_objects.invoice_status import InvoiceStatus
    job = await repo.get(job_id)
    if not job or job.status != InvoiceStatus.FAILED:
        return RedirectResponse("/jobs", status_code=303)
    if not job.pending_file_path or not os.path.exists(job.pending_file_path):
        return RedirectResponse("/jobs", status_code=303)

    file_data = open(job.pending_file_path, "rb").read()
    paired_bytes: bytes | None = None
    if job.pending_pdf_path and os.path.exists(job.pending_pdf_path):
        paired_bytes = open(job.pending_pdf_path, "rb").read()

    await repo.increment_retry_count(job_id)
    await process_uc.execute(filename=job.filename, file_data=file_data, paired_pdf=paired_bytes)
    return RedirectResponse("/jobs", status_code=303)