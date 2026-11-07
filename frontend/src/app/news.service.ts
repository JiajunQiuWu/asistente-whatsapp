import { HttpClient, HttpParams } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { Observable } from 'rxjs';
import { NewsResponse } from './api.models';

@Injectable({ providedIn: 'root' })
export class NewsService {
  private readonly http = inject(HttpClient);

  getNews(topic: string): Observable<NewsResponse> {
    let params = new HttpParams();
    if (topic) {
      params = params.set('tema', topic);
    }
    return this.http.get<NewsResponse>('/api/news/', { params });
  }
}
