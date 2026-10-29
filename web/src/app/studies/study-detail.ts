import { DatePipe, KeyValuePipe } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, computed, effect, inject, input, signal, untracked } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatDialog } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatSelectModule } from '@angular/material/select';
import { MatSnackBar } from '@angular/material/snack-bar';
import { MatTabsModule } from '@angular/material/tabs';
import { MatTooltipModule } from '@angular/material/tooltip';
import { RouterLink } from '@angular/router';
import { Observable, firstValueFrom, forkJoin } from 'rxjs';

import { CurrentUser } from '../core/current-user';
import {
  Arm,
  ArmInput,
  AuditEntry,
  ConflictDetail,
  Objective,
  ObjectiveInput,
  PHASES,
  STATUSES,
  StudyDetail,
  StudyInput,
  StudyPhase,
  StudyStatus,
} from '../core/models';
import { StudiesApi } from '../core/studies-api';
import { StudySocket } from '../core/study-socket';
import { acronymAvailable } from '../core/validators';
import { ArmDialog } from './arm-dialog';
import { ConflictChoice, ConflictData, ConflictDialog } from './conflict-dialog';
import { ObjectiveDialog } from './objective-dialog';
import { StatusLabelPipe } from './status-label.pipe';

const FIELD_LABELS: Record<string, string> = {
  title: 'Title',
  acronym: 'Acronym',
  phase: 'Phase',
  therapeutic_area: 'Therapeutic area',
  status: 'Status',
  name: 'Name',
  arm_type: 'Arm type',
  dose: 'Dose',
  planned_size: 'Planned size',
  description: 'Description',
  level: 'Level',
  endpoint: 'Endpoint',
};

type StudyChanges = Partial<StudyInput & { status: StudyStatus }>;

@Component({
  selector: 'app-study-detail',
  imports: [
    ReactiveFormsModule,
    RouterLink,
    DatePipe,
    KeyValuePipe,
    MatButtonModule,
    MatCardModule,
    MatFormFieldModule,
    MatIconModule,
    MatInputModule,
    MatProgressBarModule,
    MatSelectModule,
    MatTabsModule,
    MatTooltipModule,
    StatusLabelPipe,
  ],
  templateUrl: './study-detail.html',
  styleUrl: './study-detail.scss',
})
export class StudyDetailPage {
  /** Route param, bound automatically by withComponentInputBinding(). */
  readonly id = input.required<string>();

  private readonly api = inject(StudiesApi);
  private readonly dialog = inject(MatDialog);
  private readonly snack = inject(MatSnackBar);
  private readonly user = inject(CurrentUser);
  private readonly fb = inject(FormBuilder).nonNullable;
  protected readonly socket = inject(StudySocket);

  protected readonly studyId = computed(() => Number(this.id()));
  protected readonly study = signal<StudyDetail | null>(null);
  protected readonly audit = signal<AuditEntry[]>([]);
  protected readonly loading = signal(true);
  protected readonly notFound = signal(false);
  protected readonly saving = signal(false);
  /** True when someone else saved the study while this user has unsaved edits. */
  protected readonly staleWhileEditing = signal(false);

  protected readonly phases = PHASES;
  protected readonly statuses = STATUSES;

  /** The study version (and values) the form was last synced with. */
  private formBaseVersion = 0;
  private formBaseValues: StudyChanges = {};

  protected readonly details = this.fb.group({
    title: this.fb.control('', [Validators.required, Validators.minLength(3)]),
    acronym: this.fb.control('', {
      validators: [Validators.maxLength(50)],
      asyncValidators: [acronymAvailable(this.api, () => this.studyId())],
    }),
    phase: this.fb.control<StudyPhase>('Phase 1'),
    therapeutic_area: this.fb.control(''),
    status: this.fb.control<StudyStatus>('draft'),
  });

  constructor() {
    // Load data and open the live connection whenever the route id changes.
    effect((onCleanup) => {
      const id = this.studyId();
      untracked(() => this.reload());
      const sub = this.socket.watch(id).subscribe((event) => {
        if (event.type === 'resync') {
          this.reload(); // we may have missed events while offline
          return;
        }
        if (event.changed_by === this.user.name()) return; // our own save
        this.snack.open(
          `${event.changed_by} ${verb(event.action)} ${event.entity_type === 'study' ? 'study details' : `an ${event.entity_type}`}`,
          'OK',
          { duration: 4000 },
        );
        this.reload();
      });
      onCleanup(() => sub.unsubscribe());
    });
  }

  protected reload(): void {
    forkJoin([this.api.getStudy(this.studyId()), this.api.getAudit(this.studyId())]).subscribe({
      next: ([study, audit]) => {
        this.loading.set(false);
        this.study.set(study);
        this.audit.set(audit);
        this.syncForm(study);
      },
      error: (err: HttpErrorResponse) => {
        this.loading.set(false);
        if (err.status === 404) this.notFound.set(true);
      },
    });
  }

  /** Stale-state handling: never overwrite the user's unsaved edits silently. */
  private syncForm(study: StudyDetail): void {
    if (this.details.dirty && study.version !== this.formBaseVersion) {
      this.staleWhileEditing.set(true);
      return;
    }
    if (!this.details.dirty) this.resetForm(study);
  }

  private resetForm(study: StudyDetail): void {
    this.details.reset({
      title: study.title,
      acronym: study.acronym ?? '',
      phase: study.phase,
      therapeutic_area: study.therapeutic_area ?? '',
      status: study.status,
    });
    this.formBaseVersion = study.version;
    this.formBaseValues = this.formValues();
    this.staleWhileEditing.set(false);
  }

  private formValues(): StudyChanges {
    const v = this.details.getRawValue();
    return {
      title: v.title.trim(),
      acronym: v.acronym.trim() || null,
      phase: v.phase,
      therapeutic_area: v.therapeutic_area.trim() || null,
      status: v.status,
    };
  }

  protected discardEdits(): void {
    const s = this.study();
    if (s) this.resetForm(s);
  }

  // ---------------- Study details ----------------
  protected async saveDetails(): Promise<void> {
    const study = this.study();
    if (!study || this.details.invalid || this.details.pending) return;

    // Send ONLY the fields this user changed. Then two people editing different
    // fields never overwrite each other, and a conflict shows just the real clashes.
    const current = this.formValues();
    const mine = Object.fromEntries(
      Object.entries(current).filter(
        ([k, val]) => val !== this.formBaseValues[k as keyof StudyChanges],
      ),
    ) as StudyChanges;
    if (Object.keys(mine).length === 0) {
      this.details.markAsPristine();
      return;
    }

    this.saving.set(true);
    const saved = await this.saveWithConflictHandling(
      'Study details',
      mine,
      (version) => this.api.updateStudy(study.id, version, mine),
      this.formBaseVersion,
    );
    this.saving.set(false);

    if (saved) {
      this.details.markAsPristine();
      this.snack.open('Study saved', undefined, { duration: 2000 });
    } else {
      this.details.markAsPristine(); // user chose "theirs"
    }
    this.reload();
  }

  // ---------------- Arms ----------------
  protected async addArm(): Promise<void> {
    const input = await this.openDialog<ArmInput>(ArmDialog, null);
    if (!input) return;
    this.api.createArm(this.studyId(), input).subscribe(() => this.reload());
  }

  protected async editArm(arm: Arm): Promise<void> {
    const input = await this.openDialog<ArmInput>(ArmDialog, arm);
    if (!input) return;
    const changes = changedFields(arm, input);
    if (Object.keys(changes).length === 0) return;
    await this.saveWithConflictHandling(
      `Arm: ${arm.name}`,
      changes,
      (version) => this.api.updateArm(arm.id, version, changes),
      arm.version,
    );
    this.reload();
  }

  protected deleteArm(arm: Arm): void {
    this.api.deleteArm(arm.id, arm.version).subscribe({
      next: () => {
        this.reload();
        this.offerUndo(`Arm "${arm.name}" deleted`, () =>
          this.api.createArm(this.studyId(), pickArm(arm)),
        );
      },
      error: (err: HttpErrorResponse) => this.handleDeleteError(err),
    });
  }

  // ---------------- Objectives ----------------
  protected async addObjective(): Promise<void> {
    const input = await this.openDialog<ObjectiveInput>(ObjectiveDialog, null);
    if (!input) return;
    this.api.createObjective(this.studyId(), input).subscribe(() => this.reload());
  }

  protected async editObjective(obj: Objective): Promise<void> {
    const input = await this.openDialog<ObjectiveInput>(ObjectiveDialog, obj);
    if (!input) return;
    const changes = changedFields(obj, input);
    if (Object.keys(changes).length === 0) return;
    await this.saveWithConflictHandling(
      'Objective',
      changes,
      (version) => this.api.updateObjective(obj.id, version, changes),
      obj.version,
    );
    this.reload();
  }

  protected deleteObjective(obj: Objective): void {
    this.api.deleteObjective(obj.id, obj.version).subscribe({
      next: () => {
        this.reload();
        this.offerUndo('Objective deleted', () =>
          this.api.createObjective(this.studyId(), {
            level: obj.level,
            description: obj.description,
            endpoint: obj.endpoint,
          }),
        );
      },
      error: (err: HttpErrorResponse) => this.handleDeleteError(err),
    });
  }

  // ---------------- Shared helpers ----------------

  /**
   * Save with optimistic concurrency.
   * On 409, show "yours vs theirs"; "Keep mine" retries against the latest version.
   * Returns true if the user's version was saved.
   */
  private async saveWithConflictHandling<T extends object>(
    what: string,
    mine: T,
    save: (version: number) => Observable<unknown>,
    version: number,
  ): Promise<boolean> {
    try {
      await firstValueFrom(save(version));
      return true;
    } catch (err) {
      if (!(err instanceof HttpErrorResponse) || err.status !== 409) {
        this.snack.open('Save failed. Please try again.', 'OK', { duration: 4000 });
        return false;
      }
      const conflict = err.error.detail as ConflictDetail;
      const fields = Object.entries(mine)
        .filter(([field, value]) => (conflict.current[field] ?? null) !== (value ?? null))
        .map(([field, value]) => ({
          field,
          label: FIELD_LABELS[field] ?? field,
          mine: value,
          theirs: conflict.current[field],
        }));

      const choice = await this.openDialog<ConflictChoice>(ConflictDialog, {
        what,
        fields,
      } satisfies ConflictData);

      if (choice === 'mine') {
        // Retry once against the version we were just told about.
        return this.saveWithConflictHandling(what, mine, save, conflict.current.version);
      }
      return false;
    }
  }

  /** Safe undo: re-create the deleted item (a new, audited change, not a rollback). */
  private offerUndo(message: string, recreate: () => Observable<unknown>): void {
    this.snack
      .open(message, 'Undo', { duration: 6000 })
      .onAction()
      .subscribe(() => recreate().subscribe(() => this.reload()));
  }

  private handleDeleteError(err: HttpErrorResponse): void {
    const msg =
      err.status === 409
        ? 'Someone changed this item first. Showing the latest version.'
        : 'Delete failed. Please try again.';
    this.snack.open(msg, 'OK', { duration: 4000 });
    this.reload();
  }

  private openDialog<R>(component: unknown, data: unknown): Promise<R | undefined> {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const ref = this.dialog.open(component as any, { data, autoFocus: 'first-tabbable' });
    return firstValueFrom(ref.afterClosed()) as Promise<R | undefined>;
  }

  protected label(field: string): string {
    return FIELD_LABELS[field] ?? field;
  }

  protected formatChange(value: unknown): string {
    if (value && typeof value === 'object' && 'old' in value && 'new' in value) {
      const v = value as { old: unknown; new: unknown };
      return `${show(v.old)} → ${show(v.new)}`;
    }
    return show(value);
  }
}

/** Only the fields the user actually changed (sent as a PATCH). */
function changedFields<T extends object>(original: T, edited: Partial<T>): Partial<T> {
  return Object.fromEntries(
    Object.entries(edited).filter(
      ([k, v]) => (v ?? null) !== ((original as Record<string, unknown>)[k] ?? null),
    ),
  ) as Partial<T>;
}

function pickArm(arm: Arm): ArmInput {
  const { name, arm_type, description, planned_size, dose } = arm;
  return { name, arm_type, description, planned_size, dose };
}

function verb(action: string): string {
  return action === 'create' ? 'added' : action === 'delete' ? 'deleted' : 'updated';
}

function show(value: unknown): string {
  return value === null || value === undefined || value === '' ? '—' : String(value);
}
