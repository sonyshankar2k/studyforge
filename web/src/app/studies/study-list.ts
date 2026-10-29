import { DatePipe } from '@angular/common';
import { Component, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatChipsModule } from '@angular/material/chips';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatSelectModule } from '@angular/material/select';
import { Router, RouterLink } from '@angular/router';

import { PHASES, StudyPhase, StudySummary } from '../core/models';
import { StudiesApi } from '../core/studies-api';
import { acronymAvailable } from '../core/validators';
import { StatusLabelPipe } from './status-label.pipe';

@Component({
  selector: 'app-study-list',
  imports: [
    ReactiveFormsModule,
    RouterLink,
    DatePipe,
    MatButtonModule,
    MatCardModule,
    MatChipsModule,
    MatFormFieldModule,
    MatIconModule,
    MatInputModule,
    MatProgressBarModule,
    MatSelectModule,
    StatusLabelPipe,
  ],
  templateUrl: './study-list.html',
  styleUrl: './study-list.scss',
})
export class StudyList {
  private readonly api = inject(StudiesApi);
  private readonly router = inject(Router);
  private readonly fb = inject(FormBuilder).nonNullable;

  protected readonly studies = signal<StudySummary[]>([]);
  protected readonly loading = signal(true);
  protected readonly showCreate = signal(false);
  protected readonly saving = signal(false);
  protected readonly error = signal<string | null>(null);
  protected readonly phases = PHASES;

  // Typed reactive form: TypeScript knows every control's value type.
  protected readonly form = this.fb.group({
    title: this.fb.control('', [Validators.required, Validators.minLength(3)]),
    acronym: this.fb.control('', {
      validators: [Validators.maxLength(50)],
      asyncValidators: [acronymAvailable(this.api)],
    }),
    phase: this.fb.control<StudyPhase>('Phase 1'),
    therapeutic_area: this.fb.control(''),
  });

  constructor() {
    this.load();
  }

  protected load(): void {
    this.loading.set(true);
    this.api.listStudies().subscribe({
      next: (studies) => {
        this.studies.set(studies);
        this.loading.set(false);
      },
      error: () => {
        this.error.set('Could not reach the API. Is the backend running on port 8000?');
        this.loading.set(false);
      },
    });
  }

  protected create(): void {
    if (this.form.invalid || this.form.pending) return;
    const v = this.form.getRawValue();
    this.saving.set(true);
    this.api
      .createStudy({
        title: v.title.trim(),
        acronym: v.acronym.trim() || null,
        phase: v.phase,
        therapeutic_area: v.therapeutic_area.trim() || null,
      })
      .subscribe({
        next: (study) => this.router.navigate(['/studies', study.id]),
        error: () => this.saving.set(false),
      });
  }
}
