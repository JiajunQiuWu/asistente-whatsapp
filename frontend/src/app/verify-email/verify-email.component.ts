import { HttpErrorResponse } from '@angular/common/http';
import { Component, inject, OnInit, signal } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { EMPTY, switchMap } from 'rxjs';
import { VerificationResponse } from '../api.models';
import { AccountService } from '../account.service';

@Component({
  imports: [RouterLink],
  selector: 'app-verify-email',
  templateUrl: './verify-email.component.html',
})
export class VerifyEmailComponent implements OnInit {
  private readonly route = inject(ActivatedRoute);
  private readonly accountService = inject(AccountService);

  readonly state = signal<VerificationResponse['state'] | 'loading' | 'missing'>(
    'loading',
  );
  readonly email = signal<string | null>(null);
  readonly message = signal<string | null>(null);
  readonly loading = signal(false);
  private token = '';

  ngOnInit(): void {
    this.route.queryParamMap
      .pipe(
        switchMap((params) => {
          this.token = params.get('token') ?? '';
          if (!this.token) {
            this.state.set('missing');
            this.message.set(
              'Abre el enlace de verificación que recibiste por correo.',
            );
            return EMPTY;
          }
          return this.accountService.getVerification(this.token);
        }),
      )
      .subscribe({
        next: (response) => this.applyResponse(response),
        error: (error: HttpErrorResponse) => this.handleError(error),
      });
  }

  confirm(): void {
    if (!this.token || this.loading() || this.state() !== 'confirm') {
      return;
    }
    this.loading.set(true);
    this.message.set(null);
    this.accountService.confirmVerification(this.token).subscribe({
      next: (response) => this.applyResponse(response),
      error: (error: HttpErrorResponse) => this.handleError(error),
      complete: () => this.loading.set(false),
    });
  }

  private applyResponse(response: VerificationResponse): void {
    this.state.set(response.state);
    this.email.set(response.email);
    this.message.set(response.message);
    this.loading.set(false);
  }

  private handleError(error: HttpErrorResponse): void {
    this.loading.set(false);
    if (error.status === 400) {
      const body = error.error as VerificationResponse;
      this.state.set('invalid');
      this.message.set(
        body?.message ??
          'El enlace ha caducado, no es válido o ya no corresponde a la dirección actual.',
      );
      return;
    }
    this.state.set('invalid');
    this.message.set(
      error.status === 0
        ? 'No se pudo conectar con Django. Comprueba que el servidor esté iniciado.'
        : 'No se pudo comprobar el enlace de verificación.',
    );
  }
}
