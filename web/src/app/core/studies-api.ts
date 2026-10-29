import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, map } from 'rxjs';

import {
  Arm,
  ArmInput,
  AuditEntry,
  Objective,
  ObjectiveInput,
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
}
