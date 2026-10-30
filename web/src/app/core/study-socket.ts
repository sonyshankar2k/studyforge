import { Injectable, inject, signal } from '@angular/core';
import { Observable } from 'rxjs';

import { AuthService } from './auth';
import { ChangeEvent } from './models';

export type SocketStatus = 'connecting' | 'live' | 'reconnecting';

/**
 * Live updates for one study, with automatic reconnect.
 *
 * - Reconnects with exponential backoff (1s, 2s, 4s ... max 15s).
 * - Emits a synthetic `resync` after a reconnect, because events sent while
 *   we were offline are lost: the page must refetch to recover stale state.
 * - Sends the JWT as `?token=` (browsers can't set headers on WebSockets).
 *   If the server rejects it (close code 1008), sign out instead of retrying.
 */
@Injectable({ providedIn: 'root' })
export class StudySocket {
  private readonly auth = inject(AuthService);
  readonly status = signal<SocketStatus>('connecting');

  watch(studyId: number): Observable<ChangeEvent | { type: 'resync' }> {
    return new Observable((subscriber) => {
      let ws: WebSocket | undefined;
      let retry = 0;
      let pingTimer: ReturnType<typeof setInterval> | undefined;
      let retryTimer: ReturnType<typeof setTimeout> | undefined;
      let closedByUs = false;

      const connect = () => {
        const proto = location.protocol === 'https:' ? 'wss' : 'ws';
        const token = encodeURIComponent(this.auth.token() ?? '');
        ws = new WebSocket(`${proto}://${location.host}/ws/studies/${studyId}?token=${token}`);
        this.status.set(retry === 0 ? 'connecting' : 'reconnecting');

        ws.onopen = () => {
          if (retry > 0) subscriber.next({ type: 'resync' });
          retry = 0;
          this.status.set('live');
          pingTimer = setInterval(() => ws?.send('ping'), 25_000);
        };
        ws.onmessage = (msg) => subscriber.next(JSON.parse(msg.data) as ChangeEvent);
        ws.onclose = (event) => {
          clearInterval(pingTimer);
          if (closedByUs) return;
          if (event.code === 1008) {
            this.auth.logout(location.pathname); // token expired or invalid
            return;
          }
          this.status.set('reconnecting');
          const delay = Math.min(15_000, 1000 * 2 ** retry++);
          retryTimer = setTimeout(connect, delay);
        };
      };

      connect();

      return () => {
        closedByUs = true;
        clearInterval(pingTimer);
        clearTimeout(retryTimer);
        ws?.close();
      };
    });
  }
}
