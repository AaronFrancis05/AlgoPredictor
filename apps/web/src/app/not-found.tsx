import { ButtonLink } from "@/components/ui";

export default function NotFound() {
  return (
    <main id="main" className="flex min-h-screen flex-col items-center justify-center gap-4 px-4 text-center">
      <p className="text-sm text-muted">404</p>
      <h1 className="text-3xl font-bold">This page does not exist</h1>
      <ButtonLink href="/">Back to home</ButtonLink>
    </main>
  );
}
