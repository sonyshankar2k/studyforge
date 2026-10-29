import { Component, DestroyRef, inject } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MAT_DIALOG_DATA, MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';

import { ARM_TYPES, Arm, ArmInput, ArmType } from '../core/models';

/**
 * Add/edit an arm. Shows a CONDITIONAL validation rule:
 * "dose" becomes required only when the arm type is Experimental.
 * (The API enforces the same rule, so the UI and server never disagree.)
 */
@Component({
  selector: 'app-arm-dialog',
  imports: [
    ReactiveFormsModule,
    MatButtonModule,
    MatDialogModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
  ],
  template: `
    <h2 mat-dialog-title>{{ data ? 'Edit arm' : 'Add arm' }}</h2>
    <mat-dialog-content>
      <form [formGroup]="form" id="arm-form" (ngSubmit)="save()" class="dialog-form">
        <mat-form-field>
          <mat-label>Arm name</mat-label>
          <input matInput formControlName="name" cdkFocusInitial autocomplete="off" />
          <mat-error>Name is required</mat-error>
        </mat-form-field>

        <mat-form-field>
          <mat-label>Arm type</mat-label>
          <mat-select formControlName="arm_type">
            @for (t of armTypes; track t.value) {
              <mat-option [value]="t.value">{{ t.label }}</mat-option>
            }
          </mat-select>
        </mat-form-field>

        <mat-form-field>
          <mat-label>Dose</mat-label>
          <input matInput formControlName="dose" placeholder="e.g. 10 mg once daily" />
          @if (form.controls.arm_type.value === 'experimental') {
            <mat-hint>Required for experimental arms</mat-hint>
          }
          <mat-error>Dose is required for experimental arms</mat-error>
        </mat-form-field>

        <mat-form-field>
          <mat-label>Planned size</mat-label>
          <input matInput type="number" min="1" formControlName="planned_size" />
          <mat-error>Must be at least 1</mat-error>
        </mat-form-field>

        <mat-form-field class="full">
          <mat-label>Description</mat-label>
          <textarea matInput rows="3" formControlName="description"></textarea>
        </mat-form-field>
      </form>
    </mat-dialog-content>
    <mat-dialog-actions align="end">
      <button mat-button mat-dialog-close type="button">Cancel</button>
      <button mat-flat-button type="submit" form="arm-form" [disabled]="form.invalid">Save</button>
    </mat-dialog-actions>
  `,
  styleUrl: './dialog-form.scss',
})
export class ArmDialog {
  protected readonly data = inject<Arm | null>(MAT_DIALOG_DATA);
  private readonly ref = inject(MatDialogRef<ArmDialog, ArmInput>);
  private readonly fb = inject(FormBuilder);
  protected readonly armTypes = ARM_TYPES;

  protected readonly form = this.fb.group({
    name: this.fb.nonNullable.control(this.data?.name ?? '', Validators.required),
    arm_type: this.fb.nonNullable.control<ArmType>(this.data?.arm_type ?? 'experimental'),
    dose: this.fb.control(this.data?.dose ?? null),
    planned_size: this.fb.control<number | null>(
      this.data?.planned_size ?? null,
      Validators.min(1),
    ),
    description: this.fb.control(this.data?.description ?? null),
  });

  constructor() {
    const doseControl = this.form.controls.dose;
    const applyDoseRule = (type: ArmType) => {
      doseControl.setValidators(type === 'experimental' ? Validators.required : null);
      doseControl.updateValueAndValidity();
    };
    applyDoseRule(this.form.controls.arm_type.value);
    this.form.controls.arm_type.valueChanges
      .pipe(takeUntilDestroyed(inject(DestroyRef)))
      .subscribe(applyDoseRule);
  }

  protected save(): void {
    if (this.form.invalid) return;
    const v = this.form.getRawValue();
    this.ref.close({
      name: v.name.trim(),
      arm_type: v.arm_type,
      dose: v.dose?.trim() || null,
      planned_size: v.planned_size || null,
      description: v.description?.trim() || null,
    });
  }
}
