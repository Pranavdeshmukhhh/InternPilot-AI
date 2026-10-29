import { notFound } from 'next/navigation';
import { routes } from '@/lib/routes';
import type { Metadata } from 'next';
export const metadata: Metadata = { robots: { index: false, follow: false } };
import { Suspense } from 'react';
import { Workspace } from '@/features/workspace/workspace';
import { Skeleton } from '@/components/ui/skeleton';
export default async function WorkspacePage({ params }: { params: Promise<{ workspace: string[] }> }) {
  const path = '/' + (await params).workspace.join('/');
  if (![...Object.values(routes), '/login', '/register'].includes(path)) notFound();
  return (
    <Suspense fallback={<Skeleton />}>
      <Workspace />
    </Suspense>
  );
}
