import { CommonModule } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { NgIcon } from '@ng-icons/core';

interface Page<T> { results: T[]; count: number; }
interface Variance {
  id: string; count_reference: string; location_code: string; product_sku: string; product_name: string;
  expected_quantity: string; counted_quantity: string; variance_quantity: string; variance_percent: string | null;
  unit_cost: string; shortage_cost: string; surplus_cost: string; net_cost_variance: string;
  shortage_retail: string; surplus_retail: string; counted_at: string;
}
type VarianceFilter = 'ALL' | 'SHORTAGE' | 'SURPLUS';

@Component({
  selector: 'sp-variances',
  standalone: true,
  imports: [CommonModule, NgIcon],
  templateUrl: './variances.component.html',
  styleUrl: './variances.component.css',
})
export class VariancesComponent implements OnInit {
  private readonly http = inject(HttpClient);
  readonly rows = signal<Variance[]>([]);
  readonly filter = signal<VarianceFilter>('ALL');
  readonly query = signal('');
  readonly loading = signal(true);
  readonly error = signal('');
  readonly grossShortage = computed(() => this.rows().reduce((total, row) => total + Number(row.shortage_cost), 0));
  readonly grossSurplus = computed(() => this.rows().reduce((total, row) => total + Number(row.surplus_cost), 0));
  readonly netCost = computed(() => this.rows().reduce((total, row) => total + Number(row.net_cost_variance), 0));
  readonly filtered = computed(() => {
    const query = this.query().trim().toLowerCase();
    return this.rows().filter((row) => {
      const categoryMatches = this.filter() === 'ALL'
        || (this.filter() === 'SHORTAGE' ? Number(row.variance_quantity) < 0 : Number(row.variance_quantity) > 0);
      const queryMatches = !query || `${row.count_reference} ${row.location_code} ${row.product_sku} ${row.product_name}`
        .toLowerCase().includes(query);
      return categoryMatches && queryMatches;
    });
  });

  ngOnInit(): void { this.load(); }

  load(): void {
    this.loading.set(true);
    this.error.set('');
    this.http.get<Page<Variance>>('/api/v1/variances/').subscribe({
      next: (page) => { this.rows.set(page.results); this.loading.set(false); },
      error: () => { this.error.set('Could not load variances. Check your access and retry.'); this.loading.set(false); },
    });
  }

  isShortage(row: Variance): boolean { return Number(row.variance_quantity) < 0; }
}