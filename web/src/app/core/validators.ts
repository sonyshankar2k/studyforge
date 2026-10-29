import { AbstractControl, AsyncValidatorFn, ValidationErrors } from '@angular/forms';
import { Observable, catchError, map, of, switchMap, timer } from 'rxjs';

import { StudiesApi } from './studies-api';

/**
 * Async validator: checks with the API that the acronym isn't used by another study.
 * The 400ms timer debounces typing; switchMap cancels older in-flight checks.
 */
export function acronymAvailable(
  api: StudiesApi,
  excludeId?: () => number | undefined,
): AsyncValidatorFn {
  return (control: AbstractControl): Observable<ValidationErrors | null> => {
    const value = (control.value ?? '').trim();
    if (!value) return of(null);
    return timer(400).pipe(
      switchMap(() => api.isAcronymAvailable(value, excludeId?.())),
      map((available) => (available ? null : { acronymTaken: true })),
      catchError(() => of(null)), // never block the form because the check failed
    );
  };
}
