import { HttpErrorResponse } from '@angular/common/http';
import { Component, inject, OnInit, signal } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { catchError, distinctUntilChanged, map, of, switchMap, tap } from 'rxjs';
import { NewsResponse } from '../api.models';
import { NewsService } from '../news.service';

@Component({
  imports: [RouterLink],
  selector: 'app-news',
  templateUrl: './news.component.html',
})
export class NewsComponent implements OnInit {
  private readonly route = inject(ActivatedRoute);
  private readonly newsService = inject(NewsService);

  readonly data = signal<NewsResponse | null>(null);
  readonly loading = signal(true);
  readonly error = signal<string | null>(null);
  readonly loginRequired = signal(false);

  ngOnInit(): void {
    this.route.queryParamMap
      .pipe(
        map((params) => params.get('tema') ?? ''),
        distinctUntilChanged(),
        tap(() => {
          this.loading.set(true);
          this.error.set(null);
          this.loginRequired.set(false);
        }),
        switchMap((topic) =>
          this.newsService.getNews(topic).pipe(
            map((data) => ({ data, error: null, loginRequired: false })),
            catchError((error: HttpErrorResponse) =>
              of({
                data: null,
                error: this.errorMessage(error),
                loginRequired: error.status === 401,
              }),
            ),
          ),
        ),
      )
      .subscribe((result) => {
        this.data.set(result.data);
        this.error.set(result.error);
        this.loginRequired.set(result.loginRequired);
        this.loading.set(false);
      });
  }

  private errorMessage(error: HttpErrorResponse): string {
    if (error.status === 401) {
      return 'Tu sesión ya no está activa. Inicia sesión para consultar las noticias.';
    }
    if (error.status === 0) {
      return 'No se pudieron cargar las noticias. Comprueba que Django esté iniciado.';
    }
    return 'No se pudieron cargar las noticias. Inténtalo de nuevo.';
  }
}
