import {
  CdkDrag,
  CdkDragDrop,
  CdkDragHandle,
  CdkDropList,
  moveItemInArray,
} from '@angular/cdk/drag-drop';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, computed, effect, inject, input, signal, untracked } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatSnackBar } from '@angular/material/snack-bar';
import { MatTooltipModule } from '@angular/material/tooltip';

import { apiErrorMessage } from '../core/api-errors';
import { Criterion, CriterionCategory } from '../core/models';
import { StudiesApi } from '../core/studies-api';

interface Section {
  category: CriterionCategory;
  title: string;
  hint: string;
}

const SECTIONS: Section[] = [
  { category: 'inclusion', title: 'Inclusion criteria', hint: 'Who can take part' },
  { category: 'exclusion', title: 'Exclusion criteria', hint: 'Who cannot take part' },
];

/**
 * Inclusion / exclusion criteria, numbered I1, I2... and E1, E2...
 *
 * Reordering: drag with the handle (Angular CDK drag-drop), or use the move buttons,
 * which also work from the keyboard. The new order shows at once (optimistic) and is
 * saved; if someone else changed the list meanwhile, the server says 409 and we reload.
 */
@Component({
  selector: 'app-eligibility-panel',
  imports: [
    CdkDropList,
    CdkDrag,
    CdkDragHandle,
    ReactiveFormsModule,
    MatButtonModule,
    MatCardModule,
    MatFormFieldModule,
    MatIconModule,
    MatInputModule,
    MatTooltipModule,
  ],
  templateUrl: './eligibility-panel.html',
  styleUrl: './eligibility-panel.scss',
})
export class EligibilityPanel {
  readonly studyId = input.required<number>();
  /** Bumped by the page when someone else changes the study: reload. */
  readonly refresh = input(0);

  private readonly api = inject(StudiesApi);
  private readonly snack = inject(MatSnackBar);
  private readonly fb = inject(FormBuilder).nonNullable;

  protected readonly sections = SECTIONS;
  protected readonly criteria = signal<Criterion[]>([]);
  protected readonly loaded = signal(false);
  protected readonly editingId = signal<number | null>(null);
  protected readonly busy = signal(false);

  protected readonly byCategory = computed(() => ({
    inclusion: this.criteria().filter((c) => c.category === 'inclusion'),
    exclusion: this.criteria().filter((c) => c.category === 'exclusion'),
  }));

  protected readonly addForms = {
    inclusion: this.fb.control('', [
      Validators.required,
      Validators.minLength(3),
      Validators.maxLength(2000),
    ]),
    exclusion: this.fb.control('', [
      Validators.required,
      Validators.minLength(3),
      Validators.maxLength(2000),
    ]),
  };
  protected readonly editText = this.fb.control('', [
    Validators.required,
    Validators.minLength(3),
    Validators.maxLength(2000),
  ]);

  constructor() {
    effect(() => {
      const id = this.studyId();
      this.refresh();
      untracked(() => this.load(id));
    });
  }

  private load(studyId = this.studyId()): void {
    this.api.listCriteria(studyId).subscribe((items) => {
      this.criteria.set(items);
      this.loaded.set(true);
    });
  }

  protected add(category: CriterionCategory): void {
    const control = this.addForms[category];
    if (control.invalid || this.busy()) {
      control.markAsTouched();
      return;
    }
    this.busy.set(true);
    this.api.createCriterion(this.studyId(), category, control.value.trim()).subscribe({
      next: (created) => {
        this.busy.set(false);
        control.reset();
        this.criteria.update((all) => [...all, created]);
      },
      error: (err) => this.fail(err, 'Could not add the criterion.'),
    });
  }

  protected startEdit(item: Criterion): void {
    this.editingId.set(item.id);
    this.editText.setValue(item.text);
  }

  protected saveEdit(item: Criterion): void {
    if (this.editText.invalid || this.busy()) return;
    const text = this.editText.value.trim();
    if (text === item.text) {
      this.editingId.set(null);
      return;
    }
    this.busy.set(true);
    this.api.updateCriterion(item.id, item.version, text).subscribe({
      next: (updated) => {
        this.busy.set(false);
        this.editingId.set(null);
        this.criteria.update((all) => all.map((c) => (c.id === updated.id ? updated : c)));
      },
      error: (err) => this.fail(err, 'Could not save the criterion.'),
    });
  }

  protected remove(item: Criterion): void {
    this.busy.set(true);
    this.api.deleteCriterion(item.id, item.version).subscribe({
      next: () => {
        this.busy.set(false);
        this.snack.open(`${item.identifier} deleted; the rest were renumbered`, undefined, {
          duration: 3000,
        });
        this.load();
      },
      error: (err) => this.fail(err, 'Could not delete the criterion.'),
    });
  }

  // ---------------- reordering ----------------
  protected drop(category: CriterionCategory, event: CdkDragDrop<Criterion[]>): void {
    this.reorder(category, event.previousIndex, event.currentIndex);
  }

  protected move(category: CriterionCategory, index: number, delta: -1 | 1): void {
    this.reorder(category, index, index + delta);
  }

  private reorder(category: CriterionCategory, from: number, to: number): void {
    const list = [...this.byCategory()[category]];
    if (from === to || to < 0 || to >= list.length) return;
    const previous = this.criteria();
    moveItemInArray(list, from, to);

    // Optimistic: show the new order and numbers right away.
    const renumbered = list.map((c, i) => ({
      ...c,
      ordinal: i + 1,
      identifier: `${category === 'inclusion' ? 'I' : 'E'}${i + 1}`,
    }));
    this.criteria.set(
      [...previous.filter((c) => c.category !== category), ...renumbered].sort(sortCriteria),
    );

    this.api
      .reorderCriteria(
        this.studyId(),
        category,
        list.map((c) => c.id),
      )
      .subscribe({
        next: (saved) => this.criteria.set(saved),
        error: (err: HttpErrorResponse) => {
          this.criteria.set(previous); // roll back
          if (err.status === 409) {
            this.snack.open('Someone else changed these criteria. Showing the latest list.', 'OK', {
              duration: 4000,
            });
            this.load();
          } else {
            this.snack.open('Could not save the new order.', 'OK', { duration: 4000 });
          }
        },
      });
  }

  private fail(err: unknown, fallback: string): void {
    this.busy.set(false);
    const conflict = err instanceof HttpErrorResponse && err.status === 409;
    this.snack.open(
      conflict
        ? 'Someone else changed this criterion. Showing the latest version.'
        : apiErrorMessage(err, fallback),
      'OK',
      { duration: 4000 },
    );
    if (conflict) {
      this.editingId.set(null);
      this.load();
    }
  }
}

function sortCriteria(a: Criterion, b: Criterion): number {
  if (a.category !== b.category) return a.category === 'inclusion' ? -1 : 1;
  return a.ordinal - b.ordinal;
}
