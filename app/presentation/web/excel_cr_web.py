# app/presentation/web/excel_cr_web.py
from fastapi import APIRouter
from fastapi.responses import FileResponse
import os

router = APIRouter()

@router.get("/excel-cr/", include_in_schema=False)
async def excel_cr_index():
    path = os.path.join(os.path.dirname(__file__), "../../static/excel_cr/index.html")
    return FileResponse(os.path.abspath(path))
