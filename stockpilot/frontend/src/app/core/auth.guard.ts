import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { catchError, map, of } from 'rxjs';
import { AuthService } from './auth.service';

export const authGuard: CanActivateFn = () => {
  const auth = inject(AuthService), router = inject(Router);
  if (auth.me()) return true;
  return auth.load().pipe(map(() => true), catchError(() => of(router.createUrlTree(['/login']))));
};
