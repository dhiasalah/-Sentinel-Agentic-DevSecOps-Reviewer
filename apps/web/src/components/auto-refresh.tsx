"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

// Re-reads the server page every few seconds while something is still being worked on. Unmounts (and stops) as soon
// as the page no longer renders it, and pauses while the tab is hidden.
export function AutoRefresh({ seconds = 5 }: { seconds?: number }) {
  const router = useRouter();
  useEffect(() => {
    const timer = setInterval(() => {
      if (document.visibilityState === "visible") router.refresh();
    }, seconds * 1000);
    return () => clearInterval(timer);
  }, [router, seconds]);
  return null;
}
