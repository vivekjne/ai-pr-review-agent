"""
Data Schemas (Pydantic Models)
==============================
Defines the data structures used throughout the application.

Why Pydantic?
    - Validates data at runtime (invalid data = clear error)
    - Converts JSON/dicts to typed Python objects automatically
    - Provides excellent IDE support (autocomplete, type checking)
    - Serialises back to JSON/dict seamlessly

Key models:
    - ReviewRequest  → API request body (url or owner/repo/pull_number)
    - ReviewResponse → API response body (review result)
    - SkippedFile    → Metadata about a skipped file
"""

from app.schemas.review import (
    ErrorResponse,
    ReviewRequest,
    ReviewResponse,
    SkippedFile,
)  # noqa: F401
