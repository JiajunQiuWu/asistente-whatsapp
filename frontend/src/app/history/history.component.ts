import { HttpErrorResponse } from '@angular/common/http';
import { Component, inject, OnInit, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { NewsletterHistoryResponse } from '../api.models';
import { AccountService } from '../account.service';

@Component({
  imports: [RouterLink],
  selector: 'app-history',
  templateUrl: './history.component.html',
})
export class HistoryComponent implements OnInit {
  private readonly accountService = inject(AccountService);

  readonly history = signal<NewsletterHistoryResponse | null>(null);
  readonly loading = signal(true);
  readonly error = signal<string | null>(null);
  readonly loginRequired = signal(false);

  ngOnInit(): void {
    this.accountService.getNewsletterHistory().subscribe({
      next: (history) => {
        this.history.set(history);
        this.loading.set(false);
      },
      error: (error: HttpErrorResponse) => {
        this.error.set(
          error.status === 401
            ? 'Tu sesión ya no está activa. Inicia sesión para consultar el historial.'
            : 'No se pudo cargar el historial. Inténtalo de nuevo.',
        );
        this.loginRequired.set(error.status === 401);
        this.loading.set(false);
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
}
