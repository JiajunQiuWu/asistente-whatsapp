import { HttpErrorResponse } from '@angular/common/http';
import { Component, inject, OnInit, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import {
  ApiErrorResponse,
  NewsletterPreviewResponse,
} from '../api.models';
import { AccountService } from '../account.service';

@Component({
  imports: [RouterLink],
  selector: 'app-newsletter',
  templateUrl: './newsletter.component.html',
})
export class NewsletterComponent implements OnInit {
  private readonly accountService = inject(AccountService);

  readonly preview = signal<NewsletterPreviewResponse | null>(null);
  readonly loading = signal(true);
  readonly error = signal<string | null>(null);
  readonly loginRequired = signal(false);
  readonly sending = signal(false);
  readonly sendMessage = signal<string | null>(null);
  readonly sendError = signal<string | null>(null);
  readonly verificationRequired = signal(false);

  ngOnInit(): void {
    this.accountService.getNewsletterPreview().subscribe({
      next: (preview) => {
        this.preview.set(preview);
        this.verificationRequired.set(!preview.email_verified);
        this.loading.set(false);
      },
      error: (error: HttpErrorResponse) => {
        this.error.set(this.errorMessage(error));
        this.loginRequired.set(error.status === 401);
        this.loading.set(false);
      },
    });
  }

  requestSend(): void {
    if (this.sending()) {
      return;
    }
    this.sending.set(true);
    this.sendMessage.set(null);
    this.sendError.set(null);
    this.verificationRequired.set(false);

    this.accountService.sendManualNewsletter().subscribe({
      next: (response) => {
        this.sendMessage.set(response.detail);
        this.sending.set(false);
      },
      error: (error: HttpErrorResponse) => {
        this.sendError.set(this.errorMessage(error));
        this.verificationRequired.set(error.status === 403);
        this.loginRequired.set(error.status === 401);
        this.sending.set(false);
      },
    });
  }

  formatDate(value: string, timezoneName: string): string {
    return new Intl.DateTimeFormat('es-ES', {
      dateStyle: 'short',
      timeStyle: 'short',
      timeZone: timezoneName,
    }).format(new Date(value));
  }

  private errorMessage(error: HttpErrorResponse): string {
    const body = error.error as ApiErrorResponse | null;
    if (typeof body?.detail === 'string') {
      return body.detail;
    }
    if (error.status === 401) {
      return 'Tu sesión ya no está activa. Inicia sesión para continuar.';
    }
    if (error.status === 0) {
      return 'No se pudo conectar con Django. Comprueba que el servidor esté iniciado.';
    }
    return 'No se pudo cargar el boletín. Inténtalo de nuevo.';
  }
}
