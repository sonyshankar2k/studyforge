import { HttpErrorResponse } from '@angular/common/http';
import { Component, computed, inject, input, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { Router } from '@angular/router';

import { AuthService } from '../core/auth';

type Mode = 'login' | 'register';

const DEMO_ACCOUNTS = [
  { name: 'Alice', email: 'alice@studyforge.dev' },
  { name: 'Bob', email: 'bob@studyforge.dev' },
  { name: 'Carol', email: 'carol@studyforge.dev' },
];
const DEMO_PASSWORD = 'studyforge';

/** Sign in or create an account. Supports ?returnUrl= to go back after login. */
@Component({
  selector: 'app-login',
  imports: [
    ReactiveFormsModule,
    MatButtonModule,
    MatCardModule,
    MatFormFieldModule,
    MatIconModule,
    MatInputModule,
  ],
  templateUrl: './login.html',
  styleUrl: './login.scss',
})
export class Login {
  /** Bound from the query string by withComponentInputBinding(). */
  readonly returnUrl = input<string>();

  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);
  private readonly fb = inject(FormBuilder).nonNullable;

  protected readonly mode = signal<Mode>('login');
  protected readonly busy = signal(false);
  protected readonly error = signal<string | null>(null);
  protected readonly hidePassword = signal(true);
  protected readonly isRegister = computed(() => this.mode() === 'register');
  protected readonly demoAccounts = DEMO_ACCOUNTS;

  protected readonly form = this.fb.group({
    email: this.fb.control('', [Validators.required, Validators.email]),
    displayName: this.fb.control(''),
    password: this.fb.control('', [Validators.required]),
  });

  protected setMode(mode: Mode): void {
    this.mode.set(mode);
    this.error.set(null);
    const { displayName, password } = this.form.controls;
    // Conditional validation: name and an 8+ char password only matter when registering.
    displayName.setValidators(mode === 'register' ? [Validators.required] : []);
    password.setValidators(
      mode === 'register' ? [Validators.required, Validators.minLength(8)] : [Validators.required],
    );
    displayName.updateValueAndValidity();
    password.updateValueAndValidity();
  }

  protected useDemo(email: string): void {
    this.setMode('login');
    this.form.patchValue({ email, password: DEMO_PASSWORD });
    this.submit();
  }

  protected submit(): void {
    if (this.form.invalid || this.busy()) {
      this.form.markAllAsTouched();
      return;
    }
    const { email, displayName, password } = this.form.getRawValue();
    this.busy.set(true);
    this.error.set(null);

    const request$ = this.isRegister()
      ? this.auth.register(email, displayName, password)
      : this.auth.login(email, password);

    request$.subscribe({
      next: () => this.router.navigateByUrl(this.safeReturnUrl()),
      error: (err: HttpErrorResponse) => {
        this.busy.set(false);
        this.error.set(messageFor(err));
      },
    });
  }

  /** Only allow in-app paths, so ?returnUrl=https://evil.example can't redirect users away. */
  private safeReturnUrl(): string {
    const url = this.returnUrl();
    return url && url.startsWith('/') && !url.startsWith('//') ? url : '/';
  }
}

function messageFor(err: HttpErrorResponse): string {
  if (err.status === 401) return 'Incorrect email or password.';
  if (err.status === 409) return 'An account with this email already exists. Sign in instead.';
  if (err.status === 422) return 'Please check the details and try again.';
  if (err.status === 0) return 'Cannot reach the server. Is the API running?';
  return 'Something went wrong. Please try again.';
}
