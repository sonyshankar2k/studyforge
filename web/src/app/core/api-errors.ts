import { HttpErrorResponse } from '@angular/common/http';

/**
 * A readable message from an API error.
 * 422s use FastAPI's shape: {"detail": [{"loc": [...], "msg": "..."}]};
 * other errors use {"detail": "..."}.
 */
export function apiErrorMessage(
  err: unknown,
  fallback = 'Something went wrong. Please try again.',
): string {
  if (!(err instanceof HttpErrorResponse)) return fallback;
  const detail = err.error?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail) && typeof detail[0]?.msg === 'string') {
    return detail[0].msg.replace(/^Value error, /, '');
  }
  if (err.status === 0) return 'Cannot reach the server. Check your connection.';
  return fallback;
}
