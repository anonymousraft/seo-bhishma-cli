from pydantic import BaseModel


class BacklinkCheckRequest(BaseModel):
    """Input for a single backlink check."""

    backlink_url: str
    target_url: str
    expected_anchor: str = ""


class BacklinkCheckResult(BaseModel):
    """Result of a single backlink check."""

    backlink_url: str
    target_url: str
    status: str  # "Live", "Not Live", "Not Found", "Error"
    anchor_status: str  # "Present", "Missing", "N/A"
    link_exists: str  # "Yes", "No"
    actual_anchor_text: str | None = None
    http_status: int | None = None
    rel_values: list[str] = []  # e.g. ["nofollow"], ["sponsored", "ugc"]
    is_dofollow: bool | None = None
