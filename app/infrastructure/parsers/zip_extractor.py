import io
import logging
import zipfile

logger = logging.getLogger(__name__)

_ALLOWED_EXTENSIONS = {".pdf", ".xml"}


def extract_zip_contents(zip_filename: str, zip_data: bytes) -> list[dict]:
    """Extract PDF and XML files from a ZIP archive.

    Returns list of {"filename": str, "data": bytes} dicts.
    Returns empty list on error or no valid files.
    """
    try:
        buf = io.BytesIO(zip_data)
        with zipfile.ZipFile(buf, "r") as zf:
            results = []
            for info in zf.infolist():
                name = info.filename
                # Handle cases where filename might have directory separators
                basename = name.split("/")[-1]

                if not basename:
                    continue
                if basename.startswith("."):
                    continue
                if "__MACOSX" in name:
                    continue

                ext = "." + basename.rsplit(".", 1)[-1].lower() if "." in basename else ""
                if ext == ".zip":
                    logger.warning(f"[ZipExtractor] Skipping nested ZIP: {name}")
                    continue
                if ext not in _ALLOWED_EXTENSIONS:
                    logger.debug(f"[ZipExtractor] Skipping unsupported file: {name}")
                    continue

                data = zf.read(name)
                results.append({"filename": basename, "data": data})
                logger.debug(f"[ZipExtractor] Extracted: {basename} ({len(data)} bytes)")

            if not results:
                logger.warning(f"[ZipExtractor] No valid invoice files found in {zip_filename}")
            return results

    except zipfile.BadZipFile:
        logger.error(f"[ZipExtractor] Invalid or corrupt ZIP: {zip_filename}")
        return []
    except Exception as e:
        logger.error(f"[ZipExtractor] Unexpected error reading {zip_filename}: {e}")
        return []
