"use client";

import { useFormStatus } from "react-dom";

// A submit button that says what it is doing and can't be pressed twice while the form is sending.
export function SubmitButton({ children, pending, className }: { children: React.ReactNode; pending: string; className: string }) {
  const status = useFormStatus();
  return (
    <button type="submit" disabled={status.pending} aria-disabled={status.pending} className={`${className} disabled:cursor-wait disabled:opacity-60`}>
      {status.pending ? pending : children}
    </button>
  );
}
