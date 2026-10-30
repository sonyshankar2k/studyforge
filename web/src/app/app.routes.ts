import { Routes } from '@angular/router';

import { authGuard, guestGuard } from './core/auth';

export const routes: Routes = [
  {
    path: 'login',
    title: 'Sign in · StudyForge',
    canActivate: [guestGuard],
    loadComponent: () => import('./auth/login').then((m) => m.Login),
  },
  {
    path: '',
    canActivate: [authGuard],
    children: [
      {
        path: '',
        title: 'Studies · StudyForge',
        loadComponent: () => import('./studies/study-list').then((m) => m.StudyList),
      },
      {
        path: 'studies/:id',
        title: 'Study · StudyForge',
        loadComponent: () => import('./studies/study-detail').then((m) => m.StudyDetailPage),
      },
    ],
  },
  { path: '**', redirectTo: '' },
];
