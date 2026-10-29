import { Component, inject } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MAT_DIALOG_DATA, MatDialogModule } from '@angular/material/dialog';
import { MatIconModule } from '@angular/material/icon';

export interface ConflictData {
  what: string; // e.g. "Study details", "Arm: Placebo"
  fields: { field: string; label: string; mine: unknown; theirs: unknown }[];
}

export type ConflictChoice = 'mine' | 'theirs';

/**
 * Shown on HTTP 409: someone else saved first.
 * The user chooses to overwrite with their version or accept the other person's.
 */
@Component({
  selector: 'app-conflict-dialog',
  imports: [MatButtonModule, MatDialogModule, MatIconModule],
  template: `
    <h2 mat-dialog-title class="title">
      <mat-icon aria-hidden="true">merge_type</mat-icon> Someone else changed this
    </h2>
    <mat-dialog-content>
      <p>
        <strong>{{ data.what }}</strong> was saved by another user while you were editing. Choose
        which version to keep.
      </p>
      @if (data.fields.length) {
        <table class="diff">
          <thead>
            <tr>
              <th scope="col">Field</th>
              <th scope="col">Yours</th>
              <th scope="col">Theirs (saved)</th>
            </tr>
          </thead>
          <tbody>
            @for (f of data.fields; track f.field) {
              <tr>
                <th scope="row">{{ f.label }}</th>
                <td class="mine">{{ show(f.mine) }}</td>
                <td class="theirs">{{ show(f.theirs) }}</td>
              </tr>
            }
          </tbody>
        </table>
      } @else {
        <p>No field-level differences; only the version changed.</p>
      }
    </mat-dialog-content>
    <mat-dialog-actions align="end">
      <button mat-button [mat-dialog-close]="'theirs'">Use theirs</button>
      <button mat-flat-button [mat-dialog-close]="'mine'">Keep mine</button>
    </mat-dialog-actions>
  `,
  styles: `
    .title {
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .diff {
      width: 100%;
      border-collapse: collapse;
      font: var(--mat-sys-body-medium);
    }
    .diff th,
    .diff td {
      text-align: left;
      padding: 8px;
      border-bottom: 1px solid var(--mat-sys-outline-variant);
      vertical-align: top;
    }
    .diff thead th {
      font: var(--mat-sys-label-large);
      color: var(--mat-sys-on-surface-variant);
    }
    .mine {
      background: var(--mat-sys-primary-container);
      color: var(--mat-sys-on-primary-container);
    }
    .theirs {
      background: var(--mat-sys-tertiary-container);
      color: var(--mat-sys-on-tertiary-container);
    }
  `,
})
export class ConflictDialog {
  protected readonly data = inject<ConflictData>(MAT_DIALOG_DATA);

  protected show(value: unknown): string {
    return value === null || value === undefined || value === '' ? '—' : String(value);
  }
}
