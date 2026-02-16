"""Document endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session, get_current_user
from app.models import User
from app.repositories import DocumentRepository
from app.schemas.document import DocumentListItem, DocumentUploadResponse
from app.services.document_service import DocumentService


router = APIRouter(prefix="/documents")


@router.post("/upload", response_model=DocumentUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(...),
    session: AsyncSession = Depends(db_session),
    current_user: User = Depends(get_current_user),
) -> DocumentUploadResponse:
    service = DocumentService(session)
    try:
        doc, chunk_count = await service.ingest_upload(user_id=current_user.id, upload=file)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        logger.exception("Document upload failed: {}", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process uploaded document",
        )

    return DocumentUploadResponse(
        id=str(doc.id),
        filename=doc.filename,
        file_type=doc.file_type,
        file_size=doc.file_size,
        status=doc.status,
        chunk_count=chunk_count,
        created_at=doc.created_at,
    )


@router.get("", response_model=list[DocumentListItem])
async def list_documents(
    session: AsyncSession = Depends(db_session),
    current_user: User = Depends(get_current_user),
) -> list[DocumentListItem]:
    docs = await DocumentRepository(session).list_for_user(current_user.id)
    return [
        DocumentListItem(
            id=str(doc.id),
            filename=doc.filename,
            original_filename=doc.original_filename,
            file_type=doc.file_type,
            file_size=doc.file_size,
            status=doc.status,
            created_at=doc.created_at,
        )
        for doc in docs
    ]

