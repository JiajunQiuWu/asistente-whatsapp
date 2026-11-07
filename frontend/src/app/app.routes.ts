import { Routes } from '@angular/router';
import { authGuard } from './auth.guard';

export const routes: Routes = [
  { path: '', pathMatch: 'full', redirectTo: 'noticias' },
  {
    path: 'login',
    loadComponent: () =>
      import('./login/login.component').then((module) => module.LoginComponent),
  },
  {
    path: 'registro',
    loadComponent: () =>
      import('./register/register.component').then(
        (module) => module.RegisterComponent,
      ),
  },
  {
    path: 'verificar-email',
    loadComponent: () =>
      import('./verify-email/verify-email.component').then(
        (module) => module.VerifyEmailComponent,
      ),
  },
  {
    path: 'preferencias',
    canActivate: [authGuard],
    loadComponent: () =>
      import('./preferences/preferences.component').then(
        (module) => module.PreferencesComponent,
      ),
  },
  {
    path: 'noticias',
    canActivate: [authGuard],
    loadComponent: () =>
      import('./news/news.component').then((module) => module.NewsComponent),
  },
  {
    path: 'boletin',
    canActivate: [authGuard],
    loadComponent: () =>
      import('./newsletter/newsletter.component').then(
        (module) => module.NewsletterComponent,
      ),
  },
  {
    path: 'historial',
    canActivate: [authGuard],
    loadComponent: () =>
      import('./history/history.component').then(
        (module) => module.HistoryComponent,
      ),
  },
  { path: '**', redirectTo: 'noticias' },
];
