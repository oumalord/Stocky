import { HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { AuthService } from './auth.service';

function cookie(name: string): string {
  return document.cookie.split('; ').find(c => c.startsWith(name + '='))?.split('=')[1] ?? '';
}

/** Sends cookies, the CSRF token on unsafe methods, and the active organisation on every API call. */
export const apiInterceptor: HttpInterceptorFn = (req, next) => {
  if (!req.url.startsWith('/api/')) return next(req);
  const headers: Record<string, string> = {};
  if (!['GET', 'HEAD', 'OPTIONS'].includes(req.method)) headers['X-CSRFToken'] = cookie('csrftoken');
  const org = inject(AuthService).activeOrgId();
  if (org) headers['X-Organisation-Id'] = org;
  return next(req.clone({ withCredentials: true, setHeaders: headers }));
};
