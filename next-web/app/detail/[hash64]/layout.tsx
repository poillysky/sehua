import { FloatTool } from "@/components/FloatTool";
import { PageSearchHeader } from "@/components/PageSearchHeader";

export default function DetailLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <section className="flex flex-col justify-center gap-4 py-3 md:py-8">
      <PageSearchHeader className="mb-1" />
      <div className="px-3">{children}</div>
      <FloatTool />
    </section>
  );
}
