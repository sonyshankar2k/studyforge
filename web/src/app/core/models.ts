// API contracts. These mirror the Pydantic schemas in api/app/schemas.py.
// (Week 3 idea: generate them from /openapi.json with openapi-typescript.)

export type StudyPhase = 'Phase 1' | 'Phase 2' | 'Phase 3' | 'Phase 4';
export type StudyStatus = 'draft' | 'in_review' | 'approved';
export type ArmType = 'experimental' | 'active_comparator' | 'placebo';
export type ObjectiveLevel = 'primary' | 'secondary' | 'exploratory';

export interface StudySummary {
  id: number;
  title: string;
  acronym: string | null;
  phase: StudyPhase;
  therapeutic_area: string | null;
  status: StudyStatus;
  version: number;
  updated_at: string;
}

export interface Arm {
  id: number;
  study_id: number;
  name: string;
  arm_type: ArmType;
  description: string | null;
  planned_size: number | null;
  dose: string | null;
  version: number;
}

export interface Objective {
  id: number;
  study_id: number;
  level: ObjectiveLevel;
  description: string;
  endpoint: string;
  version: number;
}

export interface StudyDetail extends StudySummary {
  arms: Arm[];
  objectives: Objective[];
}

export interface AuditEntry {
  id: number;
  entity_type: 'study' | 'arm' | 'objective';
  entity_id: number;
  action: 'create' | 'update' | 'delete';
  changes: Record<string, unknown>;
  changed_by: string;
  changed_at: string;
}

/** Body of a 409 response: lets the UI show "yours vs theirs". */
export interface ConflictDetail {
  message: string;
  current: Record<string, unknown> & { id: number; version: number };
}

/** Event pushed over the WebSocket after someone saves. */
export interface ChangeEvent {
  type: 'changed';
  entity_type: 'study' | 'arm' | 'objective';
  entity_id: number;
  action: 'create' | 'update' | 'delete';
  changed_by: string;
}

export type ArmInput = Omit<Arm, 'id' | 'study_id' | 'version'>;
export type ObjectiveInput = Omit<Objective, 'id' | 'study_id' | 'version'>;
export type StudyInput = Pick<StudySummary, 'title' | 'acronym' | 'phase' | 'therapeutic_area'>;

export const PHASES: StudyPhase[] = ['Phase 1', 'Phase 2', 'Phase 3', 'Phase 4'];
export const STATUSES: StudyStatus[] = ['draft', 'in_review', 'approved'];
export const ARM_TYPES: { value: ArmType; label: string }[] = [
  { value: 'experimental', label: 'Experimental' },
  { value: 'active_comparator', label: 'Active comparator' },
  { value: 'placebo', label: 'Placebo' },
];
export const OBJECTIVE_LEVELS: ObjectiveLevel[] = ['primary', 'secondary', 'exploratory'];
