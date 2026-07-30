export type LogLine = {
  t: string;
  level: "info" | "warn" | "error";
  msg: string;
};

const MAX = 300;
const lines: LogLine[] = [];

export function pushLog(
  level: LogLine["level"],
  msg: string,
): void {
  const text = String(msg || "").trim();
  if (!text) return;
  lines.push({
    t: new Date().toISOString(),
    level,
    msg: text.slice(0, 800),
  });
  if (lines.length > MAX) lines.splice(0, lines.length - MAX);
}

export function getLogs(limit = 80): LogLine[] {
  const n = Math.max(1, Math.min(MAX, Number(limit) || 80));
  return lines.slice(-n);
}

/** 把带 [scrape] 前缀的 console 输出收进环形缓冲 */
export function installScrapeLogCapture(): void {
  const wrap =
    (level: LogLine["level"], orig: (...a: unknown[]) => void) =>
    (...args: unknown[]) => {
      const msg = args
        .map((a) => {
          if (typeof a === "string") return a;
          if (a instanceof Error) return a.message;
          try {
            return JSON.stringify(a);
          } catch {
            return String(a);
          }
        })
        .join(" ");
      if (/\[scrape/i.test(msg)) pushLog(level, msg);
      orig.apply(console, args as never[]);
    };
  console.log = wrap("info", console.log.bind(console));
  console.warn = wrap("warn", console.warn.bind(console));
  console.error = wrap("error", console.error.bind(console));
}
