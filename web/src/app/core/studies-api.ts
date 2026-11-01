import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, map } from 'rxjs';

import {
  Arm,
  ArmInput,
  Activity,
  AuditEntry,
  Criterion,
  CriterionCategory,
  DigitizationJob,
  Encounter,
  EncounterInput,
  Objective,
  ObjectiveInput,
  Schedule,
  StudyDetail,
  StudyInput,
  StudyStatus,
  StudySummary,
} from './models';

/** Thin typed wrapper around the REST API. Every update sends `version`. */
@Injectable({ providedIn: 'root' })
export class StudiesApi {
  private readonly http = inject(HttpClient);
  private readonly base = '/api';

  listStudies(): Observable<StudySummary[]> {
    return this.http.get<StudySummary[]>(`${this.base}/studies`);
  }

  getStudy(id: number): Observable<StudyDetail> {
    return this.http.get<StudyDetail>(`${this.base}/studies/${id}`);
  }

  createStudy(body: StudyInput): Observable<StudyDetail> {
    return this.http.post<StudyDetail>(`${this.base}/studies`, body);
  }

  updateStudy(
    id: number,
    version: number,
    changes: Partial<StudyInput & { status: StudyStatus }>,
  ): Observable<StudyDetail> {
    return this.http.patch<StudyDetail>(`${this.base}/studies/${id}`, { ...changes, version });
  }

  isAcronymAvailable(acronym: string, excludeId?: number): Observable<boolean> {
    const params: Record<string, string> = { acronym };
    if (excludeId) params['exclude_id'] = String(excludeId);
    return this.http
      .get<{ available: boolean }>(`${this.base}/studies/acronym-available`, { params })
      .pipe(map((r) => r.available));
  }

  getAudit(studyId: number): Observable<AuditEntry[]> {
    return this.http.get<AuditEntry[]>(`${this.base}/studies/${studyId}/audit`);
  }

  createArm(studyId: number, body: ArmInput): Observable<Arm> {
    return this.http.post<Arm>(`${this.base}/studies/${studyId}/arms`, body);
  }

  updateArm(id: number, version: number, changes: Partial<ArmInput>): Observable<Arm> {
    return this.http.patch<Arm>(`${this.base}/arms/${id}`, { ...changes, version });
  }

  deleteArm(id: number, version: number): Observable<void> {
    return this.http.delete<void>(`${this.base}/arms/${id}`, { params: { version } });
  }

  createObjective(studyId: number, body: ObjectiveInput): Observable<Objective> {
    return this.http.post<Objective>(`${this.base}/studies/${studyId}/objectives`, body);
  }

  updateObjective(
    id: number,
    version: number,
    changes: Partial<ObjectiveInput>,
  ): Observable<Objective> {
    return this.http.patch<Objective>(`${this.base}/objectives/${id}`, { ...changes, version });
  }

  deleteObjective(id: number, version: number): Observable<void> {
    return this.http.delete<void>(`${this.base}/objectives/${id}`, { params: { version } });
  }

  // ---------- Protocol digitization ----------

  /**
   * Upload a protocol and start an AI extraction job.
   * Pass the SAME idempotencyKey when retrying the same upload, so a retry after a
   * network error returns the original job instead of starting (and paying for) a second one.
   */
  digitize(studyId: number, file: File, idempotencyKey: string): Observable<DigitizationJob> {
    const body = new FormData();
    body.append('file', file, file.name);
    return this.http.post<DigitizationJob>(`${this.base}/studies/${studyId}/digitize`, body, {
      headers: { 'Idempotency-Key': idempotencyKey },
    });
  }

  listJobs(studyId: number): Observable<DigitizationJob[]> {
    return this.http.get<DigitizationJob[]>(`${this.base}/studies/${studyId}/jobs`);
  }

  cancelJob(jobId: number): Observable<DigitizationJob> {
    return this.http.post<DigitizationJob>(`${this.base}/jobs/${jobId}/cancel`, {});
  }

  retryJob(jobId: number): Observable<DigitizationJob> {
    return this.http.post<DigitizationJob>(`${this.base}/jobs/${jobId}/retry`, {});
  }

  applyJob(
    jobId: number,
    selection: { arms: number[]; objectives: number[] },
  ): Observable<{ arms_added: number; objectives_added: number }> {
    return this.http.post<{ arms_added: number; objectives_added: number }>(
      `${this.base}/jobs/${jobId}/apply`,
      selection,
    );
  }

  // ---------- Eligibility criteria ----------
  listCriteria(studyId: number): Observable<Criterion[]> {
    return this.http.get<Criterion[]>(`${this.base}/studies/${studyId}/criteria`);
  }

  createCriterion(
    studyId: number,
    category: CriterionCategory,
    text: string,
  ): Observable<Criterion> {
    return this.http.post<Criterion>(`${this.base}/studies/${studyId}/criteria`, {
      category,
      text,
    });
  }

  updateCriterion(id: number, version: number, text: string): Observable<Criterion> {
    return this.http.patch<Criterion>(`${this.base}/criteria/${id}`, { version, text });
  }

  deleteCriterion(id: number, version: number): Observable<void> {
    return this.http.delete<void>(`${this.base}/criteria/${id}`, { params: { version } });
  }

  /** Send the complete new order for one category; 409 if the list changed meanwhile. */
  reorderCriteria(
    studyId: number,
    category: CriterionCategory,
    ids: number[],
  ): Observable<Criterion[]> {
    return this.http.put<Criterion[]>(`${this.base}/studies/${studyId}/criteria/order`, {
      category,
      ids,
    });
  }

  // ---------- Schedule of Activities ----------
  getSchedule(studyId: number): Observable<Schedule> {
    return this.http.get<Schedule>(`${this.base}/studies/${studyId}/schedule`);
  }

  createEncounter(studyId: number, body: EncounterInput): Observable<Encounter> {
    return this.http.post<Encounter>(`${this.base}/studies/${studyId}/encounters`, body);
  }

  deleteEncounter(id: number, version: number): Observable<void> {
    return this.http.delete<void>(`${this.base}/encounters/${id}`, { params: { version } });
  }

  createActivity(studyId: number, name: string): Observable<Activity> {
    return this.http.post<Activity>(`${this.base}/studies/${studyId}/activities`, { name });
  }

  deleteActivity(id: number, version: number): Observable<void> {
    return this.http.delete<void>(`${this.base}/activities/${id}`, { params: { version } });
  }

  /** Idempotent: says the state you want, not "toggle", so repeats are harmless. */
  setCell(
    studyId: number,
    encounterId: number,
    activityId: number,
    planned: boolean,
  ): Observable<{ planned: boolean; changed: boolean }> {
    return this.http.put<{ planned: boolean; changed: boolean }>(
      `${this.base}/studies/${studyId}/schedule/cells`,
      { encounter_id: encounterId, activity_id: activityId, planned },
    );
  }

  /** The design as USDM-shaped JSON. */
  exportUsdm(studyId: number): Observable<unknown> {
    return this.http.get<unknown>(`${this.base}/studies/${studyId}/usdm`);
  }
}
