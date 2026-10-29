import { HttpInterceptorFn } from '@angular/common/http';
import { Injectable, effect, inject, signal } from '@angular/core';

export const DEMO_USERS = ['Alice', 'Bob', 'Carol'];

/**
 * Who is editing. Stored per browser tab (sessionStorage), so you can open
 * two tabs as different users and watch live updates and conflicts.
 * Week 1 task: replace with real JWT login.
 */
@Injectable({ providedIn: 'root' })
export class CurrentUser {
  readonly name = signal(readStored() ?? DEMO_USERS[0]);

  constructor() {
    effect(() => {
      try {
        sessionStorage.setItem('studyforge.user', this.name());
      } catch {
        /* storage unavailable: fine, keep it in memory */
      }
    });
  }
}

function readStored(): string | null {
  try {
    return sessionStorage.getItem('studyforge.user');
  } catch {
    return null;
  }
}

/** Adds the X-User header to every API call. */
export const currentUserInterceptor: HttpInterceptorFn = (req, next) => {
  const user = inject(CurrentUser).name();
  return next(req.clone({ setHeaders: { 'X-User': user } }));
};
