import { HttpErrorResponse } from '@angular/common/http';
import { DatePipe } from '@angular/common';
import { Component, inject, OnInit, signal } from '@angular/core';
import {
  FormBuilder,
  FormControl,
  ReactiveFormsModule,
  Validators,
} from '@angular/forms';
import { RouterLink } from '@angular/router';
import {
  ApiErrorResponse,
  PreferencesResponse,
  TopicChoice,
} from '../api.models';
import { AccountService } from '../account.service';

type TopicField = 'newsletter_topics' | 'alert_topics';

@Component({
  imports: [DatePipe, ReactiveFormsModule, RouterLink],
  selector: 'app-preferences',
  templateUrl: './preferences.component.html',
})
export class PreferencesComponent implements OnInit {
  private readonly formBuilder = inject(FormBuilder);
  private readonly accountService = inject(AccountService);

  readonly form = this.formBuilder.nonNullable.group({
    newsletter_topics: new FormControl<string[]>([], { nonNullable: true }),
    newsletter_enabled: new FormControl(false, { nonNullable: true }),
    newsletter_time: new FormControl('09:00', {
      nonNullable: true,
      validators: [Validators.required],
    }),
    timezone_name: new FormControl('Europe/Madrid', {
      nonNullable: true,
      validators: [Validators.required],
    }),
    alerts_enabled: new FormControl(false, { nonNullable: true }),
    alert_topics: new FormControl<string[]>([], { nonNullable: true }),
    daily_alert_limit: new FormControl(3, {
      nonNullable: true,
      validators: [Validators.required, Validators.min(1), Validators.max(10)],
    }),
  });

  readonly data = signal<PreferencesResponse | null>(null);
  readonly topics = signal<TopicChoice[]>([]);
  readonly loading = signal(true);
  readonly saving = signal(false);
  readonly resending = signal(false);
  readonly error = signal<string | null>(null);
  readonly fieldErrors = signal<Record<string, string[]>>({});
  readonly confirmation = signal<string | null>(null);
  readonly sessionExpired = signal(false);

  ngOnInit(): void {
    this.loadPreferences();
  }

  loadPreferences(): void {
    this.loading.set(true);
    this.error.set(null);
    this.accountService.getPreferences().subscribe({
      next: (data) => {
        this.applyData(data);
        this.loading.set(false);
      },
      error: (error: HttpErrorResponse) => this.handleError(error),
    });
  }

  toggleTopic(field: TopicField, topic: string, event: Event): void {
    const target = event.target;
    if (!(target instanceof HTMLInputElement)) {
      return;
    }
    const control = this.form.controls[field];
    const selected = control.value;
    control.setValue(
      target.checked
        ? [...selected, topic]
        : selected.filter((item) => item !== topic),
    );
    control.markAsDirty();
  }

  hasTopic(field: TopicField, topic: string): boolean {
    return this.form.controls[field].value.includes(topic);
  }

  errorsFor(field: string): string[] {
    return this.fieldErrors()[field] ?? [];
  }

  save(): void {
    if (this.form.invalid || this.saving()) {
      this.form.markAllAsTouched();
      return;
    }
    this.saving.set(true);
    this.error.set(null);
    this.confirmation.set(null);
    this.fieldErrors.set({});
    this.accountService.savePreferences(this.form.getRawValue()).subscribe({
      next: (data) => {
        this.applyData(data);
        this.confirmation.set('Tus preferencias se han guardado.');
      },
      error: (error: HttpErrorResponse) => this.handleError(error),
      complete: () => this.saving.set(false),
    });
  }

  resendVerification(): void {
    if (this.resending()) {
      return;
    }
    this.resending.set(true);
    this.error.set(null);
    this.confirmation.set(null);
    this.accountService.resendVerification().subscribe({
      next: (response) => {
        this.confirmation.set(response.message);
        this.loadPreferences();
      },
      error: (error: HttpErrorResponse) => this.handleError(error),
      complete: () => this.resending.set(false),
    });
  }

  private applyData(data: PreferencesResponse): void {
    this.data.set(data);
    this.topics.set(data.topic_choices);
    this.form.setValue(data.preferences);
  }

  private handleError(error: HttpErrorResponse): void {
    this.loading.set(false);
    this.saving.set(false);
    this.resending.set(false);
    if (error.status === 401) {
      this.sessionExpired.set(true);
      this.error.set(
        'Tu sesión ha caducado. Inicia sesión de nuevo para consultar o guardar tus preferencias.',
      );
      return;
    }
    const body = error.error as ApiErrorResponse | null;
    this.fieldErrors.set(body?.field_errors ?? {});
    this.error.set(
      body?.non_field_errors?.join(' ') ??
        body?.detail ??
        (error.status === 0
          ? 'No se pudo conectar con Django. Inténtalo de nuevo.'
          : body?.message ?? 'No se pudo completar la operación. Inténtalo de nuevo.'),
    );
  }
}
