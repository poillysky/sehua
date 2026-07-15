import { FloatTool } from "@/components/FloatTool";

export default function SearchLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <>
      <section className="flex flex-col justify-center gap-4 px-3 py-3 pb-8 md:py-8 md:pb-8">
        {children}
      </section>
      <FloatTool />
    </>
  );
}
