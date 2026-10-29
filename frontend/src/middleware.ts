import { NextResponse, type NextRequest } from 'next/server';
import { routes, type View } from '@/lib/routes';
// Preserve historic root view links while keeping the public page static.
export function middleware(request: NextRequest) {
  const view = request.nextUrl.searchParams.get('view');
  if (view && Object.hasOwn(routes, view))
    return NextResponse.redirect(new URL(routes[view as View], request.url));
  return NextResponse.next();
}
export const config = { matcher: ['/'] };
