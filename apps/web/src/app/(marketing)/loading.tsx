import { PageLoading } from "@/components/page-loading";
import { Container } from "@/components/ui";

export default function Loading() {
  return (
    <Container className="py-12">
      <PageLoading />
    </Container>
  );
}
