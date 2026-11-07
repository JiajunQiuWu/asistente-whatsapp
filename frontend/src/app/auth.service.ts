import { HttpClient } from '@angular/common/http';
import { inject, Injectable, signal } from '@angular/core';
import { Observable, switchMap, tap } from 'rxjs';
import { LoginCredentials, SessionResponse } from './api.models';

@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly http = inject(HttpClient);

  readonly session = signal<SessionResponse | null>(null);
  readonly sessionError = signal<string | null>(null);

  refreshSession(): Observable<SessionResponse> {
    return this.http.get<SessionResponse>('/api/session/').pipe(
      tap((session) => {
        this.session.set(session);
        this.sessionError.set(null);
      }),
    );
  }

  ensureCsrfCookie(): Observable<{ detail: string }> {
    return this.http.get<{ detail: string }>('/api/csrf/');
  }

  login(credentials: LoginCredentials): Observable<SessionResponse> {
    this.sessionError.set(null);
    return this.ensureCsrfCookie().pipe(
      switchMap(() =>
        this.http.post<SessionResponse>('/api/login/', credentials),
      ),
      tap((session) => this.session.set(session)),
    );
  }

  logout(): Observable<SessionResponse> {
    return this.http
      .post<SessionResponse>('/api/logout/', {})
      .pipe(tap((session) => this.session.set(session)));
  }

  setSessionError(message: string): void {
    this.sessionError.set(message);
  }
}
