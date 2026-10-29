import { Component, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatSelectModule } from '@angular/material/select';
import { MatToolbarModule } from '@angular/material/toolbar';
import { RouterLink, RouterOutlet } from '@angular/router';

import { CurrentUser, DEMO_USERS } from './core/current-user';

@Component({
  selector: 'app-root',
  imports: [
    RouterOutlet,
    RouterLink,
    FormsModule,
    MatToolbarModule,
    MatIconModule,
    MatFormFieldModule,
    MatSelectModule,
  ],
  template: `
    <mat-toolbar class="toolbar">
      <a routerLink="/" class="brand" aria-label="StudyForge home">
        <mat-icon aria-hidden="true">science</mat-icon>
        <span>StudyForge</span>
      </a>
      <span class="spacer"></span>
      <mat-form-field appearance="outline" subscriptSizing="dynamic" class="user-picker">
        <mat-label>Editing as</mat-label>
        <mat-select [(ngModel)]="user.name">
          @for (u of users; track u) {
            <mat-option [value]="u">{{ u }}</mat-option>
          }
        </mat-select>
      </mat-form-field>
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
    .user-picker {
      width: 160px;
      font-size: 14px;
    }
    .page {
      max-width: 1100px;
      margin: 0 auto;
      padding: 24px 16px 64px;
    }
  `,
})
export class App {
  protected readonly user = inject(CurrentUser);
  protected readonly users = DEMO_USERS;
}
