import tempfile
import os
from markitdown import MarkItDown

_converter = MarkItDown()

def extract_text_from_pdf(data: bytes) -> str:
    """Convert PDF bytes to markdown text using markitdown."""
    if not data.startswith(b"%PDF"):
        raise ValueError("Invalid PDF file: does not start with PDF header")

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(data)
        tmp_path = tmp.name
    try:
        result = _converter.convert(tmp_path)
        if not result or not result.text_content:
            raise ValueError("PDF conversion resulted in empty content")
        return result.text_content
    except Exception as e:
        raise ValueError(f"Failed to extract text from PDF: {str(e)}")
    finally:
        os.unlink(tmp_path)