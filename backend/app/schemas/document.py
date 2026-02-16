"""Document API schemas."""

from datetime import datetime

from pydantic import BaseModel


class DocumentUploadResponse(BaseModel):
    id: str
    filename: str
    file_type: str
    file_size: int
    status: str
    chunk_count: int
    created_at: datetime


class DocumentListItem(BaseModel):
    id: str
    filename: str
    original_filename: str
    file_type: str
    file_size: int
    status: str
    created_at: datetime
