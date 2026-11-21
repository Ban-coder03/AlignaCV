"""Tests HTTP (requieren fastapi + httpx: pip install -r requirements-dev.txt)."""
import io
import os

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
os.environ["USE_MOCK_AI"] = "true"
os.environ["RATE_LIMIT_PER_MINUTE"] = "0"

from fastapi.testclient import TestClient  # noqa: E402

from conftest import CV, JD  # noqa: E402
from main import app  # noqa: E402
from test_services import make_docx, make_pdf  # noqa: E402

client = TestClient(app, raise_server_exceptions=False)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["mode"] == "mock"


def test_analyze_ok_contract():
    r = client.post("/api/analyze", json={"cv_text": CV, "job_description": JD, "tone": "executive", "target_section": "experience"})
    assert r.status_code == 200
    body = r.json()
    for key in ("compatibility_score", "score_breakdown", "summary", "missing_keywords", "improvements", "rewritten_section", "meta"):
        assert key in body
    assert set(body["missing_keywords"]) == {"technical", "soft"}
    assert set(body["rewritten_section"]) >= {"section_name", "original_excerpt", "improved_text", "rationale"}


def test_analyze_validation_errors_do_not_echo_input():
    r = client.post("/api/analyze", json={"cv_text": "corto", "job_description": JD})
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_input"
    assert "corto" not in r.text
    assert client.post("/api/analyze", json={"cv_text": CV, "job_description": CV}).status_code == 422
    assert client.post("/api/analyze", content=b"{bad", headers={"content-type": "application/json"}).status_code == 422


def test_missing_key_is_controlled_error(monkeypatch):
    monkeypatch.setenv("USE_MOCK_AI", "false")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    r = client.post("/api/analyze", json={"cv_text": CV, "job_description": JD})
    assert r.status_code == 503 and r.json()["error"]["code"] == "ai_not_configured"
    assert "Traceback" not in r.text


def test_extract_text():
    r = client.post("/api/extract-text", files={"file": ("cv.pdf", make_pdf(), "application/pdf")})
    assert r.status_code == 200 and r.json()["file_type"] == "pdf"
    r = client.post("/api/extract-text", files={"file": ("cv.docx", make_docx(), "application/octet-stream")})
    assert r.status_code == 200 and r.json()["file_type"] == "docx"
    assert client.post("/api/extract-text", files={"file": ("a.txt", b"hola", "text/plain")}).status_code == 415
    assert client.post("/api/extract-text").status_code == 422


def test_cors_preflight():
    r = client.options("/api/analyze", headers={"Origin": "http://localhost:5500", "Access-Control-Request-Method": "POST"})
    assert r.status_code == 200 and "access-control-allow-origin" in r.headers
