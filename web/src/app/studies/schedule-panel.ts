import { HttpErrorResponse } from '@angular/common/http';
import { Component, computed, effect, inject, input, signal, untracked } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatMenuModule } from '@angular/material/menu';
import { MatSnackBar } from '@angular/material/snack-bar';
import { MatTooltipModule } from '@angular/material/tooltip';

import { apiErrorMessage } from '../core/api-errors';
import { Activity, Encounter, Schedule } from '../core/models';
import { StudiesApi } from '../core/studies-api';

const EMPTY: Schedule = { encounters: [], activities: [], cells: [] };

export function cellKey(encounterId: number, activityId: number): string {
  return `${encounterId}:${activityId}`;
}

/** "Day 29 (±3)", "Day -14", "Day 1 (-0/+2)". */
export function visitTiming(e: Encounter): string {
  const window =
    e.window_before === 0 && e.window_after === 0
      ? ''
      : e.window_before === e.window_after
        ? ` (±${e.window_before})`
        : ` (-${e.window_before}/+${e.window_after})`;
  return `Day ${e.day}${window}`;
}

/**
 * The Schedule of Activities: visits across the top, activities down the side,
 * a tick where an activity happens at a visit.
 *
 * Ticking is optimistic (the box changes at once) and is rolled back if the save fails.
 * The API call says the state we want ("planned": true/false), not "toggle", so a
 * double click or a retry can never flip the cell back by accident.
 */
@Component({
  selector: 'app-schedule-panel',
  imports: [
    ReactiveFormsModule,
    MatButtonModule,
    MatCardModule,
    MatFormFieldModule,
    MatIconModule,
    MatInputModule,
    MatMenuModule,
    MatTooltipModule,
  ],
  templateUrl: './schedule-panel.html',
  styleUrl: './schedule-panel.scss',
})
export class SchedulePanel {
  readonly studyId = input.required<number>();
  readonly refresh = input(0);

  private readonly api = inject(StudiesApi);
  private readonly snack = inject(MatSnackBar);
  private readonly fb = inject(FormBuilder).nonNullable;

  protected readonly schedule = signal<Schedule>(EMPTY);
  protected readonly loaded = signal(false);
  /** Cells waiting for the server, so a second click can't race the first. */
  protected readonly pending = signal<ReadonlySet<string>>(new Set());
  protected readonly showVisitForm = signal(false);
  protected readonly busy = signal(false);

  protected readonly planned = computed(
    () => new Set(this.schedule().cells.map((c) => cellKey(c.encounter_id, c.activity_id))),
  );
  protected readonly countByVisit = computed(() => {
    const counts = new Map<number, number>();
    for (const c of this.schedule().cells)
      counts.set(c.encounter_id, (counts.get(c.encounter_id) ?? 0) + 1);
    return counts;
  });

  protected readonly visitForm = this.fb.group({
    name: this.fb.control('', [Validators.required, Validators.maxLength(100)]),
    day: this.fb.control<number | null>(null, [
      Validators.required,
      Validators.min(-365),
      Validators.max(3650),
    ]),
    window_before: this.fb.control(0, [Validators.min(0), Validators.max(90)]),
    window_after: this.fb.control(0, [Validators.min(0), Validators.max(90)]),
  });
  protected readonly activityName = this.fb.control('', [
    Validators.required,
    Validators.maxLength(200),
  ]);

  protected readonly timing = visitTiming;
  protected readonly key = cellKey;

  constructor() {
    effect(() => {
      const id = this.studyId();
      this.refresh();
      untracked(() => this.load(id));
    });
  }

  private load(studyId = this.studyId()): void {
    this.api.getSchedule(studyId).subscribe((schedule) => {
      this.schedule.set(schedule);
      this.loaded.set(true);
    });
  }

  protected isPlanned(e: Encounter, a: Activity): boolean {
    return this.planned().has(cellKey(e.id, a.id));
  }

  protected isPending(e: Encounter, a: Activity): boolean {
    return this.pending().has(cellKey(e.id, a.id));
  }

  // ---------------- cells ----------------
  protected toggle(e: Encounter, a: Activity): void {
    const key = cellKey(e.id, a.id);
    if (this.pending().has(key)) return;
    const want = !this.planned().has(key);

    this.setLocal(e.id, a.id, want); // optimistic
    this.pending.update((s) => new Set(s).add(key));

    this.api.setCell(this.studyId(), e.id, a.id, want).subscribe({
      next: () => this.clearPending(key),
      error: (err) => {
        this.clearPending(key);
        this.setLocal(e.id, a.id, !want); // roll back
        this.snack.open(apiErrorMessage(err, 'Could not update the schedule.'), 'OK', {
          duration: 4000,
        });
        if (err instanceof HttpErrorResponse && err.status === 404) this.load();
      },
    });
  }

  private setLocal(encounterId: number, activityId: number, planned: boolean): void {
    this.schedule.update((s) => {
      const others = s.cells.filter(
        (c) => !(c.encounter_id === encounterId && c.activity_id === activityId),
      );
      return {
        ...s,
        cells: planned
          ? [...others, { encounter_id: encounterId, activity_id: activityId }]
          : others,
      };
    });
  }

  private clearPending(key: string): void {
    this.pending.update((s) => {
      const next = new Set(s);
      next.delete(key);
      return next;
    });
  }

  // ---------------- visits and activities ----------------
  protected addVisit(): void {
    if (this.visitForm.invalid || this.busy()) {
      this.visitForm.markAllAsTouched();
      return;
    }
    const v = this.visitForm.getRawValue();
    this.busy.set(true);
    this.api
      .createEncounter(this.studyId(), {
        name: v.name.trim(),
        day: v.day ?? 1,
        window_before: v.window_before || 0,
        window_after: v.window_after || 0,
      })
      .subscribe({
        next: () => {
          this.busy.set(false);
          this.visitForm.reset({ name: '', day: null, window_before: 0, window_after: 0 });
          this.showVisitForm.set(false);
          this.load();
        },
        error: (err) => this.fail(err, 'Could not add the visit.'),
      });
  }

  protected addActivity(): void {
    if (this.activityName.invalid || this.busy()) {
      this.activityName.markAsTouched();
      return;
    }
    this.busy.set(true);
    this.api.createActivity(this.studyId(), this.activityName.value.trim()).subscribe({
      next: () => {
        this.busy.set(false);
        this.activityName.reset();
        this.load();
      },
      error: (err) => this.fail(err, 'Could not add the activity.'),
    });
  }

  protected deleteVisit(e: Encounter): void {
    const count = this.countByVisit().get(e.id) ?? 0;
    this.api.deleteEncounter(e.id, e.version).subscribe({
      next: () => {
        this.snack.open(
          count ? `Deleted ${e.name} and its ${count} planned activities` : `Deleted ${e.name}`,
          undefined,
          { duration: 3000 },
        );
        this.load();
      },
      error: (err) => this.fail(err, 'Could not delete the visit.'),
    });
  }

  protected deleteActivity(a: Activity): void {
    this.api.deleteActivity(a.id, a.version).subscribe({
      next: () => {
        this.snack.open(`Deleted ${a.name}`, undefined, { duration: 3000 });
        this.load();
      },
      error: (err) => this.fail(err, 'Could not delete the activity.'),
    });
  }

  private fail(err: unknown, fallback: string): void {
    this.busy.set(false);
    const conflict = err instanceof HttpErrorResponse && err.status === 409;
    this.snack.open(
      conflict
        ? 'Someone else changed this first. Showing the latest schedule.'
        : apiErrorMessage(err, fallback),
      'OK',
      { duration: 4000 },
    );
    if (conflict) this.load();
  }
}
