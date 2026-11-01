// API contracts. These mirror the Pydantic schemas in api/app/schemas.py.
// (Week 3 idea: generate them from /openapi.json with openapi-typescript.)

export type EntityType =
  'study' | 'arm' | 'objective' | 'criterion' | 'encounter' | 'activity' | 'schedule';

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
  entity_type: EntityType;
  entity_id: number;
  action: 'create' | 'update' | 'delete' | 'reorder';
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
  entity_type: EntityType;
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

// ---------- Protocol digitization (Week 2) ----------
export type JobStatus = 'queued' | 'running' | 'succeeded' | 'failed' | 'cancelled';

export interface ExtractedArm {
  name: string;
  arm_type: ArmType;
  dose: string | null;
  planned_size: number | null;
  description: string | null;
}

export interface ExtractedObjective {
  level: ObjectiveLevel;
  description: string;
  endpoint: string;
}

export interface ExtractionResult {
  arms: ExtractedArm[];
  objectives: ExtractedObjective[];
  notes: string | null;
}

export interface DigitizationJob {
  id: number;
  study_id: number;
  created_by: string;
  filename: string;
  size_bytes: number;
  status: JobStatus;
  progress: number;
  stage: string;
  attempts: number;
  extractor: string | null;
  error: string | null;
  result: ExtractionResult | null;
  created_at: string;
  updated_at: string;
  finished_at: string | null;
  applied_at: string | null;
}

/** Pushed over the WebSocket whenever a job's status or progress changes. */
export interface JobEvent {
  type: 'job';
  job: DigitizationJob;
}

export type StudyEvent = ChangeEvent | JobEvent | { type: 'resync' };

// ---------- Study design (Week 3) ----------
export type CriterionCategory = 'inclusion' | 'exclusion';

export interface Criterion {
  id: number;
  study_id: number;
  category: CriterionCategory;
  ordinal: number;
  /** I1, I2... for inclusion; E1, E2... for exclusion. */
  identifier: string;
  text: string;
  version: number;
}

export interface Encounter {
  id: number;
  study_id: number;
  name: string;
  /** Study day; Day 1 = first dose, so screening is negative. */
  day: number;
  window_before: number;
  window_after: number;
  version: number;
}

export type EncounterInput = Pick<Encounter, 'name' | 'day' | 'window_before' | 'window_after'>;

export interface Activity {
  id: number;
  study_id: number;
  name: string;
  ordinal: number;
  version: number;
}

export interface ScheduleCell {
  encounter_id: number;
  activity_id: number;
}

export interface Schedule {
  encounters: Encounter[];
  activities: Activity[];
  cells: ScheduleCell[];
}
