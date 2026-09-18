"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Alert, Button, Card, PageHeader, Spinner } from "@/components/ui";
import { api } from "@/lib/api";
import { useMe } from "@/lib/hooks";
import { User } from "@/lib/schemas";

export default function Onboarding() {
  const router = useRouter();
  const qc = useQueryClient();
  const me = useMe();
  const [checked, setChecked] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const alreadyConfirmed = Boolean(me.data?.age_confirmed);

  // Age is confirmed at sign-up; this page only exists for accounts that skipped it (e.g. Google sign-in).
  useEffect(() => {
    if (alreadyConfirmed) router.replace("/dashboard");
  }, [alreadyConfirmed, router]);
  if (alreadyConfirmed) return <Spinner label="Redirecting" />;

  async function confirm() {
    try {
      const user = await api("/auth/confirm-age", User, { method: "POST", json: { confirm_age_18: true } });
      qc.setQueryData(["me"], user);
      router.replace("/dashboard");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save");
    }
  }

  return (
    <div className="mx-auto max-w-lg">
      <PageHeader title="One last step" subtitle="AlgoPredict is only for adults." />
      <Card className="space-y-4">
        {error ? <Alert tone="error">{error}</Alert> : null}
        <label className="flex items-start gap-2 text-sm">
          <input type="checkbox" className="mt-1" checked={checked} onChange={(e) => setChecked(e.target.checked)} />
          <span>I confirm I am 18 or older and allowed to use betting information where I live.</span>
        </label>
        <Button onClick={confirm} disabled={!checked} className="w-full">Continue</Button>
      </Card>
    </div>
  );
}
