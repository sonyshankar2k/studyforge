import { Routes } from '@angular/router';

export const routes: Routes = [
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
  { path: '**', redirectTo: '' },
];
