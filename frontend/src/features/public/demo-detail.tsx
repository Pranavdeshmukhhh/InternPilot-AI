'use client';
import * as Dialog from '@radix-ui/react-dialog';
import Link from 'next/link';
import type { Example } from './demo';
export default function DemoDetail({
  row,
  workspaceAvailable,
  onClose,
  returnFocus,
}: {
  row: Example;
  workspaceAvailable: boolean;
  onClose: () => void;
  returnFocus: () => void;
}) {
  return (
    <Dialog.Root
      open
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <Dialog.Portal>
        <Dialog.Overlay className="public-dialog-overlay" />
        <Dialog.Content
          className="public-dialog"
          onCloseAutoFocus={(event) => {
            event.preventDefault();
            returnFocus();
          }}
        >
          <Dialog.Close className="public-dialog-close" aria-label="Close demo detail">
            ×
          </Dialog.Close>
          <span className="public-eyebrow">FICTIONAL DEMONSTRATION</span>
          <Dialog.Title>{row.title}</Dialog.Title>
          <Dialog.Description>
            {row.company} · {row.place}
          </Dialog.Description>
          <h3>Eligibility, with context.</h3>
          <p>{row.reason}</p>
          <h3>What is verified here?</h3>
          <p>
            Nothing about a real employer. These examples explain the interface. Real opportunities show their
            original source, last verification and disclosed requirements.
          </p>
          <p>Deadline, stipend and live application URL: not applicable to this demo.</p>
          <Link className="public-cta" href={workspaceAvailable ? '/register' : '/'} prefetch={false}>
            {workspaceAvailable ? 'Start your own notebook' : 'About this product preview'}{' '}
            <span aria-hidden="true">→</span>
          </Link>
          <Dialog.Close className="public-text-button">Back to examples</Dialog.Close>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
