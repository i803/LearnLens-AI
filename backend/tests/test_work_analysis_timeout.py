import asyncio
import hashlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app


def test_bundled_sample_analysis_skips_pdf_rendering_ai_and_persistence(monkeypatch):
    from app import persistence as persistence_module
    from app.routers import ai as ai_router

    project_root = Path(__file__).resolve().parents[2]
    sample_path = project_root / "web" / "public" / "sample_math_test.pdf"
    sample_bytes = sample_path.read_bytes()
    assert hashlib.sha256(sample_bytes).hexdigest() == ai_router.BUNDLED_DEMO_PDF_SHA256

    def unexpected_render(*_args, **_kwargs):
        pytest.fail("The bundled demo PDF should not be rendered during analysis")

    async def unexpected_persist(*_args, **_kwargs):
        pytest.fail("Synthetic bundled demo results must not be persisted as student work")

    monkeypatch.setattr(ai_router, "pdf_to_inputs", unexpected_render)
    monkeypatch.setattr(persistence_module.persistence, "save_work_analysis", unexpected_persist)

    with TestClient(app) as client:
        response = client.post(
            "/work/analyze",
            files={"files": ("sample_math_test.pdf", sample_bytes, "application/pdf")},
            data={"studentId": "demo-fast-path-test"},
        )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["source"] == "demo"
    assert payload["provider"] == "Bundled sample"
    assert len(payload["questions"]) >= 1


def test_ai_analysis_has_a_shared_timeout_budget(monkeypatch):
    from app import services

    class SlowClient:
        async def complete_json(self, *_args, **_kwargs):
            await asyncio.sleep(0.2)
            return {}

    monkeypatch.setattr(services, "client", SlowClient())
    monkeypatch.setattr(services, "WORK_ANALYSIS_TIMEOUT_SECONDS", 0.03)

    with pytest.raises(RuntimeError, match="0.03-second AI processing budget"):
        asyncio.run(services.analyze_work("Question 1: calculate 1 + 1", [], student_id="timeout-test"))


def test_pdf_preprocessing_rejects_excessive_page_count():
    import fitz
    from app.parsing import pdf_to_inputs
    from app.config import MAX_PDF_PAGES

    doc = fitz.open()
    for _ in range(MAX_PDF_PAGES + 1):
        doc.new_page()
    pdf_bytes = doc.tobytes()
    doc.close()

    with pytest.raises(ValueError, match=f"limited to {MAX_PDF_PAGES} pages"):
        pdf_to_inputs(pdf_bytes)
