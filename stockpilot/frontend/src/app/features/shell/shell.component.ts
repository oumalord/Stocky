import { Component, inject } from '@angular/core';
import { NgIcon } from '@ng-icons/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { AuthService } from '../../core/auth.service';

@Component({
  selector: 'sp-shell',
  standalone: true,
  imports: [NgIcon, RouterLink, RouterLinkActive, RouterOutlet],
  templateUrl: './shell.component.html',
  styleUrl: './shell.component.css',
})
export class ShellComponent {
  readonly auth = inject(AuthService);

  logout(): void {
    this.auth.logout().subscribe({ next: () => window.location.assign('/login') });
  }
}