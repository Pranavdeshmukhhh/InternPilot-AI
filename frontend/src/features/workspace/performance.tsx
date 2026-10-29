'use client';
import { useReportWebVitals } from 'next/web-vitals';
// Local observation only. No user content, identifiers or telemetry upload.
export function PerformanceObserver() {
  useReportWebVitals((metric) =>
    window.dispatchEvent(
      new CustomEvent('internpilot:performance', {
        detail: { name: metric.name, value: metric.value, rating: metric.rating },
      }),
    ),
  );
  return null;
}
