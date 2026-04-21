from fastapi import APIRouter, Depends, File, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
from app.core.dependencies import get_process_invoice_uc, get_review_confirm_uc, get_job_repo

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
router = APIRouter()

@router.get("/", response_class=HTMLResponse)
async def upload_page(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@router.post("/upload")
async def handle_upload(
    request: Request,
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
        await process_uc.execute(filename=filename, file_data=data, paired_pdf=paired_pdf)

    return RedirectResponse("/jobs", status_code=303)

@router.get("/jobs", response_class=HTMLResponse)
async def jobs_page(request: Request, repo=Depends(get_job_repo)):
    jobs = await repo.list_all()
    return templates.TemplateResponse("jobs.html", {"request": request, "jobs": jobs})

@router.get("/jobs/{job_id}/review", response_class=HTMLResponse)
async def review_page(job_id: str, request: Request, repo=Depends(get_job_repo)):
    job = await repo.get(job_id)
    return templates.TemplateResponse("review.html", {"request": request, "job": job})

@router.post("/jobs/{job_id}/confirm")
async def web_confirm(job_id: str, request: Request, repo=Depends(get_job_repo),
                      confirm_uc=Depends(get_review_confirm_uc)):
    form = await request.form()
    job = await repo.get(job_id)
    from app.domain.entities.invoice_item import InvoiceItem
    from decimal import Decimal
    from datetime import date

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

    await confirm_uc.confirm(job_id=job_id, updated_items=items)
    return RedirectResponse("/jobs", status_code=303)

@router.post("/jobs/{job_id}/reject")
async def web_reject(job_id: str, confirm_uc=Depends(get_review_confirm_uc)):
    await confirm_uc.reject(job_id=job_id)
    return RedirectResponse("/jobs", status_code=303)