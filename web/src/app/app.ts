import { Component, inject } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatMenuModule } from '@angular/material/menu';
import { MatToolbarModule } from '@angular/material/toolbar';
import { RouterLink, RouterOutlet } from '@angular/router';

import { AuthService } from './core/auth';

@Component({
  selector: 'app-root',
  imports: [
    RouterOutlet,
    RouterLink,
    MatToolbarModule,
    MatIconModule,
    MatButtonModule,
    MatMenuModule,
  ],
  template: `
    <mat-toolbar class="toolbar">
      <a routerLink="/" class="brand" aria-label="StudyForge home">
        <mat-icon aria-hidden="true">science</mat-icon>
        <span>StudyForge</span>
      </a>
      <span class="spacer"></span>
      @if (auth.user(); as user) {
        <button mat-button [matMenuTriggerFor]="userMenu" class="user-button">
          <mat-icon aria-hidden="true">account_circle</mat-icon>
          {{ user.display_name }}
        </button>
        <mat-menu #userMenu="matMenu" xPosition="before">
          <div class="menu-email" aria-hidden="true">{{ user.email }}</div>
          <button mat-menu-item (click)="auth.logout()">
            <mat-icon>logout</mat-icon>
            <span>Sign out</span>
          </button>
        </mat-menu>
      }
    </mat-toolbar>
    <main class="page">
      <router-outlet />
    </main>
  `,
  styles: `
    .toolbar {
      position: sticky;
      top: 0;
      z-index: 10;
      gap: 8px;
    }
    .brand {
      display: flex;
      align-items: center;
      gap: 8px;
      color: inherit;
      text-decoration: none;
      font-weight: 600;
    }
    .spacer {
      flex: 1;
    }
    .menu-email {
      padding: 8px 16px;
      font: var(--mat-sys-body-small);
      color: var(--mat-sys-on-surface-variant);
    }
    .page {
      max-width: 1100px;
      margin: 0 auto;
      padding: 24px 16px 64px;
    }
  `,
})
export class App {
  protected readonly auth = inject(AuthService);
}
