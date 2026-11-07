import { HttpErrorResponse } from '@angular/common/http';
import { Component, inject, signal } from '@angular/core';
import {
  AbstractControl,
  FormBuilder,
  ReactiveFormsModule,
  ValidationErrors,
  Validators,
} from '@angular/forms';
import { RouterLink } from '@angular/router';
import {
  ApiErrorResponse,
  RegistrationPayload,
  RegistrationResponse,
} from '../api.models';
import { AccountService } from '../account.service';

function passwordsMatch(control: AbstractControl): ValidationErrors | null {
  const password = control.get('password1')?.value;
  const confirmation = control.get('password2')?.value;
  return password && confirmation && password !== confirmation
    ? { passwordMismatch: true }
    : null;
}

@Component({
  imports: [ReactiveFormsModule, RouterLink],
  selector: 'app-register',
  templateUrl: './register.component.html',
})
export class RegisterComponent {
  private readonly formBuilder = inject(FormBuilder);
  private readonly accountService = inject(AccountService);

  readonly form = this.formBuilder.nonNullable.group(
    {
      username: ['', Validators.required],
      email: ['', [Validators.required, Validators.email]],
      password1: ['', Validators.required],
      password2: ['', Validators.required],
    },
    { validators: passwordsMatch },
  );
  readonly loading = signal(false);
  readonly result = signal<RegistrationResponse | null>(null);
  readonly error = signal<string | null>(null);
  readonly fieldErrors = signal<Record<string, string[]>>({});

  submit(): void {
    if (this.form.invalid || this.loading()) {
      this.form.markAllAsTouched();
      return;
    }

    this.loading.set(true);
    this.clearErrors();
    const payload: RegistrationPayload = this.form.getRawValue();
    this.accountService.register(payload).subscribe({
      next: (response) => this.result.set(response),
      error: (error: HttpErrorResponse) => this.handleError(error),
      complete: () => this.loading.set(false),
    });
  }

  errorsFor(field: string): string[] {
    return this.fieldErrors()[field] ?? [];
  }

  private handleError(error: HttpErrorResponse): void {
    this.loading.set(false);
    const body = error.error as ApiErrorResponse | null;
    this.fieldErrors.set(body?.field_errors ?? {});
    this.error.set(
      body?.non_field_errors?.join(' ') ??
        body?.detail ??
        (error.status === 0
          ? 'No se pudo conectar con Django. Inténtalo de nuevo.'
          : 'No se pudo crear la cuenta. Revisa los datos e inténtalo de nuevo.'),
    );
  }

  private clearErrors(): void {
    this.error.set(null);
    this.fieldErrors.set({});
  }
}
