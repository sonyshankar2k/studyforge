import { HttpClient, HttpErrorResponse, HttpInterceptorFn, HttpParams } from '@angular/common/http';
import { Injectable, computed, inject, signal } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { Observable, catchError, tap, throwError } from 'rxjs';

export interface AuthUser {
  id: number;
  email: string;
  display_name: string;
}

interface TokenResponse {
  access_token: string;
  token_type: 'bearer';
  user: AuthUser;
}

interface StoredSession {
  token: string;
  user: AuthUser;
}

const STORAGE_KEY = 'studyforge.session';

/**
 * Holds the signed-in user and their JWT as signals.
 *
 * Storage choice: sessionStorage, so each browser TAB has its own login
 * (handy for the two-user collaboration demo) and closing the tab signs out.
 * Trade-off: any script on the page can read it, so XSS protection matters.
 * The more secure production option is an HttpOnly, Secure, SameSite cookie
 * set by the API, which JavaScript cannot read at all.
 */
@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly http = inject(HttpClient);
  private readonly router = inject(Router);

  private readonly session = signal<StoredSession | null>(readSession());

  readonly user = computed(() => this.session()?.user ?? null);
  readonly token = computed(() => this.session()?.token ?? null);
  readonly isLoggedIn = computed(() => this.session() !== null);

  login(email: string, password: string): Observable<TokenResponse> {
    // OAuth2 password flow: form-encoded `username` + `password`.
    const body = new HttpParams().set('username', email.trim()).set('password', password);
    return this.http
      .post<TokenResponse>('/api/auth/login', body)
      .pipe(tap((res) => this.store(res)));
  }

  register(email: string, displayName: string, password: string): Observable<TokenResponse> {
    return this.http
      .post<TokenResponse>('/api/auth/register', {
        email: email.trim(),
        display_name: displayName.trim(),
        password,
      })
      .pipe(tap((res) => this.store(res)));
  }

  logout(returnUrl?: string): void {
    this.session.set(null);
    try {
      sessionStorage.removeItem(STORAGE_KEY);
    } catch {
      /* storage unavailable */
    }
    this.router.navigate(['/login'], returnUrl ? { queryParams: { returnUrl } } : {});
  }

  private store(res: TokenResponse): void {
    const session: StoredSession = { token: res.access_token, user: res.user };
    this.session.set(session);
    try {
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(session));
    } catch {
      /* storage unavailable: keep the session in memory only */
    }
  }
}

function readSession(): StoredSession | null {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as StoredSession) : null;
  } catch {
    return null;
  }
}

/**
 * Adds `Authorization: Bearer <token>` to API calls.
 * If the API answers 401 (expired or invalid token), sign out and go to /login,
 * remembering where the user was so they land back there after signing in.
 */
export const authInterceptor: HttpInterceptorFn = (req, next) => {
  const auth = inject(AuthService);
  const router = inject(Router);
  const token = auth.token();
  const isAuthCall =
    req.url.startsWith('/api/auth/login') || req.url.startsWith('/api/auth/register');

  const authed =
    token && !isAuthCall ? req.clone({ setHeaders: { Authorization: `Bearer ${token}` } }) : req;

  return next(authed).pipe(
    catchError((err: unknown) => {
      if (err instanceof HttpErrorResponse && err.status === 401 && !isAuthCall) {
        auth.logout(router.url);
      }
      return throwError(() => err);
    }),
  );
};

/** Route guard: only signed-in users may enter; others go to /login. */
export const authGuard: CanActivateFn = (_route, state) => {
  const auth = inject(AuthService);
  if (auth.isLoggedIn()) return true;
  return inject(Router).createUrlTree(['/login'], { queryParams: { returnUrl: state.url } });
};

/** Route guard for /login: signed-in users skip straight to the app. */
export const guestGuard: CanActivateFn = () => {
  const auth = inject(AuthService);
  return auth.isLoggedIn() ? inject(Router).createUrlTree(['/']) : true;
};
