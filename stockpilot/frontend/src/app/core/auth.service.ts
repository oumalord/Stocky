import { HttpClient } from '@angular/common/http';
import { Injectable, computed, inject, signal } from '@angular/core';
import { Observable, switchMap, tap } from 'rxjs';

export interface Membership {
  organisation_id: string; organisation_name: string; is_demo: boolean; currency: string;
  role: string; permissions: string[]; branch_ids: string[] | null;
}
export interface Me { id: string; email: string; full_name: string; memberships: Membership[]; }

@Injectable({ providedIn: 'root' })
export class AuthService {
  private http = inject(HttpClient);
  readonly me = signal<Me | null>(null);
  readonly activeOrgId = signal<string | null>(localStorage.getItem('sp_org'));
  readonly membership = computed(() => {
    const m = this.me()?.memberships ?? [];
    return m.find(x => x.organisation_id === this.activeOrgId()) ?? m[0] ?? null;
  });

  /** UI hint only. The backend enforces every permission. */
  can(code: string): boolean {
    const p = this.membership()?.permissions ?? [];
    return p.includes('*') || p.includes(code);
  }

  private apply(me: Me) {
    this.me.set(me);
    const first = this.membership();
    if (first) { this.activeOrgId.set(first.organisation_id); localStorage.setItem('sp_org', first.organisation_id); }
  }

  load(): Observable<Me> { return this.http.get<Me>('/api/v1/auth/me/').pipe(tap(m => this.apply(m))); }
  login(email: string, password: string): Observable<Me> {
    // The GET sets the csrftoken cookie; the interceptor then sends it with the POST.
    return this.http.get('/api/v1/auth/csrf/').pipe(
      switchMap(() => this.http.post<Me>('/api/v1/auth/login/', { email, password })),
      tap(m => this.apply(m)));
  }
  logout(): Observable<unknown> { return this.http.post('/api/v1/auth/logout/', {}).pipe(tap(() => this.me.set(null))); }
}
