import { Pipe, PipeTransform } from '@angular/core';

const LABELS: Record<string, string> = {
  draft: 'Draft',
  in_review: 'In review',
  approved: 'Approved',
  experimental: 'Experimental',
  active_comparator: 'Active comparator',
  placebo: 'Placebo',
  primary: 'Primary',
  secondary: 'Secondary',
  exploratory: 'Exploratory',
};

/** Turns API enum values ("in_review") into readable labels ("In review"). */
@Pipe({ name: 'statusLabel' })
export class StatusLabelPipe implements PipeTransform {
  transform(value: string | null | undefined): string {
    if (!value) return '';
    return LABELS[value] ?? value;
  }
}
