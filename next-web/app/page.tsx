import { HomeHero } from "@/components/HomeHero";
import { HomePulse } from "@/components/HomePulse";
import { HomeZones } from "@/components/HomeZones";
import { Stats } from "@/components/Stats";

export const dynamic = "force-dynamic";

export default function Home() {
  return (
    <section className="home-page relative mx-auto flex h-full min-h-0 w-full max-w-5xl flex-1 flex-col overflow-hidden lg:max-w-6xl">
      <HomeHero brandCorner={<HomePulse />} />
      <HomeZones />

      <div className="safe-fixed-bottom-right fixed invisible md:visible">
        <Stats />
      </div>
    </section>
  );
}
