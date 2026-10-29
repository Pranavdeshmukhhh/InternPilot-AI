import type { Metadata } from 'next';
import { RecoveryForm } from '@/features/auth/recovery-form';
export const metadata: Metadata = { title: 'Account recovery', robots: { index: false, follow: false } };
export default function Recover() {
  return <RecoveryForm />;
}
