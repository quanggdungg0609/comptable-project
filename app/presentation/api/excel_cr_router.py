# app/presentation/api/excel_cr_router.py
import logging
from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from fastapi.responses import StreamingResponse
import io
from app.core.dependencies import (
    get_excel_cr_upload_uc,
    get_excel_cr_aggregate_uc,
    get_excel_cr_llm_classify_uc,
    get_excel_cr_confirm_uc,
    get_excel_cr_download_uc,
    get_excel_cr_repo,
    get_storage,
    get_settings,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/excel-cr", tags=["excel-cr"])

BUCKET = "excel-cr"


@router.post("/upload-source")
async def upload_source(
    file: UploadFile = File(...),
    uc=Depends(get_excel_cr_upload_uc),
):
    try:
        data = await file.read()
        session = await uc.execute(filename=file.filename, file_data=data)
        return {"session_id": session.id, "status": session.status}
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.post("/upload-template/{session_id}")
async def upload_template(
    session_id: str,
    file: UploadFile = File(...),
    repo=Depends(get_excel_cr_repo),
    storage=Depends(get_storage),
    settings=Depends(get_settings),
):
    session = await repo.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    data = await file.read()
    key = f"uploads/{session_id}/template_{file.filename}"
    await storage.upload_file(settings.excel_cr_bucket, key, data,
                               "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    session.template_key = key
    await repo.update(session)
    return {"session_id": session_id, "template_key": key}


@router.get("/aggregate/{session_id}")
async def aggregate(session_id: str, uc=Depends(get_excel_cr_aggregate_uc)):
    try:
        return await uc.execute(session_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/llm-review/{session_id}")
async def llm_review(session_id: str, uc=Depends(get_excel_cr_llm_classify_uc)):
    try:
        return await uc.execute(session_id)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.post("/confirm/{session_id}")
async def confirm(
    session_id: str,
    body: list[dict],
    uc=Depends(get_excel_cr_confirm_uc),
):
    try:
        return await uc.execute(session_id, body)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get("/download/{session_id}")
async def download(session_id: str, uc=Depends(get_excel_cr_download_uc)):
    try:
        output_bytes = await uc.execute(session_id)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return StreamingResponse(
        io.BytesIO(output_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="excel_cr_output.xlsx"'},
    )


@router.get("/rules")
async def get_rules(rules_mgr=Depends(lambda: __import__(
    "app.core.dependencies", fromlist=["get_excel_cr_rules_manager"]
).get_excel_cr_rules_manager())):
    return await rules_mgr.load()


@router.post("/rules")
async def update_rules(body: dict, rules_mgr=Depends(lambda: __import__(
    "app.core.dependencies", fromlist=["get_excel_cr_rules_manager"]
).get_excel_cr_rules_manager())):
    await rules_mgr.save(body)
    return {"status": "saved"}
