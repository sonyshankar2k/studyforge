import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { Criterion, CriterionCategory } from '../core/models';
import { EligibilityPanel } from './eligibility-panel';

function criterion(
  id: number,
  category: CriterionCategory,
  ordinal: number,
  text: string,
): Criterion {
  const identifier = `${category === 'inclusion' ? 'I' : 'E'}${ordinal}`;
  return { id, study_id: 7, category, ordinal, identifier, text, version: 1 };
}

const LIST = [
  criterion(1, 'inclusion', 1, 'Adults aged 18 to 65'),
  criterion(2, 'inclusion', 2, 'Diagnosed asthma'),
  criterion(3, 'exclusion', 1, 'Current smoker'),
];

function setup() {
  TestBed.configureTestingModule({
    imports: [EligibilityPanel],
    providers: [provideHttpClient(), provideHttpClientTesting()],
  });
  const fixture = TestBed.createComponent(EligibilityPanel);
  fixture.componentRef.setInput('studyId', 7);
  fixture.detectChanges();
  const httpMock = TestBed.inject(HttpTestingController);
  httpMock.expectOne('/api/studies/7/criteria').flush(LIST);
  fixture.detectChanges();
  const panel = fixture.componentInstance as unknown as {
    criteria: () => Criterion[];
    move: (category: CriterionCategory, index: number, delta: -1 | 1) => void;
  };
  const summary = () => panel.criteria().map((c) => `${c.identifier} ${c.text}`);
  return { fixture, panel, httpMock, summary };
}

describe('EligibilityPanel', () => {
  it('lists inclusion and exclusion criteria with their numbers', () => {
    const { fixture } = setup();
    const ids = [...fixture.nativeElement.querySelectorAll('.identifier')].map((el: Element) =>
      el.textContent?.trim(),
    );
    expect(ids).toEqual(['I1', 'I2', 'E1']);
  });

  it('moves a criterion and renumbers immediately, then saves the full order', () => {
    const { panel, httpMock, summary } = setup();

    panel.move('inclusion', 1, -1); // move I2 up
    expect(summary()).toEqual([
      'I1 Diagnosed asthma',
      'I2 Adults aged 18 to 65',
      'E1 Current smoker',
    ]);

    const req = httpMock.expectOne('/api/studies/7/criteria/order');
    expect(req.request.body).toEqual({ category: 'inclusion', ids: [2, 1] });
    req.flush([
      criterion(2, 'inclusion', 1, 'Diagnosed asthma'),
      criterion(1, 'inclusion', 2, 'Adults aged 18 to 65'),
      LIST[2],
    ]);
  });

  it('rolls back and reloads when someone else changed the list (409)', () => {
    const { panel, httpMock, summary } = setup();

    panel.move('inclusion', 0, 1);
    httpMock
      .expectOne('/api/studies/7/criteria/order')
      .flush({ detail: 'changed' }, { status: 409, statusText: 'Conflict' });

    expect(summary()).toEqual([
      'I1 Adults aged 18 to 65',
      'I2 Diagnosed asthma',
      'E1 Current smoker',
    ]);
    httpMock.expectOne('/api/studies/7/criteria'); // fetches the latest list
  });

  it('does nothing when moving past either end', () => {
    const { panel, httpMock } = setup();
    panel.move('inclusion', 0, -1);
    panel.move('exclusion', 0, 1);
    httpMock.expectNone('/api/studies/7/criteria/order');
  });
});
