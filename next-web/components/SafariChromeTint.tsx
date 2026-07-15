"use client";

/**
 * Full-width fixed edge strips for iOS Safari 26+ Liquid Glass tab/toolbar tinting.
 * Safari ignores theme-color and samples fixed/sticky edge backgrounds (then body).
 * Hidden outside iOS Safari via CSS; pointer-events none so they never block UI.
 */
export function SafariChromeTint() {
  return (
    <>
      <div aria-hidden className="safari-chrome-tint safari-chrome-tint--top" />
      <div aria-hidden className="safari-chrome-tint safari-chrome-tint--bottom" />
    </>
  );
}
