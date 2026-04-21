from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
from app.core.dependencies import get_process_invoice_uc, get_review_confirm_uc, get_job_repo

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
router = APIRouter()

@router.get("/", response_class=HTMLResponse)
async def upload_page(request: Request):
    return templates.TemplateResponse(request=request, name="index.html", context={})

@router.post("/upload")
async def handle_upload(
    request: Request,
    background_tasks: BackgroundTasks,
    files: list[UploadFile] = File(...),
    process_uc=Depends(get_process_invoice_uc),
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
        background_tasks.add_task(process_uc.execute, filename=filename, file_data=data, paired_pdf=paired_pdf)

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
async def preview_file(job_id: str, repo=Depends(get_job_repo)):
    job = await repo.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job không tồn tại")
    path = job.pending_file_path
    if not path or not Path(path).is_file():
        raise HTTPException(status_code=404, detail="File không còn khả dụng")
    content_type = "application/xml" if job.file_type.value == "XML" else "application/pdf"
    return FileResponse(path, media_type=content_type)

@router.post("/jobs/{job_id}/confirm")
async def web_confirm(job_id: str, request: Request, repo=Depends(get_job_repo),
                      confirm_uc=Depends(get_review_confirm_uc)):
    form = await request.form()
    job = await repo.get(job_id)
    from app.domain.entities.invoice_item import InvoiceItem
    from app.domain.entities.invoice_line_item import InvoiceLineItem
    from decimal import Decimal
    from datetime import date

    # Parse invoice items
    items = []
    for item in job.extracted_items:
        items.append(InvoiceItem(
            id=item.id,
            invoice_symbol=form.get(f"invoice_symbol_{item.id}", item.invoice_symbol),
            invoice_number=form.get(f"invoice_number_{item.id}", item.invoice_number),
            invoice_date=date.fromisoformat(form.get(f"invoice_date_{item.id}", item.invoice_date.isoformat())),
            seller_name=form.get(f"seller_name_{item.id}", item.seller_name),
            seller_tax_code=form.get(f"seller_tax_code_{item.id}", item.seller_tax_code),
            description=form.get(f"description_{item.id}", item.description),
            price_before_tax=Decimal(form.get(f"price_before_tax_{item.id}", str(item.price_before_tax))),
            tax_rate=Decimal(form.get(f"tax_rate_{item.id}", str(item.tax_rate))),
            price_after_tax=Decimal(form.get(f"price_after_tax_{item.id}", str(item.price_after_tax))),
        ))

    # Parse line items từ form
    line_items = []
    for li in job.extracted_line_items:
        line_items.append(InvoiceLineItem(
            id=li.id,
            invoice_symbol=li.invoice_symbol,
            invoice_number=li.invoice_number,
            invoice_date=li.invoice_date,
            seller_name=li.seller_name,
            seller_tax_code=li.seller_tax_code,
            ten_hang_hoa=form.get(f"li_ten_hang_hoa_{li.id}", li.ten_hang_hoa),
            don_vi_tinh=form.get(f"li_don_vi_tinh_{li.id}", li.don_vi_tinh),
            so_luong=Decimal(form.get(f"li_so_luong_{li.id}", str(li.so_luong))),
            don_gia=Decimal(form.get(f"li_don_gia_{li.id}", str(li.don_gia))),
            thanh_tien=Decimal(form.get(f"li_thanh_tien_{li.id}", str(li.thanh_tien))),
            tax_rate=Decimal(form.get(f"li_tax_rate_{li.id}", str(li.tax_rate))),
            tax_amount=Decimal(form.get(f"li_tax_amount_{li.id}", str(li.tax_amount))),
        ))

    await confirm_uc.confirm(job_id=job_id, updated_items=items, updated_line_items=line_items)
    return RedirectResponse("/jobs", status_code=303)

@router.post("/jobs/{job_id}/reject")
async def web_reject(job_id: str, confirm_uc=Depends(get_review_confirm_uc)):
    await confirm_uc.reject(job_id=job_id)
    return RedirectResponse("/jobs", status_code=303)