import { PageLoading } from "@/components/page-loading";

// Rendered inside the app shell (header and nav stay), so a tab click shows this at once.
export default function Loading() {
  return <PageLoading />;
}
