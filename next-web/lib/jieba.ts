const requiredTags = [
  ["n", "nr", "ns", "nt", "nz"], // noun
  "vn", // gerund
  "x", // other
].flat();

type CutItem = { keyword: string; required: boolean };

type TagFn = (
  text: string,
  happy?: boolean,
) => Array<{ word: string; tag: string }>;

let tagFn: TagFn | null = null;
try {
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  tagFn = require("@node-rs/jieba").tag as TagFn;
} catch (err) {
  console.warn("[jieba] native binding unavailable, fallback to noop:", err);
}

export function jiebaCut(text: string): CutItem[] {
  if (!tagFn) {
    const t = String(text || "").trim();
    return t ? [{ keyword: t, required: true }] : [];
  }
  return tagFn(text, true).map((_) => ({
    keyword: _.word,
    required: requiredTags.includes(_.tag),
  }));
}
