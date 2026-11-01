import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { Encounter, Schedule } from '../core/models';
import { SchedulePanel, visitTiming } from './schedule-panel';

function visit(overrides: Partial<Encounter> = {}): Encounter {
  return {
    id: 1,
    study_id: 7,
    name: 'Day 1',
    day: 1,
    window_before: 0,
    window_after: 0,
    version: 1,
    ...overrides,
  };
}

const SCHEDULE: Schedule = {
  encounters: [visit({ id: 10, name: 'Screening', day: -14 }), visit({ id: 11 })],
  activities: [{ id: 20, study_id: 7, name: 'Vitals', ordinal: 1, version: 1 }],
  cells: [{ encounter_id: 10, activity_id: 20 }],
};

function setup() {
  TestBed.configureTestingModule({
    imports: [SchedulePanel],
    providers: [provideHttpClient(), provideHttpClientTesting()],
  });
  const fixture = TestBed.createComponent(SchedulePanel);
  fixture.componentRef.setInput('studyId', 7);
  fixture.detectChanges();
  const httpMock = TestBed.inject(HttpTestingController);
  httpMock.expectOne('/api/studies/7/schedule').flush(SCHEDULE);
  fixture.detectChanges();
  const panel = fixture.componentInstance as unknown as {
    schedule: () => Schedule;
    toggle: (e: Encounter, a: Schedule['activities'][number]) => void;
    isPlanned: (e: Encounter, a: Schedule['activities'][number]) => boolean;
    isPending: (e: Encounter, a: Schedule['activities'][number]) => boolean;
  };
  return { fixture, panel, httpMock };
}

describe('visitTiming', () => {
  it('shows the study day and a symmetric window as ±', () => {
    expect(visitTiming(visit({ day: 29, window_before: 3, window_after: 3 }))).toBe('Day 29 (±3)');
  });

  it('shows an asymmetric window with both sides', () => {
    expect(visitTiming(visit({ day: 1, window_before: 0, window_after: 2 }))).toBe('Day 1 (-0/+2)');
  });

  it('shows no window when there is none', () => {
    expect(visitTiming(visit({ day: -14 }))).toBe('Day -14');
  });
});

describe('SchedulePanel', () => {
  it('renders an accessible checkbox for every cell', () => {
    const { fixture } = setup();
    const boxes = fixture.nativeElement.querySelectorAll('td input[type=checkbox]');
    expect(boxes.length).toBe(2);
    expect(boxes[0].getAttribute('aria-label')).toBe('Vitals at Screening');
    expect(boxes[0].checked).toBe(true);
    expect(boxes[1].checked).toBe(false);
  });

  it('ticks a cell at once and sends the wanted state, not a toggle', () => {
    const { panel, httpMock } = setup();
    const [, day1] = SCHEDULE.encounters;
    const vitals = SCHEDULE.activities[0];

    panel.toggle(day1, vitals);
    expect(panel.isPlanned(day1, vitals)).toBe(true); // optimistic
    expect(panel.isPending(day1, vitals)).toBe(true);

    const req = httpMock.expectOne('/api/studies/7/schedule/cells');
    expect(req.request.method).toBe('PUT');
    expect(req.request.body).toEqual({ encounter_id: 11, activity_id: 20, planned: true });
    req.flush({ encounter_id: 11, activity_id: 20, planned: true, changed: true });
    expect(panel.isPending(day1, vitals)).toBe(false);
  });

  it('rolls the cell back if the save fails', () => {
    const { panel, httpMock } = setup();
    const [screening] = SCHEDULE.encounters;
    const vitals = SCHEDULE.activities[0];

    panel.toggle(screening, vitals); // untick
    expect(panel.isPlanned(screening, vitals)).toBe(false);
    httpMock
      .expectOne('/api/studies/7/schedule/cells')
      .flush('boom', { status: 500, statusText: 'Server Error' });
    expect(panel.isPlanned(screening, vitals)).toBe(true);
  });

  it('ignores a second click while the first is still saving', () => {
    const { panel, httpMock } = setup();
    const [, day1] = SCHEDULE.encounters;
    const vitals = SCHEDULE.activities[0];
    panel.toggle(day1, vitals);
    panel.toggle(day1, vitals);
    expect(httpMock.match('/api/studies/7/schedule/cells').length).toBe(1);
  });
});
