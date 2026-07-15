import { promises as fs } from "fs";
import path from "path";

export type P115Config = {
  cookie: string;
  folderCid: string;
  folderName?: string;
  label?: string;
  updatedAt?: string;
};

export type P115PublicStatus = {
  configured: boolean;
  folderCid: string;
  folderName: string;
  label: string;
  cookieHint: string;
  updatedAt: string;
};

const CONFIG_DIR = path.join(process.cwd(), "data");
const CONFIG_PATH = path.join(CONFIG_DIR, "p115-config.json");

const EMPTY: P115Config = {
  cookie: "",
  folderCid: "0",
  folderName: "",
  label: "",
};

function cookieHint(cookie: string): string {
  const uid = cookie.match(/(?:^|;\s*)UID=([^;]+)/i)?.[1]?.trim() || "";

  if (!uid) {
    return cookie.trim() ? "已配置" : "";
  }

  if (uid.length <= 8) {
    return uid;
  }

  return `${uid.slice(0, 4)}…${uid.slice(-4)}`;
}

export async function readP115Config(): Promise<P115Config> {
  try {
    const raw = await fs.readFile(CONFIG_PATH, "utf8");
    const data = JSON.parse(raw) as Partial<P115Config>;

    return {
      cookie: String(data.cookie || "").trim(),
      folderCid: String(data.folderCid ?? "0").trim() || "0",
      folderName: String(data.folderName || "").trim(),
      label: String(data.label || "").trim(),
      updatedAt: data.updatedAt,
    };
  } catch {
    return { ...EMPTY };
  }
}

export async function writeP115Config(input: Partial<P115Config>): Promise<P115Config> {
  const prev = await readP115Config();
  const next: P115Config = {
    cookie: input.cookie !== undefined ? String(input.cookie).trim() : prev.cookie,
    folderCid:
      input.folderCid !== undefined
        ? String(input.folderCid).trim() || "0"
        : prev.folderCid || "0",
    folderName:
      input.folderName !== undefined
        ? String(input.folderName).trim()
        : prev.folderName || "",
    label: input.label !== undefined ? String(input.label).trim() : prev.label || "",
    updatedAt: new Date().toISOString(),
  };

  await fs.mkdir(CONFIG_DIR, { recursive: true });
  await fs.writeFile(CONFIG_PATH, JSON.stringify(next, null, 2), "utf8");

  return next;
}

export function toPublicStatus(cfg: P115Config): P115PublicStatus {
  const configured = Boolean(cfg.cookie && /UID=/i.test(cfg.cookie));

  return {
    configured,
    folderCid: cfg.folderCid || "0",
    folderName: cfg.folderName || "",
    label: cfg.label || "",
    cookieHint: configured ? cookieHint(cfg.cookie) : "",
    updatedAt: cfg.updatedAt || "",
  };
}
