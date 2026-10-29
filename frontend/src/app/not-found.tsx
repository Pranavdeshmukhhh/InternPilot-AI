import Link from 'next/link';

export default function NotFound() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center p-8 text-center bg-background text-foreground">
      <h1 className="text-6xl font-extrabold tracking-tight mb-4">404</h1>
      <p className="text-xl text-muted-foreground mb-8">Page not found.</p>
      <Link
        href="/"
        className="rounded-lg bg-primary px-6 py-3 text-sm font-semibold text-primary-foreground shadow-sm hover:opacity-90 transition-opacity"
      >
        Return Home
      </Link>
    </div>
  );
}
