import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { catchError, map, of } from 'rxjs';
import { AuthService } from './auth.service';

export const authGuard: CanActivateFn = (_route, state) => {
  const auth = inject(AuthService);
  const router = inject(Router);

  return auth.refreshSession().pipe(
    map((session) => {
      if (session.authenticated) {
        return true;
      }
      auth.setSessionError(
        'Inicia sesión para acceder a esta página.',
      );
      return router.createUrlTree(['/login'], {
        queryParams: { returnUrl: state.url },
      });
    }),
    catchError(() => {
      auth.setSessionError(
        'No se pudo comprobar la sesión. Comprueba que Django esté iniciado.',
      );
      return of(router.createUrlTree(['/login']));
    }),
  );
};
