import { Component, inject } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MAT_DIALOG_DATA, MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';

import { OBJECTIVE_LEVELS, Objective, ObjectiveInput, ObjectiveLevel } from '../core/models';
import { StatusLabelPipe } from './status-label.pipe';

@Component({
  selector: 'app-objective-dialog',
  imports: [
    ReactiveFormsModule,
    MatButtonModule,
    MatDialogModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    StatusLabelPipe,
  ],
  template: `
    <h2 mat-dialog-title>{{ data ? 'Edit objective' : 'Add objective' }}</h2>
    <mat-dialog-content>
      <form [formGroup]="form" id="objective-form" (ngSubmit)="save()" class="dialog-form">
        <mat-form-field class="full">
          <mat-label>Level</mat-label>
          <mat-select formControlName="level">
            @for (l of levels; track l) {
              <mat-option [value]="l">{{ l | statusLabel }}</mat-option>
            }
          </mat-select>
        </mat-form-field>

        <mat-form-field class="full">
          <mat-label>Objective</mat-label>
          <textarea
            matInput
            rows="2"
            formControlName="description"
            placeholder="e.g. Evaluate the efficacy of the drug compared with placebo"
          ></textarea>
          <mat-error>Objective is required</mat-error>
        </mat-form-field>

        <mat-form-field class="full">
          <mat-label>Endpoint</mat-label>
          <textarea
            matInput
            rows="2"
            formControlName="endpoint"
            placeholder="e.g. Change from baseline in FEV1 at Week 12"
          ></textarea>
          <mat-error>Endpoint is required</mat-error>
        </mat-form-field>
      </form>
    </mat-dialog-content>
    <mat-dialog-actions align="end">
      <button mat-button mat-dialog-close type="button">Cancel</button>
      <button mat-flat-button type="submit" form="objective-form" [disabled]="form.invalid">
        Save
      </button>
    </mat-dialog-actions>
  `,
  styleUrl: './dialog-form.scss',
})
export class ObjectiveDialog {
  protected readonly data = inject<Objective | null>(MAT_DIALOG_DATA);
  private readonly ref = inject(MatDialogRef<ObjectiveDialog, ObjectiveInput>);
  private readonly fb = inject(FormBuilder).nonNullable;
  protected readonly levels = OBJECTIVE_LEVELS;

  protected readonly form = this.fb.group({
    level: this.fb.control<ObjectiveLevel>(this.data?.level ?? 'primary'),
    description: this.fb.control(this.data?.description ?? '', Validators.required),
    endpoint: this.fb.control(this.data?.endpoint ?? '', Validators.required),
  });

  protected save(): void {
    if (this.form.invalid) return;
    const v = this.form.getRawValue();
    this.ref.close({ ...v, description: v.description.trim(), endpoint: v.endpoint.trim() });
  }
}
