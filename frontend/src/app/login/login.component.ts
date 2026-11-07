import { HttpErrorResponse } from '@angular/common/http';
import { Component, inject, OnInit, signal } from '@angular/core';
import { ReactiveFormsModule, FormBuilder, Validators } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { AuthService } from '../auth.service';

@Component({
  imports: [ReactiveFormsModule, RouterLink],
  selector: 'app-login',
  templateUrl: './login.component.html',
})
export class LoginComponent implements OnInit {
  private readonly formBuilder = inject(FormBuilder);
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);

  readonly form = this.formBuilder.nonNullable.group({
    username: ['', Validators.required],
    password: ['', Validators.required],
  });
  readonly loading = signal(false);
  readonly error = signal<string | null>(null);
  readonly returnMessage = signal(false);

  ngOnInit(): void {
    this.returnMessage.set(this.route.snapshot.queryParamMap.has('returnUrl'));
  }

  submit(): void {
    if (this.form.invalid || this.loading()) {
      this.form.markAllAsTouched();
      return;
    }

    this.loading.set(true);
    this.error.set(null);
    this.auth.login(this.form.getRawValue()).subscribe({
      next: () => {
        const returnUrl = this.route.snapshot.queryParamMap.get('returnUrl');
        const destination =
          returnUrl === '/preferencias' || returnUrl === '/noticias'
            ? returnUrl
            : '/noticias';
        void this.router.navigateByUrl(destination);
      },
      error: (error: HttpErrorResponse) => {
        this.loading.set(false);
        this.error.set(this.errorMessage(error));
      },
      complete: () => this.loading.set(false),
    });
  }

  private errorMessage(error: HttpErrorResponse): string {
    if (error.status === 401) {
      return 'Nombre de usuario o contraseña incorrectos.';
    }
    if (error.status === 0) {
      return 'No se pudo conectar con Django. Comprueba que el servidor esté iniciado.';
    }
    return 'No se pudo iniciar sesión. Inténtalo de nuevo.';
  }
}
