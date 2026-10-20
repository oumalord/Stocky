import { ApplicationConfig } from '@angular/core';
import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { provideRouter } from '@angular/router';
import { provideIcons } from '@ng-icons/core';
import { lucideArrowRight, lucideChartNoAxesCombined, lucideClipboardList, lucideLogOut, lucidePlus,
  lucideRefreshCw } from '@ng-icons/lucide';
import { routes } from './app.routes';
import { apiInterceptor } from './core/api.interceptor';

export const appConfig: ApplicationConfig = {
  providers: [
    provideRouter(routes),
    provideHttpClient(withInterceptors([apiInterceptor])),
    provideIcons({ lucideArrowRight, lucideChartNoAxesCombined, lucideClipboardList, lucideLogOut, lucidePlus,
      lucideRefreshCw }),
  ],
};
