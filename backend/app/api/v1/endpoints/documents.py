"""Document endpoints."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Request, Response, UploadFile, status
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session, get_current_user
from app.core.database import SessionLocal
from app.models import User
from app.repositories import DocumentRepository
from app.schemas.document import DocumentListItem, DocumentUploadResponse
from app.services.document_service import DocumentService


router = APIRouter(prefix="/documents")


async def process_document_in_background(document_id: UUID) -> None:
    async with SessionLocal() as session:
        service = DocumentService(session)
        await service.process_document(document_id)


@router.post("/upload", response_model=DocumentUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    session: AsyncSession = Depends(db_session),
    current_user: User = Depends(get_current_user),
) -> DocumentUploadResponse:
    request_id = getattr(request.state, "request_id", None)
    log = logger.bind(
        request_id=request_id,
        action="document_upload",
        user_id=str(current_user.id),
        filename=file.filename,
    )
    log.info("Upload request received")

    service = DocumentService(session)
    repo = DocumentRepository(session)
    try:
        doc, is_new = await service.stage_upload(user_id=current_user.id, upload=file)
        if is_new:
            background_tasks.add_task(process_document_in_background, doc.id)
    except ValueError as exc:
        log.warning("Upload rejected: {reason}", reason=str(exc))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        log.exception("Upload failed: {}", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process uploaded document",
        )
    if is_new:
        log.info("Upload staged document_id={document_id} status={status}", document_id=str(doc.id), status=doc.status)
    else:
        log.info("Upload deduplicated document_id={document_id} status={status}", document_id=str(doc.id), status=doc.status)

    chunk_count = 0 if is_new else await repo.count_chunks(doc.id)
    return DocumentUploadResponse(
        id=str(doc.id),
        filename=doc.filename,
        file_type=doc.file_type,
        file_size=doc.file_size,
        status=doc.status,
        chunk_count=chunk_count,
        processing_error=getattr(doc, "processing_error", None),
        created_at=doc.created_at,
    )


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: UUID,
    request: Request,
    session: AsyncSession = Depends(db_session),
    current_user: User = Depends(get_current_user),
) -> Response:
    request_id = getattr(request.state, "request_id", None)
    service = DocumentService(session)
    deleted = await service.delete_document_for_user(document_id=document_id, user_id=current_user.id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    logger.bind(
        request_id=request_id,
        action="document_delete",
        user_id=str(current_user.id),
        document_id=str(document_id),
    ).info("Document deleted")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("", response_model=list[DocumentListItem])
async def list_documents(
    request: Request,
    session: AsyncSession = Depends(db_session),
    current_user: User = Depends(get_current_user),
) -> list[DocumentListItem]:
    repo = DocumentRepository(session)
    docs = await repo.list_for_user(current_user.id)
    chunk_counts = await repo.chunk_counts_for_user(current_user.id)
    logger.bind(
        request_id=getattr(request.state, "request_id", None),
        action="documents_list",
        user_id=str(current_user.id),
    ).info("Documents listed count={count}", count=len(docs))
    return [
        DocumentListItem(
            id=str(doc.id),
            filename=doc.filename,
            original_filename=doc.original_filename,
            file_type=doc.file_type,
            file_size=doc.file_size,
            status=doc.status,
            chunk_count=chunk_counts.get(doc.id, 0),
            processing_error=getattr(doc, "processing_error", None),
            created_at=doc.created_at,
        )
        for doc in docs
    ]


@router.get("/{document_id}", response_model=DocumentListItem)
async def get_document(
    document_id: UUID,
    request: Request,
    session: AsyncSession = Depends(db_session),
    current_user: User = Depends(get_current_user),
) -> DocumentListItem:
    repo = DocumentRepository(session)
    doc = await repo.get_for_user(document_id=document_id, user_id=current_user.id)
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    logger.bind(
        request_id=getattr(request.state, "request_id", None),
        action="document_get",
        user_id=str(current_user.id),
        document_id=str(document_id),
    ).info("Document fetched")

    return DocumentListItem(
        id=str(doc.id),
        filename=doc.filename,
        original_filename=doc.original_filename,
        file_type=doc.file_type,
        file_size=doc.file_size,
        status=doc.status,
        chunk_count=await repo.count_chunks(doc.id),
        processing_error=getattr(doc, "processing_error", None),
        created_at=doc.created_at,
    )


@router.post("/{document_id}/retry", response_model=DocumentUploadResponse, status_code=status.HTTP_202_ACCEPTED)
async def retry_document_processing(
    document_id: UUID,
    request: Request,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(db_session),
    current_user: User = Depends(get_current_user),
) -> DocumentUploadResponse:
    request_id = getattr(request.state, "request_id", None)
    repo = DocumentRepository(session)
    doc = await repo.get_for_user(document_id=document_id, user_id=current_user.id)
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    if doc.status != "failed":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only failed documents can be retried")

    await repo.update_status(doc, status="pending", processing_error=None)
    background_tasks.add_task(process_document_in_background, doc.id)

    logger.bind(
        request_id=request_id,
        action="document_retry",
        user_id=str(current_user.id),
        document_id=str(doc.id),
    ).info("Document processing retry scheduled")

    return DocumentUploadResponse(
        id=str(doc.id),
        filename=doc.filename,
        file_type=doc.file_type,
        file_size=doc.file_size,
        status=doc.status,
        chunk_count=await repo.count_chunks(doc.id),
        processing_error=getattr(doc, "processing_error", None),
        created_at=doc.created_at,
    )
