import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { DigitizationJob } from '../core/models';
import { DigitizePanel, armProblem, defaultSelection } from './digitize-panel';

function makeJob(overrides: Partial<DigitizationJob> = {}): DigitizationJob {
  return {
    id: 1,
    study_id: 7,
    created_by: 'alice@studyforge.dev',
    filename: 'protocol.pdf',
    size_bytes: 2048,
    status: 'running',
    progress: 25,
    stage: 'Reading the document',
    attempts: 1,
    extractor: null,
    error: null,
    result: null,
    created_at: '2026-10-30T10:00:00Z',
    updated_at: '2026-10-30T10:00:05Z',
    finished_at: null,
    applied_at: null,
    ...overrides,
  };
}

function setup() {
  TestBed.configureTestingModule({
    imports: [DigitizePanel],
    providers: [provideHttpClient(), provideHttpClientTesting()],
  });
  const fixture = TestBed.createComponent(DigitizePanel);
  fixture.componentRef.setInput('studyId', 7);
  fixture.detectChanges();
  const httpMock = TestBed.inject(HttpTestingController);
  httpMock.expectOne('/api/studies/7/jobs').flush([]);
  // Reach protected members on purpose: these tests check behaviour, not markup.
  const panel = fixture.componentInstance as unknown as {
    jobs: () => DigitizationJob[];
    file: () => File | null;
    uploadError: () => string | null;
    onFileInput: (e: Event) => void;
    upload: () => void;
  };
  return { fixture, panel, httpMock };
}

function chooseFile(panel: { onFileInput: (e: Event) => void }, file: File) {
  panel.onFileInput({ target: { files: [file], value: '' } } as unknown as Event);
}

describe('defaultSelection', () => {
  it('pre-selects everything except arms that cannot be added', () => {
    const job = makeJob({
      status: 'succeeded',
      result: {
        arms: [
          {
            name: 'Drug 10 mg',
            arm_type: 'experimental',
            dose: '10 mg',
            planned_size: 50,
            description: null,
          },
          {
            name: 'Drug, dose unknown',
            arm_type: 'experimental',
            dose: null,
            planned_size: null,
            description: null,
          },
          { name: 'Placebo', arm_type: 'placebo', dose: null, planned_size: 50, description: null },
        ],
        objectives: [{ level: 'primary', description: 'Efficacy', endpoint: 'FEV1' }],
        notes: null,
      },
    });
    expect(defaultSelection(job)).toEqual({ arms: [0, 2], objectives: [0] });
  });

  it('explains why an experimental arm without a dose is blocked', () => {
    const arm = {
      name: 'X',
      arm_type: 'experimental' as const,
      dose: null,
      planned_size: null,
      description: null,
    };
    expect(armProblem(arm)).toContain('need a dose');
  });
});

describe('DigitizePanel', () => {
  it('rejects files that are not PDF or text before uploading', () => {
    const { panel } = setup();
    chooseFile(panel, new File(['x'], 'scan.png', { type: 'image/png' }));
    expect(panel.file()).toBeNull();
    expect(panel.uploadError()).toBe('Choose a PDF or a .txt file.');
  });

  it('retries a failed upload with the same idempotency key', () => {
    const { panel, httpMock } = setup();
    chooseFile(panel, new File(['%PDF-1.4'], 'protocol.pdf', { type: 'application/pdf' }));

    panel.upload();
    const first = httpMock.expectOne('/api/studies/7/digitize');
    const key = first.request.headers.get('Idempotency-Key');
    first.flush('gateway timeout', { status: 504, statusText: 'Gateway Timeout' });
    expect(panel.uploadError()).toContain('will not create a duplicate');
    expect(panel.file()).not.toBeNull(); // still there, ready to retry

    panel.upload();
    const second = httpMock.expectOne('/api/studies/7/digitize');
    expect(second.request.headers.get('Idempotency-Key')).toBe(key);
    second.flush(makeJob({ status: 'queued', progress: 0 }));
    expect(panel.jobs().length).toBe(1);
  });

  it('uses a new idempotency key for a newly chosen file', () => {
    const { panel, httpMock } = setup();
    chooseFile(panel, new File(['a'], 'one.pdf'));
    panel.upload();
    const first = httpMock.expectOne('/api/studies/7/digitize');
    first.flush(makeJob({ id: 1 }));

    chooseFile(panel, new File(['b'], 'two.pdf'));
    panel.upload();
    const second = httpMock.expectOne('/api/studies/7/digitize');
    expect(second.request.headers.get('Idempotency-Key')).not.toBe(
      first.request.headers.get('Idempotency-Key'),
    );
    second.flush(makeJob({ id: 2 }));
  });

  it('applies live updates but ignores stale, out-of-order ones', () => {
    const { fixture, panel } = setup();
    const newer = makeJob({ progress: 90, updated_at: '2026-10-30T10:00:09Z' });
    const older = makeJob({ progress: 25, updated_at: '2026-10-30T10:00:05Z' });

    fixture.componentRef.setInput('jobUpdate', newer);
    fixture.detectChanges();
    fixture.componentRef.setInput('jobUpdate', older);
    fixture.detectChanges();

    expect(panel.jobs()[0].progress).toBe(90);
  });

  it('pre-selects items for finished jobs loaded from the list, not only live ones', () => {
    TestBed.configureTestingModule({
      imports: [DigitizePanel],
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    const fixture = TestBed.createComponent(DigitizePanel);
    fixture.componentRef.setInput('studyId', 7);
    fixture.detectChanges();
    const finished = makeJob({
      status: 'succeeded',
      result: {
        arms: [
          { name: 'Placebo', arm_type: 'placebo', dose: null, planned_size: 10, description: null },
        ],
        objectives: [{ level: 'primary', description: 'Efficacy', endpoint: 'FEV1' }],
        notes: null,
      },
    });
    TestBed.inject(HttpTestingController).expectOne('/api/studies/7/jobs').flush([finished]);
    const panel = fixture.componentInstance as unknown as { selectedCount: (id: number) => number };
    expect(panel.selectedCount(1)).toBe(2);
  });

  it('ignores updates for other studies', () => {
    const { fixture, panel } = setup();
    fixture.componentRef.setInput('jobUpdate', makeJob({ study_id: 99 }));
    fixture.detectChanges();
    expect(panel.jobs().length).toBe(0);
  });
});
