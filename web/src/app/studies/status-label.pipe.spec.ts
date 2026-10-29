import { StatusLabelPipe } from './status-label.pipe';

describe('StatusLabelPipe', () => {
  const pipe = new StatusLabelPipe();

  it('turns API values into readable labels', () => {
    expect(pipe.transform('in_review')).toBe('In review');
    expect(pipe.transform('active_comparator')).toBe('Active comparator');
  });

  it('returns unknown values unchanged', () => {
    expect(pipe.transform('something_new')).toBe('something_new');
  });

  it('returns an empty string for null or undefined', () => {
    expect(pipe.transform(null)).toBe('');
    expect(pipe.transform(undefined)).toBe('');
  });
});
