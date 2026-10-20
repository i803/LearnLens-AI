from pathlib import Path
import json

from fastapi.testclient import TestClient

from app.main import app
from app.notes import MISCONCEPTIONS, NOTES, NOTES_PATH, MISCONCEPTIONS_PATH


def test_bundled_learning_data_is_loaded_and_matches_expected_minimums():
    assert NOTES_PATH.exists(), f"Missing notes bundle: {NOTES_PATH}"
    assert MISCONCEPTIONS_PATH.exists(), f"Missing misconception bundle: {MISCONCEPTIONS_PATH}"
    assert len(NOTES) >= 45
    assert len(MISCONCEPTIONS) >= 22
    assert all(item.get("id") and item.get("content") for item in NOTES)
    assert all(item.get("id") and item.get("label") for item in MISCONCEPTIONS)


def test_backend_entrypoint_and_vercel_manifest_exist():
    backend_root = Path(__file__).resolve().parents[1]
    project_root = backend_root.parent
    assert (backend_root / "index.py").exists()
    # This repository deploys frontend and backend as services in the root manifest.
    manifest = json.loads((project_root / "vercel.json").read_text(encoding="utf-8"))
    backend_service = manifest["services"]["backend"]
    assert backend_service["framework"] == "fastapi"
    assert backend_service["entrypoint"] == "index:app"
    assert backend_service["functions"]["index.py"]["maxDuration"] <= 60
    assert (backend_root / "content" / "notes.json").exists()
    assert (backend_root / "content" / "misconceptions.json").exists()


def test_health_endpoint_reports_content_inventory():
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["notesCount"] >= 45
    assert payload["misconceptionCount"] >= 22


def test_retrieval_surfaces_notes_for_topics_beyond_sets():
    from app.notes import search_notes
    expectations = {
        "alternating signs three by three determinant middle term": "mat-03",
        "add fractions common denominator": "alg-03",
        "units dimensions seconds metres": "unit-01",
        "union intersection membership both sets": "set-33",
        "matrix row operation entire row": "mat-01",
    }
    for query, expected_id in expectations.items():
        matches = search_notes(query, limit=3)
        assert matches, f"No retrieved notes for query: {query}"
        assert expected_id in [match["id"] for match in matches], f"Expected {expected_id} for: {query}"


def test_added_notes_disclose_provenance_and_review_status():
    original = [n for n in NOTES if n.get("attribution") == "LearnLens team-authored teaching note"]
    drafts = [n for n in NOTES if "AI-assisted teaching-note draft" in str(n.get("attribution", ""))]
    assert len(original) == 32
    assert len(drafts) == 13
    assert all("review pending" in n["attribution"].lower() for n in drafts)
    assert all(n.get("license") for n in NOTES)


def test_lesson_response_exposes_note_provenance_to_ui(monkeypatch):
    import asyncio
    from app import services
    from app.schemas import LessonGenerateRequest

    class FailingClient:
        async def complete_json(self, *args, **kwargs):
            raise RuntimeError("synthetic provider outage")

    monkeypatch.setattr(services, "client", FailingClient())
    result = asyncio.run(services.lesson(LessonGenerateRequest(
        studentId="test-student", conceptId="matrices", conceptName="Matrices",
        subject="Mathematics", topic="determinant alternating signs three by three",
        language="en", misconceptionTag="other", evidence=[]
    )))
    assert result.sources
    source_ids = {source.id for source in result.sources}
    assert "mat-03" in source_ids
    draft_source = next(source for source in result.sources if source.id == "mat-03")
    assert "AI-assisted teaching-note draft" in draft_source.attribution
    assert "review pending" in draft_source.attribution.lower()
    assert draft_source.license == "Review licensing before external reuse"


def test_configured_or_hosted_environment_never_enables_synthetic_teacher_data(monkeypatch):
    from app import config
    monkeypatch.setattr(config, "DEMO_MODE", True)
    monkeypatch.setattr(config, "ENV_FILE_PRESENT", True)
    assert config.demo_data_enabled() is False

    monkeypatch.setattr(config, "ENV_FILE_PRESENT", False)
    monkeypatch.setattr(config, "SUPABASE_URL", "")
    monkeypatch.setattr(config, "SUPABASE_SECRET_KEY", "")
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", "")
    monkeypatch.setattr(config, "GEMINI_API_KEY", "")
    monkeypatch.setenv("VERCEL", "1")
    assert config.demo_data_enabled() is False
