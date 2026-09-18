"use client";

import { Alert, ButtonLink, Card } from "@/components/ui";
import { ApiError } from "@/lib/api";

/** Renders a friendly message for API errors, with an upgrade path when a feature needs a higher plan. */
export function ErrorPanel({ error }: { error: unknown }) {
  if (error instanceof ApiError && error.code === "upgrade_required") {
    return (
      <Card className="flex flex-col items-start gap-3">
        <p className="font-semibold">This feature is part of a higher plan.</p>
        <p className="text-sm text-muted">Compare plans to unlock it. You can cancel any time.</p>
        <ButtonLink href="/pricing">See plans</ButtonLink>
      </Card>
    );
  }
  return <Alert tone="error">{error instanceof Error ? error.message : "Something went wrong."}</Alert>;
}
