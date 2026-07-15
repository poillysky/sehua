"use client";

import { useEffect, useState, useMemo } from "react";
import Particles, { initParticlesEngine } from "@tsparticles/react";
import { loadSlim } from "@tsparticles/slim";
import { useIsSSR } from "@react-aria/ssr";
import { useTheme } from "next-themes";

import { UI_BACKGROUND_ANIMATION } from "@/config/constant";

export const BgEffect = () => {
  const [init, setInit] = useState(false);
  const [colorScheme, setColorScheme] = useState<"light" | "dark">("light");

  const { theme } = useTheme();
  const isSSR = useIsSSR();

  useEffect(() => {
    if (theme === "system") {
      const mediaQuery = window.matchMedia("(prefers-color-scheme: dark)");

      if (!mediaQuery) return;

      mediaQuery.addEventListener("change", (event) => {
        setColorScheme(event.matches ? "dark" : "light");
      });

      setColorScheme(mediaQuery.matches ? "dark" : "light");
    } else {
      setColorScheme(theme === "dark" ? "dark" : "light");
    }
  }, [theme]);

  useEffect(() => {
    if (!UI_BACKGROUND_ANIMATION) return;

    initParticlesEngine(async (engine) => {
      await loadSlim(engine);
    }).then(() => {
      setInit(true);
    });

    return () => setInit(false);
  }, []);

  const particlesOptions = useMemo(
    () =>
      ({
        // Transparent — Safari samples body / chrome tint bars, not this layer
        background: {
          color: { value: "transparent" },
        },
        fullScreen: {
          enable: false,
        },
        fpsLimit: 120,
        interactivity: {
          events: {
            onHover: {
              enable: true,
              mode: "grab",
            },
          },
          modes: {
            push: {
              quantity: 4,
            },
            repulse: {
              distance: 200,
              duration: 0.4,
            },
          },
        },
        particles: {
          color: {
            value: colorScheme === "light" ? "#c1c7d1" : "#3b4250",
          },
          links: {
            value: colorScheme === "light" ? "#c1c7d1" : "#3b4250",
            distance: 150,
            enable: true,
            opacity: colorScheme === "light" ? 0.8 : 0.1,
            width: 1,
          },
          move: {
            direction: "none",
            enable: true,
            outModes: {
              default: "bounce",
            },
            random: false,
            speed: 1,
            straight: false,
          },
          number: {
            density: {
              enable: true,
            },
            value: 80,
          },
          opacity: {
            value: 0.8,
          },
          shape: {
            type: "circle",
          },
          size: {
            value: { min: 1, max: 5 },
          },
        },
        detectRetina: true,
      }) as any,
    [colorScheme],
  );

  if (isSSR) return null;

  // Solid page color comes from body CSS; no opaque fixed gradient that steals Safari sampling
  if (!UI_BACKGROUND_ANIMATION) {
    return null;
  }

  if (!init) return null;

  return (
    <div aria-hidden className="bg-effect-layer">
      <Particles
        className="h-full w-full"
        options={particlesOptions}
        particlesLoaded={async (_container) => {
          // ready
        }}
      />
    </div>
  );
};
