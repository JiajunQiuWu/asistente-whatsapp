import { HttpClient, HttpParams } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { Observable, switchMap } from 'rxjs';
import {
  Preferences,
  PreferencesResponse,
  NewsletterHistoryResponse,
  NewsletterPreviewResponse,
  NewsletterSendResponse,
  RegistrationPayload,
  RegistrationResponse,
  VerificationResponse,
} from './api.models';
import { AuthService } from './auth.service';

@Injectable({ providedIn: 'root' })
export class AccountService {
  private readonly http = inject(HttpClient);
  private readonly auth = inject(AuthService);

  register(payload: RegistrationPayload): Observable<RegistrationResponse> {
    return this.auth.ensureCsrfCookie().pipe(
      switchMap(() =>
        this.http.post<RegistrationResponse>('/api/register/', payload),
      ),
    );
  }

  getPreferences(): Observable<PreferencesResponse> {
    return this.http.get<PreferencesResponse>('/api/preferences/');
  }

  savePreferences(payload: Preferences): Observable<PreferencesResponse> {
    return this.auth.ensureCsrfCookie().pipe(
      switchMap(() =>
        this.http.post<PreferencesResponse>(
          '/api/preferences/save/',
          payload,
        ),
      ),
    );
  }

  resendVerification(): Observable<{ status: string; message: string }> {
    return this.auth.ensureCsrfCookie().pipe(
      switchMap(() =>
        this.http.post<{ status: string; message: string }>(
          '/api/preferences/resend-verification/',
          {},
        ),
      ),
    );
  }

  getNewsletterPreview(): Observable<NewsletterPreviewResponse> {
    return this.http.get<NewsletterPreviewResponse>('/api/newsletter/');
  }

  sendManualNewsletter(): Observable<NewsletterSendResponse> {
    return this.auth.ensureCsrfCookie().pipe(
      switchMap(() =>
        this.http.post<NewsletterSendResponse>('/api/newsletter/send/', {}),
      ),
    );
  }

  getNewsletterHistory(): Observable<NewsletterHistoryResponse> {
    return this.http.get<NewsletterHistoryResponse>(
      '/api/newsletter/history/',
    );
  }

  getVerification(token: string): Observable<VerificationResponse> {
    const params = new HttpParams().set('token', token);
    return this.http.get<VerificationResponse>('/api/verify-email/', {
      params,
    });
  }

  confirmVerification(token: string): Observable<VerificationResponse> {
    return this.auth.ensureCsrfCookie().pipe(
      switchMap(() =>
        this.http.post<VerificationResponse>(
          '/api/verify-email/confirm/',
          { token },
        ),
      ),
    );
  }
}
