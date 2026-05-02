import io
import zipfile
import pytest
from app.infrastructure.parsers.zip_extractor import extract_zip_contents


def _make_zip(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return buf.getvalue()


def test_extracts_pdf_and_xml():
    data = _make_zip({"invoice.pdf": b"pdf", "invoice.xml": b"xml"})
    result = extract_zip_contents("test.zip", data)
    assert len(result) == 2
    names = {r["filename"] for r in result}
    assert names == {"invoice.pdf", "invoice.xml"}


def test_skips_unsupported_types():
    data = _make_zip({"invoice.pdf": b"pdf", "readme.txt": b"txt", "data.csv": b"csv"})
    result = extract_zip_contents("test.zip", data)
    assert len(result) == 1
    assert result[0]["filename"] == "invoice.pdf"


def test_skips_macosx_entries():
    data = _make_zip({
        "__MACOSX/._invoice.pdf": b"junk",
        "invoice.pdf": b"pdf",
    })
    result = extract_zip_contents("test.zip", data)
    assert len(result) == 1
    assert result[0]["filename"] == "invoice.pdf"


def test_skips_hidden_files():
    data = _make_zip({".DS_Store": b"junk", "invoice.xml": b"xml"})
    result = extract_zip_contents("test.zip", data)
    assert len(result) == 1
    assert result[0]["filename"] == "invoice.xml"


def test_skips_nested_zip():
    inner = _make_zip({"inner.pdf": b"pdf"})
    outer = _make_zip({"nested.zip": inner, "invoice.pdf": b"pdf"})
    result = extract_zip_contents("outer.zip", outer)
    assert len(result) == 1
    assert result[0]["filename"] == "invoice.pdf"


def test_empty_zip_returns_empty_list():
    data = _make_zip({})
    result = extract_zip_contents("empty.zip", data)
    assert result == []


def test_corrupt_zip_returns_empty_list():
    result = extract_zip_contents("corrupt.zip", b"not a zip file at all")
    assert result == []


def test_preserves_file_data():
    pdf_bytes = b"%PDF-1.4 fake content"
    data = _make_zip({"real.pdf": pdf_bytes})
    result = extract_zip_contents("test.zip", data)
    assert result[0]["data"] == pdf_bytes


def test_strips_directory_prefix_from_filename():
    data = _make_zip({"subdir/invoice.pdf": b"pdf"})
    result = extract_zip_contents("test.zip", data)
    assert result[0]["filename"] == "invoice.pdf"
