from __future__ import annotations

import os
import time
import uuid

from fastapi.testclient import TestClient

from app.main import app


pytestmark = []
if os.getenv("RUN_DB_INTEGRATION_TESTS") != "1":
    import pytest

    pytestmark.append(pytest.mark.skip(reason="Set RUN_DB_INTEGRATION_TESTS=1 to run DB integration tests"))


def _client() -> TestClient:
    return TestClient(app)


def _login(client: TestClient) -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@structuredintelligence.com", "password": "change_me_immediately"},
    )
    assert response.status_code == 200
    payload = response.json()
    return payload["access_token"]


def test_documents_upload_and_list_with_real_db() -> None:
    token = uuid.uuid4().hex
    unique_name = f"integration-{token}.txt"
    content = f"Integration test document content {token}".encode("utf-8")

    with _client() as client:
        token = _login(client)
        headers = {"Authorization": f"Bearer {token}"}

        upload = client.post(
            "/api/v1/documents/upload",
            headers=headers,
            files={"file": (unique_name, content, "text/plain")},
        )
        assert upload.status_code == 201
        upload_payload = upload.json()
        assert upload_payload["filename"]
        assert upload_payload["file_type"] == "txt"
        assert upload_payload["status"] in {"pending", "processing", "completed"}
        assert upload_payload["chunk_count"] >= 0

        found_doc = None
        for _ in range(20):
            listing = client.get("/api/v1/documents", headers=headers)
            assert listing.status_code == 200
            docs = listing.json()
            assert isinstance(docs, list)
            found_doc = next((doc for doc in docs if doc["original_filename"] == unique_name), None)
            if found_doc and found_doc["status"] == "completed":
                break
            time.sleep(0.25)

        assert found_doc is not None
        assert found_doc["status"] in {"processing", "completed"}


def test_documents_retry_failed_processing_with_real_db() -> None:
    token = uuid.uuid4().hex
    unique_name = f"integration-bad-{token}.pdf"
    content = b"%PDF-1.7\nthis is not a valid pdf body"

    with _client() as client:
        token = _login(client)
        headers = {"Authorization": f"Bearer {token}"}

        upload = client.post(
            "/api/v1/documents/upload",
            headers=headers,
            files={"file": (unique_name, content, "application/pdf")},
        )
        assert upload.status_code == 201
        upload_payload = upload.json()
        document_id = upload_payload["id"]

        found_doc = None
        for _ in range(24):
            listing = client.get("/api/v1/documents", headers=headers)
            assert listing.status_code == 200
            docs = listing.json()
            found_doc = next((doc for doc in docs if doc["id"] == document_id), None)
            if found_doc and found_doc["status"] == "failed":
                break
            time.sleep(0.25)

        assert found_doc is not None
        assert found_doc["status"] == "failed"

        retry = client.post(f"/api/v1/documents/{document_id}/retry", headers=headers)
        assert retry.status_code == 202
        retry_payload = retry.json()
        assert retry_payload["id"] == document_id
        assert retry_payload["status"] == "pending"

        retried_doc = None
        for _ in range(24):
            listing = client.get("/api/v1/documents", headers=headers)
            assert listing.status_code == 200
            docs = listing.json()
            retried_doc = next((doc for doc in docs if doc["id"] == document_id), None)
            if retried_doc and retried_doc["status"] in {"processing", "failed"}:
                if retried_doc["status"] == "failed":
                    break
            time.sleep(0.25)

        assert retried_doc is not None
        assert retried_doc["status"] in {"processing", "failed"}


def test_documents_delete_with_real_db() -> None:
    token = uuid.uuid4().hex
    unique_name = f"integration-delete-{token}.txt"
    content = f"Integration delete document content {token}".encode("utf-8")

    with _client() as client:
        token = _login(client)
        headers = {"Authorization": f"Bearer {token}"}

        upload = client.post(
            "/api/v1/documents/upload",
            headers=headers,
            files={"file": (unique_name, content, "text/plain")},
        )
        assert upload.status_code == 201
        document_id = upload.json()["id"]

        delete_response = client.delete(f"/api/v1/documents/{document_id}", headers=headers)
        assert delete_response.status_code == 204

        listing = client.get("/api/v1/documents", headers=headers)
        assert listing.status_code == 200
        docs = listing.json()
        assert not any(doc["id"] == document_id for doc in docs)


def test_documents_get_detail_with_real_db() -> None:
    token = uuid.uuid4().hex
    unique_name = f"integration-detail-{token}.txt"
    content = f"Integration detail document content {token}".encode("utf-8")

    with _client() as client:
        token = _login(client)
        headers = {"Authorization": f"Bearer {token}"}

        upload = client.post(
            "/api/v1/documents/upload",
            headers=headers,
            files={"file": (unique_name, content, "text/plain")},
        )
        assert upload.status_code == 201
        document_id = upload.json()["id"]

        detail = client.get(f"/api/v1/documents/{document_id}", headers=headers)
        assert detail.status_code == 200
        payload = detail.json()
        assert payload["id"] == document_id
        assert payload["original_filename"] == unique_name
        assert payload["chunk_count"] >= 0


def test_search_with_real_db() -> None:
    token = uuid.uuid4().hex
    unique_text = f"vector-search-term-{token}"
    unique_name = f"integration-search-{token}.txt"
    content = f"This document contains {unique_text} for lookup.".encode("utf-8")

    with _client() as client:
        token = _login(client)
        headers = {"Authorization": f"Bearer {token}"}

        upload = client.post(
            "/api/v1/documents/upload",
            headers=headers,
            files={"file": (unique_name, content, "text/plain")},
        )
        assert upload.status_code == 201
        document_id = upload.json()["id"]

        # Wait for background processing so chunks are searchable.
        for _ in range(24):
            detail = client.get(f"/api/v1/documents/{document_id}", headers=headers)
            assert detail.status_code == 200
            if detail.json()["status"] == "completed":
                break
            time.sleep(0.25)

        search = client.post(
            "/api/v1/search",
            headers=headers,
            json={"query": unique_text, "limit": 5},
        )
        assert search.status_code == 200
        payload = search.json()
        assert payload["query"] == unique_text
        assert any(item["original_filename"] == unique_name for item in payload["results"])
