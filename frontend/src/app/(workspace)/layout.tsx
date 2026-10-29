import { Providers } from '@/features/workspace/provider';
export default function WorkspaceLayout({ children }: { children: React.ReactNode }) {
  return <Providers>{children}</Providers>;
}
