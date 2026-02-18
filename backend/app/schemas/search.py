"""Search API schemas."""

from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    limit: int = Field(default=5, ge=1, le=20)
    offset: int = Field(default=0, ge=0)
    min_score: float = Field(default=0.1, ge=0.0, le=1.0)


class SearchResultItem(BaseModel):
    document_id: str
    original_filename: str
    chunk_index: int
    content: str
    score: float


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResultItem]
