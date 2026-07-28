import makersJson from "./av-makers.japan.json";

export type AvMakerKind = "有码" | "无码";

export type AvMakerEntry = {
  maker: string;
  kind: AvMakerKind;
  description?: string;
  prefixes: string[];
  prefix_notes?: Record<string, string>;
};

export const AV_MAKERS_JAPAN = makersJson as AvMakerEntry[];

const byMaker = new Map(
  AV_MAKERS_JAPAN.map((m) => [m.maker.trim().toLowerCase(), m]),
);

export function findMakerMeta(maker: string): AvMakerEntry | undefined {
  const key = (maker || "").trim().toLowerCase();
  if (!key) return undefined;
  return byMaker.get(key);
}

export function makerDescription(maker: string): string {
  return findMakerMeta(maker)?.description?.trim() || "";
}

export function prefixNote(maker: string, prefix: string): string {
  const meta = findMakerMeta(maker);
  if (!meta?.prefix_notes) return "";
  const code = (prefix || "").trim();
  if (!code) return "";
  return (
    meta.prefix_notes[code]?.trim() ||
    meta.prefix_notes[code.toUpperCase()]?.trim() ||
    ""
  );
}
