import { ImageResponse } from "next/og";

/** Shared brand mark for favicon / Apple touch / PWA icons */
export function renderAppIcon(size: number) {
  const pad = Math.round(size * 0.14);
  const inner = size - pad * 2;
  const radius = Math.round(size * 0.22);
  const stroke = Math.max(2, Math.round(size * 0.055));
  const letterSize = Math.round(size * 0.48);

  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          background:
            "linear-gradient(145deg, #0B1220 0%, #111827 55%, #0F172A 100%)",
        }}
      >
        <div
          style={{
            width: inner,
            height: inner,
            borderRadius: radius,
            border: `${stroke}px solid #00A8FF`,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            background: "rgba(0, 168, 255, 0.08)",
          }}
        >
          <div
            style={{
              fontSize: letterSize,
              fontWeight: 800,
              color: "#00A8FF",
              letterSpacing: "-0.06em",
              lineHeight: 1,
              fontFamily:
                "ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, sans-serif",
            }}
          >
            E
          </div>
        </div>
      </div>
    ),
    { width: size, height: size },
  );
}
