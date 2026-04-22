import tempfile
import os
from unittest.mock import AsyncMock
from fastapi.testclient import TestClient
from app.main import app
from app.core.dependencies import get_job_repo
from app.domain.entities.processing_job import ProcessingJob
from app.domain.value_objects.file_type import FileType
from app.domain.value_objects.invoice_status import InvoiceStatus


def make_xml_job(tmp_path: str) -> ProcessingJob:
    job = ProcessingJob.create("hd001.xml", FileType.XML)
    job.status = InvoiceStatus.AWAITING_REVIEW
    xml_file = os.path.join(tmp_path, f"{job.id}.xml")
    with open(xml_file, "wb") as f:
        f.write(b"<HDon><TTChung>test</TTChung></HDon>")
    job.pending_file_path = xml_file
    return job


def make_pdf_job(tmp_path: str) -> ProcessingJob:
    job = ProcessingJob.create("hd001.pdf", FileType.PDF)
    job.status = InvoiceStatus.AWAITING_REVIEW
    pdf_file = os.path.join(tmp_path, f"{job.id}.pdf")
    with open(pdf_file, "wb") as f:
        f.write(b"%PDF-1.4 fake content")
    job.pending_file_path = pdf_file
    return job


def test_preview_xml_returns_200_with_xml_content_type():
    with tempfile.TemporaryDirectory() as tmp:
        job = make_xml_job(tmp)
        mock_repo = AsyncMock()
        mock_repo.get.return_value = job
        app.dependency_overrides[get_job_repo] = lambda: mock_repo
        try:
            client = TestClient(app)
            resp = client.get(f"/jobs/{job.id}/preview")
        finally:
            app.dependency_overrides.clear()

        assert resp.status_code == 200
        assert "xml" in resp.headers["content-type"]


def test_preview_pdf_returns_200_with_pdf_content_type():
    with tempfile.TemporaryDirectory() as tmp:
        job = make_pdf_job(tmp)
        mock_repo = AsyncMock()
        mock_repo.get.return_value = job
        app.dependency_overrides[get_job_repo] = lambda: mock_repo
        try:
            client = TestClient(app)
            resp = client.get(f"/jobs/{job.id}/preview")
        finally:
            app.dependency_overrides.clear()

        assert resp.status_code == 200
        assert "pdf" in resp.headers["content-type"]


def test_preview_returns_404_when_job_not_found():
    mock_repo = AsyncMock()
    mock_repo.get.return_value = None
    app.dependency_overrides[get_job_repo] = lambda: mock_repo
    try:
        client = TestClient(app)
        resp = client.get("/jobs/nonexistent-id/preview")
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 404


def test_preview_returns_404_when_file_missing():
    job = ProcessingJob.create("hd001.xml", FileType.XML)
    job.pending_file_path = "/tmp/nonexistent-file-xyz.xml"
    mock_repo = AsyncMock()
    mock_repo.get.return_value = job
    app.dependency_overrides[get_job_repo] = lambda: mock_repo
    try:
        client = TestClient(app)
        resp = client.get(f"/jobs/{job.id}/preview")
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 404


def test_confirm_duplicate_job_returns_400():
    with tempfile.TemporaryDirectory() as tmp:
        job = ProcessingJob.create("hd001.xml", FileType.XML)
        job.status = InvoiceStatus.DUPLICATE
        job.duplicate_of = "some-other-job-id"
        xml_file = os.path.join(tmp, f"{job.id}.xml")
        with open(xml_file, "wb") as f:
            f.write(b"<HDon><TTChung>test</TTChung></HDon>")
        job.pending_file_path = xml_file

        mock_repo = AsyncMock()
        mock_repo.get.return_value = job
        app.dependency_overrides[get_job_repo] = lambda: mock_repo
        try:
            client = TestClient(app)
            resp = client.post(f"/jobs/{job.id}/confirm")
        finally:
            app.dependency_overrides.clear()

        assert resp.status_code == 400
