import asyncio
from io import BytesIO
from decimal import Decimal
import openpyxl
from app.domain.entities.invoice_item import InvoiceItem
from app.domain.ports.excel_port import IExcelPort

# First data row in the template (after headers and category label)
DATA_START_ROW = 13
SHEET_NAME = "Bang ke thue"

def generate_monthly_filename(month: int, year: int) -> str:
    """Generate filename: Tong_hop_hoa_don_T{month}_{year}.xlsx
    Example: Tong_hop_hoa_don_T4_2026.xlsx
    """
    return f"Tong_hop_hoa_don_T{month}_{year}.xlsx"

class OpenpyxlWriter(IExcelPort):
    def __init__(self, template_path: str):
        self._template_path = template_path

    async def append_rows(
        self, items: list[InvoiceItem], year: int, month: int, existing_data: bytes
    ) -> tuple[str, bytes]:
        """Append rows to monthly Excel file.
        
        Returns: (filename, file_bytes) tuple
        - filename: For RustFS path like s3://exports/{filename}
        - file_bytes: Excel file bytes to save
        """
        filename = generate_monthly_filename(month, year)
        file_bytes = await asyncio.to_thread(self._append_rows_sync, items, existing_data)
        return filename, file_bytes

    def _append_rows_sync(self, items: list[InvoiceItem], existing_data: bytes) -> bytes:
        if existing_data:
            wb = openpyxl.load_workbook(BytesIO(existing_data))
        else:
            wb = openpyxl.load_workbook(self._template_path)

        ws = wb[SHEET_NAME]

        # Find next available row after the last data row
        last_row = DATA_START_ROW - 1
        for row in range(ws.max_row, DATA_START_ROW - 1, -1):
            if ws.cell(row=row, column=5).value is not None:  # invoice_number column
                last_row = row
                break

        # Determine STT offset
        stt_offset = 0
        for row in range(DATA_START_ROW, last_row + 1):
            v = ws.cell(row=row, column=1).value
            if isinstance(v, int):
                stt_offset = v

        for idx, item in enumerate(items, start=1):
            r = last_row + idx
            ws.cell(row=r, column=1).value = stt_offset + idx
            ws.cell(row=r, column=4).value = item.invoice_symbol
            ws.cell(row=r, column=5).value = item.invoice_number
            ws.cell(row=r, column=6).value = item.invoice_date
            ws.cell(row=r, column=7).value = item.seller_name
            ws.cell(row=r, column=8).value = item.seller_tax_code
            ws.cell(row=r, column=9).value = item.description
            ws.cell(row=r, column=10).value = float(item.price_before_tax)
            ws.cell(row=r, column=11).value = int(item.tax_rate * 100)
            ws.cell(row=r, column=12).value = float(item.tax_rate)
            ws.cell(row=r, column=13).value = float(item.price_after_tax)

        buf = BytesIO()
        wb.save(buf)
        return buf.getvalue()