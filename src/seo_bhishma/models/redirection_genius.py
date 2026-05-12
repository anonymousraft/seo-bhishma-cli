from pydantic import BaseModel


class UrlMappingResult(BaseModel):
    """Result of mapping a source URL to its best destination match."""

    source: str
    destination: str
    confidence_score: float
    remark: str = ""  # "Check manually", "Error", or ""
