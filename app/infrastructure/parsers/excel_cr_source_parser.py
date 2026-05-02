import io
import logging
import pandas as pd

logger = logging.getLogger(__name__)

_COLUMN_MAP = {
    "tháng": "thang",
    "diễn giải": "dien_giai",
    "số tiền": "so_tien",
    "khoản mục": "khoan_muc",
}


def parse_source_file(data: bytes, filename: str) -> pd.DataFrame:
    """Parse CSV/XLS/XLSX/PDF source file → normalized DataFrame.

    Returns columns: thang (int), dien_giai (str), so_tien (float), khoan_muc (str).
    Drops rows with purely numeric khoan_muc (totals/headers).
    """
    ext = filename.rsplit(".", 1)[-1].lower()
    if ext == "csv":
        df = _read_csv(data)
    elif ext in ("xls", "xlsx"):
        df = _read_excel(data, ext)
    elif ext == "pdf":
        df = _read_pdf(data)
    else:
        raise ValueError(f"Unsupported file extension: .{ext}")

    df = _normalize(df)
    return df


def _read_csv(data: bytes) -> pd.DataFrame:
    for enc in ("utf-8-sig", "utf-8", "cp1258", "latin-1"):
        try:
            return pd.read_csv(io.BytesIO(data), encoding=enc)
        except UnicodeDecodeError:
            continue
    raise ValueError("Cannot decode CSV — unsupported encoding")


def _read_excel(data: bytes, ext: str) -> pd.DataFrame:
    engine = "xlrd" if ext == "xls" else "openpyxl"
    return pd.read_excel(io.BytesIO(data), engine=engine)


def _read_pdf(data: bytes) -> pd.DataFrame:
    import pdfplumber
    frames = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for page in pdf.pages:
            table = page.extract_table()
            if table:
                header, *rows = table
                frames.append(pd.DataFrame(rows, columns=header))
    if not frames:
        raise ValueError("No tables found in PDF — scan-only PDF not supported")
    return pd.concat(frames, ignore_index=True)


def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    df.columns = [str(c).strip().lower() for c in df.columns]
    rename = {}
    for col in df.columns:
        for pattern, target in _COLUMN_MAP.items():
            if pattern in col:
                rename[col] = target
                break
    df = df.rename(columns=rename)

    required = ["thang", "dien_giai", "so_tien", "khoan_muc"]
    missing = set(required) - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    df = df[required].copy()

    # Drop rows where khoan_muc is purely numeric (totals/headers)
    df = df[~df["khoan_muc"].astype(str).str.strip().str.match(r"^\d+$")]

    df["so_tien"] = pd.to_numeric(
        df["so_tien"].astype(str).str.replace(",", "").str.replace(" ", ""),
        errors="coerce",
    ).fillna(0.0)

    df["thang"] = pd.to_numeric(df["thang"], errors="coerce").fillna(0).astype(int)
    df["dien_giai"] = df["dien_giai"].astype(str).str.strip()
    df["khoan_muc"] = df["khoan_muc"].astype(str).str.strip().str.lower()

    return df.reset_index(drop=True)