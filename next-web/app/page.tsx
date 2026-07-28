import { HomeHero } from "@/components/HomeHero";
import { HomeZones } from "@/components/HomeZones";
import { Stats } from "@/components/Stats";

export const dynamic = "force-dynamic";

export default function Home() {
  return (
    <section className="home-page relative mx-auto flex w-full max-w-5xl flex-col px-3 pb-[max(2.5rem,7vh)] pt-[max(0.75rem,2vh)] md:px-4 md:pb-14 md:pt-4 lg:max-w-6xl">
      <div aria-hidden className="home-page__glow" />
      <HomeHero />
      <HomeZones />

      <div className="safe-fixed-bottom-right fixed invisible md:visible">
        <Stats />
      </div>
    </section>
  );
}
