import asyncio
from io import BytesIO
from decimal import Decimal
import openpyxl
from app.domain.entities.invoice_line_item import InvoiceLineItem
from app.domain.ports.excel_detail_port import IExcelDetailPort

DATA_START_ROW = 6  # Hàng data đầu tiên trong template (sau headers)

def generate_detail_filename(month: int, year: int) -> str:
    return f"Chi_tiet_hoa_don_T{month}_{year}.xlsx"

class OpenpyxlDetailWriter(IExcelDetailPort):
    def __init__(self, template_path: str):
        self._template_path = template_path

    async def append_rows(
        self,
        items: list[InvoiceLineItem],
        year: int,
        month: int,
        existing_data: bytes,
    ) -> tuple[str, bytes]:
        filename = generate_detail_filename(month, year)
        file_bytes = await asyncio.to_thread(self._append_rows_sync, items, existing_data)
        return filename, file_bytes

    def _append_rows_sync(self, items: list[InvoiceLineItem], existing_data: bytes) -> bytes:
        if existing_data:
            wb = openpyxl.load_workbook(BytesIO(existing_data))
        else:
            wb = openpyxl.load_workbook(self._template_path)

        ws = wb.active

        # Tìm hàng cuối có dữ liệu (cột H = ten_hang_hoa)
        last_row = DATA_START_ROW - 1
        for row in range(ws.max_row, DATA_START_ROW - 1, -1):
            if ws.cell(row=row, column=8).value is not None:
                last_row = row
                break

        # STT offset
        stt_offset = 0
        for row in range(DATA_START_ROW, last_row + 1):
            v = ws.cell(row=row, column=1).value
            if isinstance(v, int):
                stt_offset = v

        for idx, li in enumerate(items, start=1):
            r = last_row + idx
            ws.cell(row=r, column=1).value = stt_offset + idx   # STT
            ws.cell(row=r, column=2).value = ""                  # Ký hiệu mẫu HĐ (trống)
            ws.cell(row=r, column=3).value = li.invoice_symbol   # Ký hiệu HĐ
            ws.cell(row=r, column=4).value = li.invoice_number   # Số HĐ
            ws.cell(row=r, column=5).value = li.invoice_date     # Ngày phát hành
            ws.cell(row=r, column=6).value = li.seller_name      # Tên nhà cung cấp
            ws.cell(row=r, column=7).value = li.seller_tax_code  # MST
            ws.cell(row=r, column=8).value = li.ten_hang_hoa     # Mặt hàng
            ws.cell(row=r, column=9).value = li.don_vi_tinh      # Đơn vị tính
            ws.cell(row=r, column=10).value = float(li.so_luong) # Số lượng
            ws.cell(row=r, column=11).value = float(li.don_gia)  # Đơn giá
            ws.cell(row=r, column=12).value = float(li.thanh_tien)  # Thành tiền
            ws.cell(row=r, column=13).value = int(li.tax_rate * 100)  # Thuế suất %
            ws.cell(row=r, column=14).value = float(li.tax_amount)    # Thuế GTGT

        buf = BytesIO()
        wb.save(buf)
        return buf.getvalue()
