import { HttpClient, provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { Component } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import {
  ActivatedRouteSnapshot,
  Router,
  RouterStateSnapshot,
  UrlTree,
  provideRouter,
} from '@angular/router';

import { AuthService, authGuard, authInterceptor } from './auth';

const SESSION = {
  token: 'test-token',
  user: { id: 1, email: 'alice@studyforge.dev', display_name: 'Alice' },
};

@Component({ template: '' })
class Blank {}

function setup(signedIn: boolean) {
  sessionStorage.clear();
  if (signedIn) sessionStorage.setItem('studyforge.session', JSON.stringify(SESSION));
  TestBed.configureTestingModule({
    providers: [
      provideRouter([{ path: 'login', component: Blank }]),
      provideHttpClient(withInterceptors([authInterceptor])),
      provideHttpClientTesting(),
    ],
  });
  return {
    http: TestBed.inject(HttpClient),
    httpMock: TestBed.inject(HttpTestingController),
    auth: TestBed.inject(AuthService),
    router: TestBed.inject(Router),
  };
}

function runGuard(url: string) {
  return TestBed.runInInjectionContext(() =>
    authGuard({} as ActivatedRouteSnapshot, { url } as RouterStateSnapshot),
  );
}

describe('authGuard', () => {
  afterEach(() => sessionStorage.clear());

  it('lets a signed-in user through', () => {
    setup(true);
    expect(runGuard('/studies/1')).toBe(true);
  });

  it('sends a signed-out user to /login and remembers where they were going', () => {
    const { router } = setup(false);
    const result = runGuard('/studies/1') as UrlTree;
    expect(router.serializeUrl(result)).toBe('/login?returnUrl=%2Fstudies%2F1');
  });
});

describe('authInterceptor', () => {
  afterEach(() => sessionStorage.clear());

  it('adds the bearer token to API calls', () => {
    const { http, httpMock } = setup(true);
    http.get('/api/studies').subscribe();
    const req = httpMock.expectOne('/api/studies');
    expect(req.request.headers.get('Authorization')).toBe('Bearer test-token');
    req.flush([]);
  });

  it('does not send a token to the login endpoint', () => {
    const { http, httpMock } = setup(true);
    http.post('/api/auth/login', {}).subscribe({ error: () => undefined });
    const req = httpMock.expectOne('/api/auth/login');
    expect(req.request.headers.has('Authorization')).toBe(false);
    req.flush({});
  });

  it('signs the user out when the API answers 401', () => {
    const { http, httpMock, auth } = setup(true);
    expect(auth.isLoggedIn()).toBe(true);

    http.get('/api/studies').subscribe({ error: () => undefined });
    httpMock
      .expectOne('/api/studies')
      .flush('expired', { status: 401, statusText: 'Unauthorized' });

    expect(auth.isLoggedIn()).toBe(false);
    expect(sessionStorage.getItem('studyforge.session')).toBeNull();
  });
});
