import { Component, inject, OnInit, signal } from '@angular/core';
import { Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { AuthService } from './auth.service';

@Component({
  imports: [RouterLink, RouterLinkActive, RouterOutlet],
  selector: 'app-root',
  templateUrl: './app.html',
})
export class App implements OnInit {
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);

  readonly session = this.auth.session;
  readonly sessionError = this.auth.sessionError;
  readonly logoutPending = signal(false);

  ngOnInit(): void {
    this.auth.refreshSession().subscribe({
      error: () =>
        this.auth.setSessionError(
          'No se pudo comprobar la sesión. Comprueba que Django esté iniciado.',
        ),
    });
  }

  logout(): void {
    if (this.logoutPending()) {
      return;
    }
    this.logoutPending.set(true);
    this.auth.logout().subscribe({
      next: () => {
        this.logoutPending.set(false);
        void this.router.navigateByUrl('/login');
      },
      error: () => {
        this.logoutPending.set(false);
        this.auth.setSessionError(
          'No se pudo cerrar la sesión. Comprueba la conexión e inténtalo de nuevo.',
        );
      },
    });
  }
}
