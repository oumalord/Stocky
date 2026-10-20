import { CommonModule } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { NgIcon } from '@ng-icons/core';
import { forkJoin } from 'rxjs';

interface Page<T> { results: T[]; count: number; }
interface Location { id: string; code: string; name: string; }
interface Product { id: string; sku: string; name: string; base_uom: string; }
interface CountLine {
  id: string; product: string; product_sku: string; product_name: string; expected_at_start: string | null;
  counted_quantity: string | null; expected_quantity: string | null; variance_quantity: string | null;
  variance_percent: string | null; shortage_cost: string | null; surplus_cost: string | null;
  net_cost_variance: string | null; unit_cost: string;
}
interface StockCount {
  id: string; reference: string; location: string; location_code: string; status: 'DRAFT' | 'SUBMITTED' | 'CANCELLED';
  blind: boolean; snapshot_at: string; created_at: string; lines: CountLine[];
}

@Component({
  selector: 'sp-counts',
  standalone: true,
  imports: [CommonModule, FormsModule, NgIcon],
  templateUrl: './counts.component.html',
  styleUrl: './counts.component.css',
})
export class CountsComponent implements OnInit {
  private readonly http = inject(HttpClient);
  readonly locations = signal<Location[]>([]);
  readonly products = signal<Product[]>([]);
  readonly counts = signal<StockCount[]>([]);
  readonly active = signal<StockCount | null>(null);
  readonly selectedLocation = signal('');
  readonly selectedProducts = signal<string[]>([]);
  readonly blind = signal(false);
  readonly quantities = signal<Record<string, string>>({});
  readonly recordKeys = signal<Record<string, string>>({});
  readonly loading = signal(true);
  readonly saving = signal(false);
  readonly error = signal('');
  readonly notice = signal('');

  ngOnInit(): void { this.load(); }

  load(): void {
    this.loading.set(true);
    this.error.set('');
    forkJoin({
      locations: this.http.get<Page<Location>>('/api/v1/locations/'),
      products: this.http.get<Page<Product>>('/api/v1/products/'),
      counts: this.http.get<Page<StockCount>>('/api/v1/stock-counts/'),
    }).subscribe({
      next: ({ locations, products, counts }) => {
        this.locations.set(locations.results);
        this.products.set(products.results);
        this.counts.set(counts.results);
        if (!this.selectedLocation() && locations.results.length) this.selectedLocation.set(locations.results[0].id);
        if (this.active()) this.selectCount(this.active()!.id);
        this.loading.set(false);
      },
      error: () => { this.error.set('Could not load stock counts. Check your connection and retry.'); this.loading.set(false); },
    });
  }

  toggleProduct(id: string, checked: boolean): void {
    this.selectedProducts.update((ids) => checked ? [...ids, id] : ids.filter((item) => item !== id));
  }

  createCount(): void {
    if (!this.selectedLocation() || !this.selectedProducts().length) return;
    this.saving.set(true);
    this.notice.set('');
    this.http.post<StockCount>('/api/v1/stock-counts/', {
      location: this.selectedLocation(), products: this.selectedProducts(), blind: this.blind(),
    }, { headers: { 'Idempotency-Key': crypto.randomUUID() } }).subscribe({
      next: (count) => {
        this.selectedProducts.set([]);
        this.blind.set(false);
        this.counts.update((items) => [count, ...items]);
        this.selectCount(count.id);
        this.notice.set(`${count.reference} created with ${count.lines.length} products.`);
        this.saving.set(false);
      },
      error: () => { this.error.set('Could not create the count. Check the selected products and try again.'); this.saving.set(false); },
    });
  }

  selectCount(id: string): void {
    const count = this.counts().find((item) => item.id === id);
    if (!count) return;
    this.active.set(count);
    this.quantities.set(Object.fromEntries(count.lines.map((line) => [line.id, line.counted_quantity ?? ''])));
  }

  setQuantity(lineId: string, value: string): void {
    this.quantities.update((values) => ({ ...values, [lineId]: value }));
    this.recordKeys.update((keys) => Object.fromEntries(Object.entries(keys).filter(([id]) => id !== lineId)));
  }

  recordLine(line: CountLine): void {
    const quantity = this.quantities()[line.id];
    if (quantity === undefined || quantity === '') return;
    const count = this.active();
    if (!count) return;
    const key = this.recordKeys()[line.id] ?? crypto.randomUUID();
    this.recordKeys.update((keys) => ({ ...keys, [line.id]: key }));
    this.saving.set(true);
    this.http.post<CountLine>(`/api/v1/stock-counts/${count.id}/record/`, {
      product: line.product, counted_quantity: quantity,
    }, { headers: { 'Idempotency-Key': key } }).subscribe({
      next: (updated) => {
        this.updateActiveLine(updated);
        this.recordKeys.update((keys) => Object.fromEntries(Object.entries(keys).filter(([id]) => id !== line.id)));
        this.saving.set(false);
        this.notice.set(`${line.product_sku} count saved.`);
      },
      error: () => { this.error.set(`Could not save ${line.product_sku}.`); this.saving.set(false); },
    });
  }

  submitCount(): void {
    const count = this.active();
    if (!count || count.status !== 'DRAFT') return;
    if (!window.confirm(`Submit ${count.reference}? Submitted counts cannot be edited.`)) return;
    this.saving.set(true);
    this.http.post<StockCount>(`/api/v1/stock-counts/${count.id}/submit/`, {}).subscribe({
      next: (submitted) => {
        this.active.set(submitted);
        this.counts.update((items) => items.map((item) => item.id === submitted.id ? submitted : item));
        this.notice.set(`${submitted.reference} submitted. Variances are now available in the register.`);
        this.saving.set(false);
      },
      error: (response) => {
        this.error.set(response.error?.message || 'Complete every product count before submitting.');
        this.saving.set(false);
      },
    });
  }

  private updateActiveLine(updated: CountLine): void {
    const count = this.active();
    if (!count) return;
    const next = { ...count, lines: count.lines.map((line) => line.id === updated.id ? updated : line) };
    this.active.set(next);
    this.counts.update((items) => items.map((item) => item.id === next.id ? next : item));
  }

  isShortage(value: string | null): boolean { return Number(value) < 0; }
  isSurplus(value: string | null): boolean { return Number(value) > 0; }
  shortageTotal(count: StockCount): number {
    return count.lines.reduce((total, line) => total + Number(line.shortage_cost || 0), 0);
  }
  surplusTotal(count: StockCount): number {
    return count.lines.reduce((total, line) => total + Number(line.surplus_cost || 0), 0);
  }
}