import { Routes } from '@angular/router';
import { authGuard } from './core/auth.guard';
import { permissionGuard } from './core/permission.guard';

export const routes: Routes = [
  { path: 'login', loadComponent: () => import('./features/auth/login.component').then(m => m.LoginComponent) },
  {
    path: '', canActivate: [authGuard],
    loadComponent: () => import('./features/shell/shell.component').then(m => m.ShellComponent),
    children: [
      { path: '', pathMatch: 'full', redirectTo: 'counts' },
      { path: 'counts', canActivate: [permissionGuard], data: { permission: 'count.view' },
        loadComponent: () => import('./features/counts/counts.component').then(m => m.CountsComponent) },
      { path: 'variances', canActivate: [permissionGuard], data: { permission: 'variance.view' },
        loadComponent: () => import('./features/variances/variances.component').then(m => m.VariancesComponent) },
    ],
  },
  { path: '**', redirectTo: '' },
];
