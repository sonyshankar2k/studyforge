import { TestBed } from '@angular/core/testing';
import { MAT_DIALOG_DATA, MatDialogRef } from '@angular/material/dialog';

import { ArmDialog } from './arm-dialog';

describe('ArmDialog conditional validation', () => {
  function create() {
    TestBed.configureTestingModule({
      imports: [ArmDialog],
      providers: [
        { provide: MAT_DIALOG_DATA, useValue: null },
        { provide: MatDialogRef, useValue: { close: () => undefined } },
      ],
    });
    const fixture = TestBed.createComponent(ArmDialog);
    // `form` is protected; tests reach it through an index signature on purpose.
    return (fixture.componentInstance as unknown as { form: ArmDialog['form'] }).form;
  }

  it('requires a dose for experimental arms', () => {
    const form = create();
    form.patchValue({ name: 'Drug A', arm_type: 'experimental', dose: null });
    expect(form.controls.dose.hasError('required')).toBe(true);
    expect(form.valid).toBe(false);
  });

  it('does not require a dose for placebo arms', () => {
    const form = create();
    form.patchValue({ name: 'Placebo', arm_type: 'placebo', dose: null });
    expect(form.controls.dose.hasError('required')).toBe(false);
    expect(form.valid).toBe(true);
  });
});
