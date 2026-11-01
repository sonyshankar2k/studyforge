"""Business-rule errors in the same shape FastAPI uses for validation errors.

FastAPI documents every 422 as `{"detail": [{"loc": [...], "msg": "...", "type": "..."}]}`.
Returning that same shape for our own rules (duplicate names, missing dose...) keeps
the API contract consistent, and `loc` tells a form which field to highlight.
"""

from fastapi import HTTPException, status


def unprocessable(message: str, field: str | None = None) -> HTTPException:
    loc = ["body", field] if field else ["body"]
    return HTTPException(
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail=[{"loc": loc, "msg": message, "type": "value_error"}],
    )
