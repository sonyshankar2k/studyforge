import { DatePipe } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import {
  Component,
  computed,
  effect,
  inject,
  input,
  output,
  signal,
  untracked,
} from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatSnackBar } from '@angular/material/snack-bar';

import { DigitizationJob, ExtractedArm } from '../core/models';
import { StudiesApi } from '../core/studies-api';
import { StatusLabelPipe } from './status-label.pipe';

const MAX_MB = 10;

interface Selection {
  arms: number[];
  objectives: number[];
}

/**
 * Upload a protocol, watch the AI job run live, review what it found, add it to the study.
 *
 * Live updates arrive through the `jobUpdate` input (fed by the page's WebSocket).
 * Updates older than what we already show are ignored, so a late, out-of-order
 * event can never move a job "backwards" on screen.
 */
@Component({
  selector: 'app-digitize-panel',
  imports: [
    DatePipe,
    MatButtonModule,
    MatCardModule,
    MatCheckboxModule,
    MatIconModule,
    MatProgressBarModule,
    StatusLabelPipe,
  ],
  templateUrl: './digitize-panel.html',
  styleUrl: './digitize-panel.scss',
})
export class DigitizePanel {
  readonly studyId = input.required<number>();
  readonly jobUpdate = input<DigitizationJob | null>(null);
  /** Changes after a WebSocket reconnect: refetch, since events may have been missed. */
  readonly refresh = input(0);
  /** Emitted after items are added, so the page reloads the study. */
  readonly applied = output<void>();

  private readonly api = inject(StudiesApi);
  private readonly snack = inject(MatSnackBar);

  protected readonly jobs = signal<DigitizationJob[]>([]);
  protected readonly file = signal<File | null>(null);
  protected readonly uploading = signal(false);
  protected readonly uploadError = signal<string | null>(null);
  protected readonly dragOver = signal(false);
  protected readonly reviewing = signal<number | null>(null);
  protected readonly selections = signal<Record<number, Selection>>({});
  protected readonly applying = signal(false);
  protected readonly hasActiveJob = computed(() =>
    this.jobs().some((j) => j.status === 'queued' || j.status === 'running'),
  );

  /** One key per chosen file: retrying the same upload reuses it (no duplicate jobs). */
  private idempotencyKey = '';

  constructor() {
    effect(() => {
      const id = this.studyId();
      this.refresh();
      untracked(() => this.load(id));
    });
    effect(() => {
      const job = this.jobUpdate();
      if (job) untracked(() => this.upsert(job));
    });
  }

  private load(studyId: number): void {
    this.api.listJobs(studyId).subscribe((jobs) => {
      const recent = jobs.slice(0, 5);
      this.jobs.set(recent);
      recent.forEach((job) => this.ensureSelection(job));
    });
  }

  /** Finished, not-yet-applied jobs start with every addable item selected. */
  private ensureSelection(job: DigitizationJob): void {
    if (job.status === 'succeeded' && !job.applied_at && !this.selections()[job.id]) {
      this.selections.update((s) => ({ ...s, [job.id]: defaultSelection(job) }));
    }
  }

  private upsert(job: DigitizationJob): void {
    if (job.study_id !== this.studyId()) return;
    this.jobs.update((jobs) => {
      const index = jobs.findIndex((j) => j.id === job.id);
      if (index === -1) return [job, ...jobs].slice(0, 5);
      if (jobs[index].updated_at > job.updated_at) return jobs; // stale event
      const copy = [...jobs];
      copy[index] = job;
      return copy;
    });
    this.ensureSelection(job);
  }

  // ---------------- choosing a file ----------------
  protected onFileInput(event: Event): void {
    const input = event.target as HTMLInputElement;
    this.choose(input.files?.[0] ?? null);
    input.value = ''; // allow choosing the same file again later
  }

  protected onDrop(event: DragEvent): void {
    event.preventDefault();
    this.dragOver.set(false);
    this.choose(event.dataTransfer?.files?.[0] ?? null);
  }

  protected onDragOver(event: DragEvent): void {
    event.preventDefault();
    this.dragOver.set(true);
  }

  private choose(file: File | null): void {
    this.uploadError.set(null);
    if (!file) return;
    const name = file.name.toLowerCase();
    if (!name.endsWith('.pdf') && !name.endsWith('.txt')) {
      this.uploadError.set('Choose a PDF or a .txt file.');
      return;
    }
    if (file.size > MAX_MB * 1024 * 1024) {
      this.uploadError.set(`That file is larger than ${MAX_MB} MB.`);
      return;
    }
    this.file.set(file);
    this.idempotencyKey = crypto.randomUUID();
  }

  protected clearFile(): void {
    this.file.set(null);
    this.uploadError.set(null);
  }

  // ---------------- upload ----------------
  protected upload(): void {
    const file = this.file();
    if (!file || this.uploading()) return;
    this.uploading.set(true);
    this.uploadError.set(null);

    this.api.digitize(this.studyId(), file, this.idempotencyKey).subscribe({
      next: (job) => {
        this.uploading.set(false);
        this.file.set(null);
        this.upsert(job);
      },
      error: (err: HttpErrorResponse) => {
        this.uploading.set(false);
        // Keep the file AND the key: pressing Start again is a safe retry.
        this.uploadError.set(uploadMessage(err));
      },
    });
  }

  // ---------------- job actions ----------------
  protected cancel(job: DigitizationJob): void {
    this.api.cancelJob(job.id).subscribe({
      next: (j) => this.upsert(j),
      error: () => this.load(this.studyId()), // it probably finished meanwhile
    });
  }

  protected retry(job: DigitizationJob): void {
    this.api.retryJob(job.id).subscribe({
      next: (j) => this.upsert(j),
      error: () =>
        this.snack.open('Could not restart the job. Try again shortly.', 'OK', { duration: 4000 }),
    });
  }

  protected toggleReview(job: DigitizationJob): void {
    this.reviewing.set(this.reviewing() === job.id ? null : job.id);
  }

  protected isSelected(jobId: number, kind: keyof Selection, index: number): boolean {
    return this.selections()[jobId]?.[kind].includes(index) ?? false;
  }

  protected toggle(jobId: number, kind: keyof Selection, index: number, checked: boolean): void {
    this.selections.update((all) => {
      const current = all[jobId] ?? { arms: [], objectives: [] };
      const list = checked ? [...current[kind], index] : current[kind].filter((i) => i !== index);
      return { ...all, [jobId]: { ...current, [kind]: list } };
    });
  }

  protected selectedCount(jobId: number): number {
    const s = this.selections()[jobId];
    return s ? s.arms.length + s.objectives.length : 0;
  }

  protected apply(job: DigitizationJob): void {
    const selection = this.selections()[job.id];
    if (!selection || this.applying()) return;
    this.applying.set(true);
    this.api.applyJob(job.id, selection).subscribe({
      next: (res) => {
        this.applying.set(false);
        this.reviewing.set(null);
        this.snack.open(
          `Added ${res.arms_added} arms and ${res.objectives_added} objectives to the study`,
          undefined,
          { duration: 3000 },
        );
        this.applied.emit();
        this.load(this.studyId());
      },
      error: (err: HttpErrorResponse) => {
        this.applying.set(false);
        const detail = typeof err.error?.detail === 'string' ? err.error.detail : null;
        this.snack.open(detail ?? 'Could not add the items. Please try again.', 'OK', {
          duration: 5000,
        });
        this.load(this.studyId());
      },
    });
  }

  protected armProblem = armProblem;

  protected sizeLabel(bytes: number): string {
    return bytes < 1024 * 1024
      ? `${Math.ceil(bytes / 1024)} KB`
      : `${(bytes / 1048576).toFixed(1)} MB`;
  }

  protected isActive(job: DigitizationJob): boolean {
    return job.status === 'queued' || job.status === 'running';
  }
}

/** Why an extracted arm can't be added as-is (same rule as the API), or null. */
export function armProblem(arm: ExtractedArm): string | null {
  if (arm.arm_type === 'experimental' && !arm.dose) {
    return 'Experimental arms need a dose. Add this one by hand.';
  }
  return null;
}

/** Pre-select everything that can be added, so reviewing is "untick what's wrong". */
export function defaultSelection(job: DigitizationJob): Selection {
  const result = job.result;
  if (!result) return { arms: [], objectives: [] };
  return {
    arms: result.arms.flatMap((arm, i) => (armProblem(arm) ? [] : [i])),
    objectives: result.objectives.map((_, i) => i),
  };
}

function uploadMessage(err: HttpErrorResponse): string {
  const detail = typeof err.error?.detail === 'string' ? err.error.detail : null;
  if (err.status === 413 || err.status === 415 || err.status === 422) {
    return detail ?? 'This file cannot be processed.';
  }
  return 'Upload failed. Press Start again to retry; it will not create a duplicate job.';
}
