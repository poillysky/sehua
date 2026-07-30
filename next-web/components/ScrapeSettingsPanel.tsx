"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Button,
  Input,
  Modal,
  ModalBody,
  ModalContent,
  ModalFooter,
  ModalHeader,
  Select,
  SelectItem,
  Switch,
} from "@nextui-org/react";
import clsx from "clsx";

import {
  SCRAPE_AUTO_REGIONS,
  resolveScopePrefixes,
  scrapeNestedBoards,
  scrapeRegionPrefixes,
  type ScrapeAutoScope,
  type ScrapeRegionId,
} from "@/config/boards";
import { MetaPreviewCard } from "@/components/scrape/MetaPreviewCard";
import {
  metaEqual,
  type ScrapePayload,
} from "@/components/scrape/types";
import { Toast } from "@/utils";

const shell =
  "overflow-hidden rounded-lg border border-gray-200 bg-white shadow-sm dark:border-slate-700 dark:bg-slate-900";
const inputWrap =
  "bg-gray-50 dark:bg-slate-800/80 border border-gray-200 dark:border-slate-700 shadow-none";

const ALL_CODES = "__ALL__";
const ALL_BOARD = "__ALL__";
const ALL_PREFIX = "__ALL__";

const MONITOR_INTERVALS = [
  { key: "5", label: "每 5 分钟" },
  { key: "15", label: "每 15 分钟" },
  { key: "30", label: "每 30 分钟" },
  { key: "60", label: "每 60 分钟" },
] as const;

const CONCURRENCY_OPTIONS = [
  { key: "1", label: "1" },
  { key: "2", label: "2" },
  { key: "3", label: "3" },
  { key: "4", label: "4" },
  { key: "5", label: "5" },
  { key: "6", label: "6" },
  { key: "8", label: "8" },
] as const;

type MonitorTargetUi = ScrapeAutoScope & {
  id: string;
  prefixes: string[];
  /** 有码/无码/素人/FC2/国产/欧美 */
  mode: CodeKind;
};

type CodeKind =
  | "av"
  | "uncensored"
  | "mgstage"
  | "fc2"
  | "chinese"
  | "western";
type PriorityOrders = { meta: string[]; cover: string[] };
type PriorityByKind = Record<CodeKind, PriorityOrders>;

const SCRAPE_KIND_OPTIONS: Array<{ key: CodeKind; label: string }> = [
  { key: "av", label: "有码" },
  { key: "uncensored", label: "无码" },
  { key: "mgstage", label: "素人" },
  { key: "fc2", label: "FC2" },
  { key: "chinese", label: "国产" },
  { key: "western", label: "欧美" },
];

const PRIORITY_KIND_ROWS = [
  { key: "av" as const, label: "有码番号" },
  { key: "uncensored" as const, label: "无码番号" },
  { key: "mgstage" as const, label: "素人番号" },
  { key: "fc2" as const, label: "FC2番号" },
  { key: "chinese" as const, label: "国产番号" },
  { key: "western" as const, label: "欧美影片" },
];

const EMPTY_PRIORITY: PriorityByKind = {
  av: { meta: [], cover: [] },
  uncensored: { meta: [], cover: [] },
  mgstage: { meta: [], cover: [] },
  fc2: { meta: [], cover: [] },
  chinese: { meta: [], cover: [] },
  western: { meta: [], cover: [] },
};

function normalizeKind(raw: unknown): CodeKind {
  const s = String(raw || "").trim().toLowerCase();
  if (SCRAPE_KIND_OPTIONS.some((o) => o.key === s)) return s as CodeKind;
  return "av";
}

function kindLabel(kind: CodeKind): string {
  return SCRAPE_KIND_OPTIONS.find((o) => o.key === kind)?.label || kind;
}

function newMonitorId(): string {
  return `mt_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 7)}`;
}

function scopePathLabel(scope: ScrapeAutoScope): string {
  const parts = [scope.region || "日本"];
  if (scope.board) parts.push(scope.board);
  else if (scope.region === "日本") parts.push("全部");
  if (scope.prefix) parts.push(scope.prefix);
  else parts.push("全部厂牌");
  if (scope.code) parts.push(scope.code);
  return parts.join(" / ");
}

function resolveMonitorPrefixes(scope: ScrapeAutoScope): string[] {
  if (scope.code) return [];
  if (scope.prefix) return [scope.prefix];
  return resolveScopePrefixes(scope).map((p) => p.prefix);
}

function withResolvedPrefixes(
  scope: ScrapeAutoScope & { id?: string; mode?: CodeKind },
): MonitorTargetUi {
  return {
    id: scope.id || newMonitorId(),
    region: scope.region,
    board: scope.board || "",
    prefix: scope.prefix || "",
    code: scope.code || "",
    mode: normalizeKind(scope.mode),
    prefixes: resolveMonitorPrefixes(scope),
  };
}

function parseMonitorTarget(t: Partial<MonitorTargetUi>): MonitorTargetUi {
  return withResolvedPrefixes({
    id: String(t.id || ""),
    region: (["日本", "国产", "欧美"].includes(String(t.region))
      ? t.region
      : "日本") as ScrapeAutoScope["region"],
    board: String(t.board || ""),
    prefix: String(t.prefix || "").toUpperCase(),
    code: String(t.code || "").toUpperCase(),
    mode: normalizeKind(t.mode),
    prefixes: Array.isArray(t.prefixes) ? (t.prefixes as string[]) : [],
  });
}
type ScrapeTab = "basic" | "status" | "sources";

type SourceCard = {
  id: string;
  name: string;
  url: string;
  enabled: boolean;
  cookie?: string;
  userAgent?: string;
  proxyMode?: "inherit" | "on" | "off";
  timeoutMs?: number;
  retry?: number;
  useFlareSolverr?: boolean;
  status: "ok" | "error" | "unknown";
  lastCheckedAt: string | null;
  lastError: string | null;
  cooldownRemainingSec: number | null;
  group?: "av" | "fc2" | "chinese" | "other";
};

type QueueStats = {
  pending: number;
  running: number;
  done: number;
  error: number;
};

type RecentJob = {
  id: number;
  code: string;
  status: string;
  attempts: number;
  last_error: string | null;
  updated_at: string;
};

const GROUP_LABEL: Record<string, string> = {
  av: "AV",
  fc2: "FC2",
  chinese: "国产",
  other: "备选",
};

const TABS: Array<{ key: ScrapeTab; label: string }> = [
  { key: "basic", label: "基本配置" },
  { key: "status", label: "刮削状态" },
  { key: "sources", label: "数据源" },
];

function zhProbeError(raw: string | null | undefined): string {
  if (!raw) return "未知错误";
  const s = String(raw).trim();
  if (/^HTTP\s+(\d+)/i.test(s) || /^服务器错误/.test(s)) {
    const code = s.match(/\d+/)?.[0];
    return code ? `服务器错误（${code}）` : "服务器错误";
  }
  if (
    /timeout|aborted|TimeoutError|UND_ERR_CONNECT_TIMEOUT|HeadersTimeout|连接超时/i.test(
      s,
    )
  ) {
    return "连接超时";
  }
  if (/ECONNREFUSED|连接被拒绝/i.test(s)) return "连接被拒绝";
  if (/ENOTFOUND|getaddrinfo|域名无法解析/i.test(s)) return "域名无法解析";
  if (/ECONNRESET|socket hang up|连接被重置/i.test(s)) return "连接被重置";
  if (/CERT_|SSL|TLS|certificate|证书/i.test(s)) return "证书错误";
  if (/proxy|PROXY|代理/i.test(s)) return "代理异常";
  if (/fetch failed|请求失败/i.test(s)) return "请求失败";
  if (/network|网络/i.test(s)) return "网络异常";
  if (/[\u4e00-\u9fff]/.test(s)) return s;
  return `请求失败（${s.slice(0, 80)}）`;
}

function relativeTime(iso: string | null): string {
  if (!iso) return "";
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return "";
  const sec = Math.max(0, Math.floor((Date.now() - t) / 1000));
  if (sec < 60) return `${sec} 秒前`;
  if (sec < 3600) return `${Math.floor(sec / 60)} 分钟前`;
  if (sec < 86400) return `${Math.floor(sec / 3600)} 小时前`;
  return `${Math.floor(sec / 86400)} 天前`;
}

export function ScrapeSettingsPanel() {
  const [tab, setTab] = useState<ScrapeTab>("basic");
  const [online, setOnline] = useState<boolean | null>(null);
  const [checking, setChecking] = useState(false);
  const [testing, setTesting] = useState(false);
  const [result, setResult] = useState<ScrapePayload | null>(null);
  const [proxyUrl, setProxyUrl] = useState("");
  const [proxySaving, setProxySaving] = useState(false);
  const [flareSolverrUrl, setFlareSolverrUrl] = useState("");
  const [flareSaving, setFlareSaving] = useState(false);
  const [sources, setSources] = useState<SourceCard[]>([]);
  const [updatedAt, setUpdatedAt] = useState<string | null>(null);
  const [editId, setEditId] = useState<string | null>(null);
  const [editUrl, setEditUrl] = useState("");
  const [editCookie, setEditCookie] = useState("");
  const [editUserAgent, setEditUserAgent] = useState("");
  const [editProxyMode, setEditProxyMode] = useState<"inherit" | "on" | "off">(
    "inherit",
  );
  const [editTimeoutMs, setEditTimeoutMs] = useState("0");
  const [editRetry, setEditRetry] = useState("1");
  const [editUseFlare, setEditUseFlare] = useState(false);
  const [editSaving, setEditSaving] = useState(false);

  const [overwriteDefault, setOverwriteDefault] = useState(false);
  const [scrapeConcurrency, setScrapeConcurrency] = useState(3);
  const [activeJobs, setActiveJobs] = useState(0);
  const [autoWorker, setAutoWorker] = useState(true);
  const [autoScope, setAutoScope] = useState<ScrapeAutoScope>({
    region: "日本",
    board: "",
    prefix: "",
    code: "",
  });
  const [autoScopeCodes, setAutoScopeCodes] = useState<string[]>([]);
  const [editScopeCodes, setEditScopeCodes] = useState<string[]>([]);
  const [autoEnqueueBusy, setAutoEnqueueBusy] = useState(false);
  const [optionSaving, setOptionSaving] = useState(false);
  const [monitorEnabled, setMonitorEnabled] = useState(false);
  const [monitorIntervalMin, setMonitorIntervalMin] = useState(15);
  const [monitorRunning, setMonitorRunning] = useState(false);
  const [monitorTargets, setMonitorTargets] = useState<MonitorTargetUi[]>([]);
  const [editTarget, setEditTarget] = useState<MonitorTargetUi | null>(null);
  const [metaLoading, setMetaLoading] = useState(false);
  const [priorityByKind, setPriorityByKind] =
    useState<PriorityByKind>(EMPTY_PRIORITY);
  const [prioritySaving, setPrioritySaving] = useState(false);

  const [queue, setQueue] = useState<QueueStats>({
    pending: 0,
    running: 0,
    done: 0,
    error: 0,
  });
  const [recent, setRecent] = useState<RecentJob[]>([]);
  const [workerRunning, setWorkerRunning] = useState(false);
  const [statusLoading, setStatusLoading] = useState(false);
  const [queueActionBusy, setQueueActionBusy] = useState(false);
  const [clearConfirmOpen, setClearConfirmOpen] = useState(false);

  const autoNestedBoards = useMemo(
    () => scrapeNestedBoards(autoScope.region),
    [autoScope.region],
  );
  const autoPrefixes = useMemo(
    () => scrapeRegionPrefixes(autoScope.region, undefined, autoScope.board),
    [autoScope.region, autoScope.board],
  );

  /** 预览番号：跟随最近完成/进行中的任务 */
  const previewCode = useMemo(() => {
    const latest = recent.find(
      (j) => j.code && j.code.toUpperCase() !== "BATCH",
    );
    return latest?.code?.toUpperCase() || "";
  }, [recent]);

  const refresh = useCallback(async () => {
    setChecking(true);
    try {
      const [hRes, cRes] = await Promise.all([
        fetch("/api/scrape/health", { cache: "no-store" }),
        fetch("/api/scrape/config", { cache: "no-store" }),
      ]);
      const health = await hRes.json();
      setOnline(Boolean(health.ok));
      if (cRes.ok) {
        const cfg = await cRes.json();
        setProxyUrl(String(cfg.proxyUrl || cfg.activeProxy || ""));
        setFlareSolverrUrl(String(cfg.flareSolverrUrl || ""));
        setSources(Array.isArray(cfg.sources) ? cfg.sources : []);
        setUpdatedAt(cfg.updatedAt || null);
        if (cfg.overwriteDefault !== undefined) {
          setOverwriteDefault(Boolean(cfg.overwriteDefault));
        }
        if (cfg.scrapeConcurrency !== undefined) {
          const n = Number(cfg.scrapeConcurrency);
          if (Number.isFinite(n)) {
            setScrapeConcurrency(Math.min(8, Math.max(1, Math.floor(n))));
          }
        }
        if (cfg.autoWorker !== undefined) {
          setAutoWorker(Boolean(cfg.autoWorker));
        }
        if (cfg.monitorEnabled !== undefined) {
          setMonitorEnabled(Boolean(cfg.monitorEnabled));
        }
        if (cfg.monitorIntervalMin !== undefined) {
          setMonitorIntervalMin(Number(cfg.monitorIntervalMin) || 15);
        }
        if (cfg.monitorRunning !== undefined) {
          setMonitorRunning(Boolean(cfg.monitorRunning));
        }
        if (Array.isArray(cfg.monitorTargets)) {
          setMonitorTargets(
            cfg.monitorTargets.map((t: Partial<MonitorTargetUi>) =>
              parseMonitorTarget(t),
            ),
          );
        }
        if (cfg.priorityByKind && typeof cfg.priorityByKind === "object") {
          setPriorityByKind({
            ...EMPTY_PRIORITY,
            ...(cfg.priorityByKind as PriorityByKind),
          });
        }
        if (cfg.autoScope && typeof cfg.autoScope === "object") {
          const s = cfg.autoScope as Partial<ScrapeAutoScope>;
          setAutoScope({
            region: (["日本", "国产", "欧美"].includes(String(s.region))
              ? s.region
              : "日本") as ScrapeAutoScope["region"],
            board: String(s.board || ""),
            prefix: String(s.prefix || "").toUpperCase(),
            code: String(s.code || "").toUpperCase(),
          });
        }
      }
    } catch {
      setOnline(false);
    } finally {
      setChecking(false);
    }
  }, []);

  const refreshStatus = useCallback(async () => {
    setStatusLoading(true);
    try {
      const res = await fetch("/api/scrape/status", { cache: "no-store" });
      const json = await res.json();
      if (!res.ok) throw new Error(json.message || "状态加载失败");
      setQueue(
        json.queue || { pending: 0, running: 0, done: 0, error: 0 },
      );
      setRecent(Array.isArray(json.recent) ? json.recent : []);
      setWorkerRunning(Boolean(json.workerRunning));
      if (json.scrapeConcurrency !== undefined) {
        const n = Number(json.scrapeConcurrency);
        if (Number.isFinite(n) && n >= 1) setScrapeConcurrency(n);
      }
      if (json.activeJobs !== undefined) {
        const n = Number(json.activeJobs);
        setActiveJobs(Number.isFinite(n) ? Math.max(0, n) : 0);
      }
      if (json.autoWorker !== undefined) setAutoWorker(Boolean(json.autoWorker));
      if (json.monitorEnabled !== undefined) {
        setMonitorEnabled(Boolean(json.monitorEnabled));
      }
      if (json.monitorIntervalMin !== undefined) {
        setMonitorIntervalMin(Number(json.monitorIntervalMin) || 15);
      }
      if (json.monitorRunning !== undefined) {
        setMonitorRunning(Boolean(json.monitorRunning));
      }
      if (Array.isArray(json.monitorTargets)) {
        setMonitorTargets(
          json.monitorTargets.map((t: Partial<MonitorTargetUi>) =>
            parseMonitorTarget(t),
          ),
        );
      }
    } catch {
      /* 离线时静默 */
    } finally {
      setStatusLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    if (tab !== "status") return;
    void refreshStatus();
    const id = window.setInterval(() => void refreshStatus(), 4000);
    return () => window.clearInterval(id);
  }, [tab, refreshStatus]);

  useEffect(() => {
    const p = autoScope.prefix.trim();
    if (!p) {
      setAutoScopeCodes([]);
      return;
    }
    let cancelled = false;
    void (async () => {
      try {
        const res = await fetch(
          `/api/scrape/prefix-codes?prefix=${encodeURIComponent(p)}&limit=2000`,
          { cache: "no-store" },
        );
        const json = await res.json();
        if (cancelled) return;
        if (!res.ok) {
          setAutoScopeCodes([]);
          return;
        }
        setAutoScopeCodes(
          Array.isArray(json.codes) ? (json.codes as string[]) : [],
        );
      } catch {
        if (!cancelled) setAutoScopeCodes([]);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [autoScope.prefix]);

  useEffect(() => {
    const p = (editTarget?.prefix || "").trim();
    if (!p) {
      setEditScopeCodes([]);
      return;
    }
    let cancelled = false;
    void (async () => {
      try {
        const res = await fetch(
          `/api/scrape/prefix-codes?prefix=${encodeURIComponent(p)}&limit=2000`,
          { cache: "no-store" },
        );
        const json = await res.json();
        if (cancelled) return;
        if (!res.ok) {
          setEditScopeCodes([]);
          return;
        }
        setEditScopeCodes(
          Array.isArray(json.codes) ? (json.codes as string[]) : [],
        );
      } catch {
        if (!cancelled) setEditScopeCodes([]);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [editTarget?.prefix]);

  useEffect(() => {
    if (!previewCode) {
      setResult(null);
      setMetaLoading(false);
      return;
    }
    let cancelled = false;

    const load = async (showLoading: boolean) => {
      // 已有预览时静默刷新，避免整卡骨架闪烁
      if (showLoading) setMetaLoading(true);
      try {
        const res = await fetch(
          `/api/scrape/meta/${encodeURIComponent(previewCode)}`,
          { cache: "no-store" },
        );
        if (cancelled) return;
        if (res.status === 404) {
          setResult((prev) => {
            const next: ScrapePayload = {
              code: previewCode,
              status: "missing",
            };
            return metaEqual(prev, next) ? prev : next;
          });
          return;
        }
        const json = await res.json();
        if (!res.ok) {
          setResult((prev) => {
            const next: ScrapePayload = {
              code: previewCode,
              status: "error",
              error: json.message,
            };
            return metaEqual(prev, next) ? prev : next;
          });
          return;
        }
        setResult((prev) => {
          const next: ScrapePayload = {
            code: json.code || previewCode,
            status: json.status,
            title: json.title,
            title_zh: json.title_zh,
            title_ja: json.title_ja,
            actresses: json.actresses,
            cover_path: json.cover_path,
            error: json.error,
            updated_at: json.updated_at
              ? String(json.updated_at)
              : json.scraped_at
                ? String(json.scraped_at)
                : null,
          };
          return metaEqual(prev, next) ? prev : next;
        });
      } catch {
        if (!cancelled && showLoading) {
          setResult((prev) => {
            const next: ScrapePayload = {
              code: previewCode,
              status: "error",
              error: "加载失败",
            };
            return metaEqual(prev, next) ? prev : next;
          });
        }
      } finally {
        if (!cancelled && showLoading) setMetaLoading(false);
      }
    };

    // 切番号时若已有旧预览，先静默拉新数据，不闪空态
    void load(!result?.code);
    const id =
      tab === "status"
        ? window.setInterval(() => void load(false), 3000)
        : 0;
    return () => {
      cancelled = true;
      if (id) window.clearInterval(id);
    };
    // result?.code 故意不进依赖：避免 setResult 触发重装轮询
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [previewCode, tab]);

  const saveProxy = async () => {
    setProxySaving(true);
    try {
      const res = await fetch("/api/scrape/config", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ proxyUrl: proxyUrl.trim() }),
      });
      const json = await res.json();
      if (!res.ok) throw new Error(json.error || json.message || "保存失败");
      setProxyUrl(String(json.proxyUrl || ""));
      Toast.success(json.proxyUrl ? "已保存" : "已清除");
      await refresh();
    } catch (err) {
      Toast.error(err instanceof Error ? err.message : "保存失败");
    } finally {
      setProxySaving(false);
    }
  };

  const saveFlareSolverr = async () => {
    setFlareSaving(true);
    try {
      const res = await fetch("/api/scrape/config", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ flareSolverrUrl: flareSolverrUrl.trim() }),
      });
      const json = await res.json();
      if (!res.ok) throw new Error(json.error || json.message || "保存失败");
      setFlareSolverrUrl(String(json.flareSolverrUrl || ""));
      Toast.success(
        json.flareSolverrUrl
          ? "FlareSolverr 已保存"
          : "已清除 FlareSolverr",
      );
      await refresh();
    } catch (err) {
      Toast.error(err instanceof Error ? err.message : "保存失败");
    } finally {
      setFlareSaving(false);
    }
  };

  const saveOptions = async (patch: {
    overwriteDefault?: boolean;
    scrapeConcurrency?: number;
    autoWorker?: boolean;
    autoScope?: ScrapeAutoScope;
    monitorEnabled?: boolean;
    monitorIntervalMin?: number;
    monitorPrefixes?: string[];
    monitorTargets?: MonitorTargetUi[];
    priorityByKind?: PriorityByKind;
  }) => {
    setOptionSaving(true);
    try {
      const res = await fetch("/api/scrape/config", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(patch),
      });
      const json = await res.json();
      if (!res.ok) throw new Error(json.error || json.message || "保存失败");
      if (json.overwriteDefault !== undefined) {
        setOverwriteDefault(Boolean(json.overwriteDefault));
      }
      if (json.scrapeConcurrency !== undefined) {
        const n = Number(json.scrapeConcurrency);
        if (Number.isFinite(n)) {
          setScrapeConcurrency(Math.min(8, Math.max(1, Math.floor(n))));
        }
      }
      if (json.autoWorker !== undefined) {
        setAutoWorker(Boolean(json.autoWorker));
      }
      if (json.monitorEnabled !== undefined) {
        setMonitorEnabled(Boolean(json.monitorEnabled));
      }
      if (json.monitorIntervalMin !== undefined) {
        setMonitorIntervalMin(Number(json.monitorIntervalMin) || 15);
      }
      if (json.monitorRunning !== undefined) {
        setMonitorRunning(Boolean(json.monitorRunning));
      }
      if (Array.isArray(json.monitorTargets)) {
        setMonitorTargets(
          json.monitorTargets.map((t: Partial<MonitorTargetUi>) =>
            parseMonitorTarget(t),
          ),
        );
      }
      if (json.priorityByKind && typeof json.priorityByKind === "object") {
        setPriorityByKind({
          ...EMPTY_PRIORITY,
          ...(json.priorityByKind as PriorityByKind),
        });
      }
      if (json.autoScope && typeof json.autoScope === "object") {
        const s = json.autoScope as Partial<ScrapeAutoScope>;
        setAutoScope({
          region: (["日本", "国产", "欧美"].includes(String(s.region))
            ? s.region
            : "日本") as ScrapeAutoScope["region"],
          board: String(s.board || ""),
          prefix: String(s.prefix || "").toUpperCase(),
          code: String(s.code || "").toUpperCase(),
        });
      }
      if (json.workerRunning !== undefined) {
        setWorkerRunning(Boolean(json.workerRunning));
      }
      return true;
    } catch (err) {
      Toast.error(err instanceof Error ? err.message : "保存失败");
      await refresh();
      return false;
    } finally {
      setOptionSaving(false);
    }
  };

  const persistMonitorTargets = async (targets: MonitorTargetUi[]) => {
    const resolved = targets.map((t) => withResolvedPrefixes(t));
    setMonitorTargets(resolved);
    return saveOptions({
      monitorTargets: resolved,
      monitorPrefixes: resolved.flatMap((t) => t.prefixes),
      monitorEnabled,
      monitorIntervalMin,
      autoWorker: monitorEnabled ? true : undefined,
    });
  };

  const enqueueByScope = async (
    scope: ScrapeAutoScope,
    overwrite: boolean,
  ): Promise<boolean> => {
    setAutoEnqueueBusy(true);
    try {
      const res = await fetch("/api/scrape/enqueue-scope", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...scope, overwrite }),
      });
      const json = await res.json();
      if (!res.ok) throw new Error(json.message || "入队失败");
      const n = Number(json.enqueued || 0);
      const skip = Number(json.skipped || 0);
      const total = Number(json.codes || 0);
      Toast.success(
        total
          ? `已入队 ${n}${skip ? ` · 跳过 ${skip}` : ""}${overwrite ? " · 全量覆盖" : " · 仅缺数据"}`
          : "该板块下暂无番号",
      );
      void refreshStatus();
      return true;
    } catch (err) {
      Toast.error(err instanceof Error ? err.message : "入队失败");
      return false;
    } finally {
      setAutoEnqueueBusy(false);
    }
  };

  const stopCrawl = async () => {
    setQueueActionBusy(true);
    try {
      const res = await fetch("/api/scrape/worker?action=stop", {
        method: "POST",
      });
      const json = await res.json();
      if (!res.ok) throw new Error(json.message || json.error || "停止失败");
      setWorkerRunning(Boolean(json.workerRunning));
      setAutoWorker(Boolean(json.autoWorker));
      Toast.success(json.message || "已停止爬虫");
      void refreshStatus();
    } catch (err) {
      Toast.error(err instanceof Error ? err.message : "停止失败");
    } finally {
      setQueueActionBusy(false);
    }
  };

  const startCrawl = async () => {
    setQueueActionBusy(true);
    try {
      const res = await fetch("/api/scrape/worker?action=start", {
        method: "POST",
      });
      const json = await res.json();
      if (!res.ok) throw new Error(json.message || json.error || "启动失败");
      setWorkerRunning(Boolean(json.workerRunning));
      setAutoWorker(Boolean(json.autoWorker));
      Toast.success(json.message || "已启动爬虫");
      void refreshStatus();
    } catch (err) {
      Toast.error(err instanceof Error ? err.message : "启动失败");
    } finally {
      setQueueActionBusy(false);
    }
  };

  const clearQueueAction = async (includeHistory: boolean) => {
    setClearConfirmOpen(false);
    setQueueActionBusy(true);
    try {
      const res = await fetch("/api/scrape/queue/clear", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ history: includeHistory }),
      });
      const json = await res.json();
      if (!res.ok) throw new Error(json.message || json.error || "清空失败");
      if (json.queue) {
        setQueue(
          json.queue || { pending: 0, running: 0, done: 0, error: 0 },
        );
      }
      Toast.success(json.message || "已清空队列");
      void refreshStatus();
    } catch (err) {
      Toast.error(err instanceof Error ? err.message : "清空失败");
    } finally {
      setQueueActionBusy(false);
    }
  };

  const retryFailedAction = async () => {
    setQueueActionBusy(true);
    try {
      const res = await fetch("/api/scrape/queue/retry-failed", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
      });
      const json = await res.json();
      if (!res.ok) throw new Error(json.message || json.error || "重试失败");
      if (json.queue) {
        setQueue(
          json.queue || { pending: 0, running: 0, done: 0, error: 0 },
        );
      }
      if (json.workerRunning !== undefined) {
        setWorkerRunning(Boolean(json.workerRunning));
      }
      Toast.success(json.message || "已重试失败任务");
      void refreshStatus();
    } catch (err) {
      Toast.error(err instanceof Error ? err.message : "重试失败");
    } finally {
      setQueueActionBusy(false);
    }
  };

  const patchAutoScope = (patch: Partial<ScrapeAutoScope>) => {
    setAutoScope((prev) => {
      const next: ScrapeAutoScope = { ...prev, ...patch };
      if (patch.region !== undefined) {
        next.board = "";
        next.prefix = "";
        next.code = "";
      } else if (patch.board !== undefined) {
        next.prefix = "";
        next.code = "";
      } else if (patch.prefix !== undefined) {
        next.code = "";
      }
      return next;
    });
  };

  const patchEditTarget = (
    patch: Partial<ScrapeAutoScope & { mode: CodeKind }>,
  ) => {
    setEditTarget((prev) => {
      if (!prev) return prev;
      const next: MonitorTargetUi = {
        ...prev,
        ...patch,
        prefixes: prev.prefixes,
      };
      if (patch.region !== undefined) {
        next.board = "";
        next.prefix = "";
        next.code = "";
      } else if (patch.board !== undefined) {
        next.prefix = "";
        next.code = "";
      } else if (patch.prefix !== undefined) {
        next.code = "";
      }
      return withResolvedPrefixes(next);
    });
  };

  const movePrioritySource = (kind: CodeKind, index: number, dir: -1 | 1) => {
    setPriorityByKind((prev) => {
      const list = [...(prev[kind]?.cover || [])];
      const j = index + dir;
      if (j < 0 || j >= list.length) return prev;
      const tmp = list[index];
      list[index] = list[j];
      list[j] = tmp;
      return {
        ...prev,
        [kind]: { meta: [...list], cover: list },
      };
    });
  };

  const removePrioritySource = (kind: CodeKind, id: string) => {
    setPriorityByKind((prev) => {
      const list = (prev[kind]?.cover || []).filter((x) => x !== id);
      return {
        ...prev,
        [kind]: { meta: [...list], cover: list },
      };
    });
  };

  const addPrioritySource = (kind: CodeKind, id: string) => {
    if (!id) return;
    setPriorityByKind((prev) => {
      const list = prev[kind]?.cover || [];
      if (list.includes(id)) return prev;
      const next = [...list, id];
      return {
        ...prev,
        [kind]: { meta: [...next], cover: next },
      };
    });
  };

  const savePriority = async () => {
    setPrioritySaving(true);
    try {
      const ok = await saveOptions({ priorityByKind });
      if (ok) Toast.success("优先级已保存");
    } finally {
      setPrioritySaving(false);
    }
  };

  const sourceName = (id: string) =>
    sources.find((s) => s.id === id)?.name || id;

  const editNestedBoards = useMemo(
    () => (editTarget ? scrapeNestedBoards(editTarget.region) : []),
    [editTarget],
  );
  const editPrefixes = useMemo(
    () =>
      editTarget
        ? scrapeRegionPrefixes(editTarget.region, undefined, editTarget.board)
        : [],
    [editTarget],
  );

  const toggleSource = async (id: string, enabled: boolean) => {
    setSources((prev) =>
      prev.map((s) => (s.id === id ? { ...s, enabled } : s)),
    );
    try {
      const res = await fetch(`/api/scrape/sources/${encodeURIComponent(id)}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled }),
      });
      const json = await res.json();
      if (!res.ok) throw new Error(json.error || json.message || "更新失败");
      if (Array.isArray(json.sources)) setSources(json.sources);
      setUpdatedAt(json.updatedAt || null);
    } catch (err) {
      Toast.error(err instanceof Error ? err.message : "更新失败");
      await refresh();
    }
  };

  const testSources = async (id?: string) => {
    setTesting(true);
    try {
      const res = await fetch("/api/scrape/sources/test", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(id ? { id } : {}),
      });
      const json = await res.json();
      if (!res.ok) throw new Error(json.message || "测试失败");
      const next = Array.isArray(json.sources)
        ? (json.sources as SourceCard[])
        : [];
      if (next.length) setSources(next);
      setUpdatedAt(json.updatedAt || null);

      if (id) {
        const hit = next.find((s) => s.id === id);
        if (hit?.status === "ok") {
          Toast.success(`${hit.name} 连通正常`);
        } else if (hit?.status === "error") {
          Toast.error(`${hit.name} 失败：${zhProbeError(hit.lastError)}`);
        } else {
          Toast.error("未拿到测试结果");
        }
      } else {
        const ok = next.filter((s) => s.status === "ok").length;
        const bad = next.filter((s) => s.status === "error").length;
        const msg = `通过 ${ok} · 失败 ${bad}`;
        if (bad > 0) Toast.error(msg);
        else Toast.success(msg);
      }
    } catch (err) {
      Toast.error(err instanceof Error ? err.message : "测试失败");
    } finally {
      setTesting(false);
    }
  };

  const openEdit = (s: SourceCard) => {
    setEditId(s.id);
    setEditUrl(s.url);
    setEditCookie(s.cookie || "");
    setEditUserAgent(s.userAgent || "");
    setEditProxyMode(s.proxyMode || "inherit");
    setEditTimeoutMs(String(s.timeoutMs ?? 0));
    setEditRetry(String(s.retry ?? 1));
    setEditUseFlare(Boolean(s.useFlareSolverr));
  };

  const saveEdit = async () => {
    if (!editId) return;
    setEditSaving(true);
    try {
      const res = await fetch(
        `/api/scrape/sources/${encodeURIComponent(editId)}`,
        {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            baseUrl: editUrl.trim(),
            cookie: editCookie,
            userAgent: editUserAgent,
            proxyMode: editProxyMode,
            timeoutMs: Number(editTimeoutMs) || 0,
            retry: Number(editRetry) || 0,
            useFlareSolverr: editUseFlare,
          }),
        },
      );
      const json = await res.json();
      if (!res.ok) throw new Error(json.error || json.message || "保存失败");
      if (Array.isArray(json.sources)) setSources(json.sources);
      setUpdatedAt(json.updatedAt || null);
      setEditId(null);
      Toast.success("已保存");
    } catch (err) {
      Toast.error(err instanceof Error ? err.message : "保存失败");
    } finally {
      setEditSaving(false);
    }
  };

  return (
    <div className="flex flex-col gap-3">
      <div
        className={`${shell} flex items-center justify-between gap-3 px-4 py-3`}
      >
        <div className="flex min-w-0 items-center gap-2 text-sm">
          <span
            className={
              online
                ? "h-2 w-2 shrink-0 rounded-full bg-emerald-500"
                : online === false
                  ? "h-2 w-2 shrink-0 rounded-full bg-rose-500"
                  : "h-2 w-2 shrink-0 rounded-full bg-gray-300"
            }
          />
          <span className="font-medium text-gray-900 dark:text-white">
            {online ? "刮削服务在线" : online === false ? "刮削服务离线" : "…"}
          </span>
          {workerRunning ? (
            <span className="rounded bg-emerald-50 px-1.5 py-0.5 text-[10px] text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300">
              自动爬取中
            </span>
          ) : autoWorker ? null : (
            <span className="rounded bg-gray-100 px-1.5 py-0.5 text-[10px] text-gray-500 dark:bg-slate-800 dark:text-slate-400">
              自动已关
            </span>
          )}
          {monitorRunning ? (
            <span className="rounded bg-sky-50 px-1.5 py-0.5 text-[10px] text-sky-700 dark:bg-sky-950/40 dark:text-sky-300">
              监控中 · {monitorIntervalMin}分
            </span>
          ) : null}
        </div>
        <Button
          isLoading={checking || statusLoading}
          radius="sm"
          size="sm"
          variant="flat"
          onPress={() => {
            if (tab === "status") {
              // 状态页只软刷队列/预览，不重拉整页配置
              void refreshStatus();
            } else if (tab === "sources") {
              void refresh();
            } else {
              void refresh();
            }
          }}
        >
          刷新
        </Button>
      </div>

      <div className="flex gap-1 rounded-lg border border-gray-200 bg-gray-50 p-1 dark:border-slate-700 dark:bg-slate-800/80">
        {TABS.map((t) => (
          <button
            key={t.key}
            className={clsx(
              "flex-1 rounded-md px-3 py-2 text-sm font-medium transition-colors",
              tab === t.key
                ? "bg-white text-primary shadow-sm dark:bg-slate-900"
                : "text-gray-600 hover:text-gray-900 dark:text-slate-300 dark:hover:text-white",
            )}
            type="button"
            onClick={() => setTab(t.key)}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "basic" ? (
        <div className="flex flex-col gap-3">
          <div className={`${shell} space-y-3 p-4`}>
            <h2 className="text-sm font-semibold text-gray-800 dark:text-slate-100">
              代理
            </h2>
            <div className="flex gap-2">
              <Input
                className="flex-1"
                classNames={{ inputWrapper: inputWrap }}
                placeholder="http://127.0.0.1:7890"
                radius="sm"
                size="sm"
                value={proxyUrl}
                variant="flat"
                onValueChange={setProxyUrl}
              />
              <Button
                color="primary"
                isLoading={proxySaving}
                radius="sm"
                size="sm"
                onPress={() => void saveProxy()}
              >
                保存
              </Button>
            </div>
          </div>

          <div className={`${shell} space-y-3 p-4`}>
            <h2 className="text-sm font-semibold text-gray-800 dark:text-slate-100">
              FlareSolverr（过 Cloudflare）
            </h2>
            <p className="text-[11px] text-gray-400">
              mdc-ng 能刮 javdb/图书馆，靠的就是这个。未配置时这些站会 403。
            </p>
            <div className="flex gap-2">
              <Input
                className="flex-1"
                classNames={{ inputWrapper: inputWrap }}
                placeholder="http://127.0.0.1:8191/v1"
                radius="sm"
                size="sm"
                value={flareSolverrUrl}
                variant="flat"
                onValueChange={setFlareSolverrUrl}
              />
              <Button
                color="primary"
                isLoading={flareSaving}
                radius="sm"
                size="sm"
                onPress={() => void saveFlareSolverr()}
              >
                保存
              </Button>
            </div>
          </div>

          <div className={`${shell} space-y-4 p-4`}>
            <h2 className="text-sm font-semibold text-gray-800 dark:text-slate-100">
              默认行为
            </h2>
            <label className="flex cursor-pointer items-center justify-between gap-3 text-sm text-gray-700 dark:text-slate-200">
              <span>
                覆盖模式
                <span className="mt-0.5 block text-xs font-normal text-gray-400">
                  开：全量覆盖已有数据；关：仅刮尚无数据的番号。始终只保留最新一份。
                </span>
              </span>
              <Switch
                aria-label="覆盖模式"
                isDisabled={optionSaving}
                isSelected={overwriteDefault}
                size="sm"
                onValueChange={(v) => {
                  setOverwriteDefault(v);
                  void saveOptions({ overwriteDefault: v });
                }}
              />
            </label>

            <div className="flex items-center justify-between gap-3 text-sm text-gray-700 dark:text-slate-200">
              <span>
                刮削并发
                <span className="mt-0.5 block text-xs font-normal text-gray-400">
                  同时刮几条；越大越快，也更容易被站点限流
                </span>
              </span>
              <Select
                aria-label="刮削并发"
                className="w-24"
                classNames={{ trigger: inputWrap }}
                isDisabled={optionSaving}
                items={[...CONCURRENCY_OPTIONS]}
                radius="sm"
                selectedKeys={new Set([String(scrapeConcurrency)])}
                size="sm"
                variant="flat"
                onSelectionChange={(keys) => {
                  const k = Array.from(keys)[0];
                  if (typeof k !== "string") return;
                  const n = Number(k) || 3;
                  setScrapeConcurrency(n);
                  void (async () => {
                    const ok = await saveOptions({ scrapeConcurrency: n });
                    if (ok) Toast.success(`并发已设为 ${n}`);
                  })();
                }}
              >
                {(item) => (
                  <SelectItem key={item.key} textValue={item.label}>
                    {item.label}
                  </SelectItem>
                )}
              </Select>
            </div>

            <label className="flex cursor-pointer items-center justify-between gap-3 text-sm text-gray-700 dark:text-slate-200">
              <span>
                自动监控
                <span className="mt-0.5 block text-xs font-normal text-gray-400">
                  开启时自动监控下面目录，入队（没有数据的），并后台刮削
                </span>
              </span>
              <Switch
                aria-label="自动监控"
                isDisabled={optionSaving}
                isSelected={monitorEnabled}
                size="sm"
                onValueChange={(v) => {
                  void (async () => {
                    const ok = await saveOptions({
                      monitorEnabled: v,
                      monitorIntervalMin,
                      monitorTargets,
                      monitorPrefixes: monitorTargets.flatMap(
                        (t) => t.prefixes,
                      ),
                      // 开监控时一并开 worker，保证入队后能刮
                      autoWorker: v ? true : false,
                    });
                    if (!ok) return;
                    Toast.success(
                      v
                        ? `监控已开 · ${monitorIntervalMin} 分钟补缺入队`
                        : "监控已关",
                    );
                  })();
                }}
              />
            </label>
          </div>

          <div className={`${shell} space-y-3 p-4`}>
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <h2 className="text-sm font-semibold text-gray-800 dark:text-slate-100">
                  监控板块
                </h2>
                <button
                  aria-label="添加监控板块"
                  className="flex h-6 w-6 items-center justify-center rounded-md bg-gray-900 text-sm text-white dark:bg-white dark:text-gray-900"
                  type="button"
                  onClick={() => {
                    const created = withResolvedPrefixes({
                      id: newMonitorId(),
                      region: "日本",
                      board: "",
                      prefix: "",
                      code: "",
                      mode: "av",
                    });
                    setEditTarget(created);
                  }}
                >
                  +
                </button>
              </div>
              <Select
                className="w-32"
                classNames={{ trigger: inputWrap }}
                items={[...MONITOR_INTERVALS]}
                radius="sm"
                selectedKeys={new Set([String(monitorIntervalMin)])}
                size="sm"
                variant="flat"
                onSelectionChange={(keys) => {
                  const k = Array.from(keys)[0];
                  if (typeof k !== "string") return;
                  const mins = Number(k) || 15;
                  setMonitorIntervalMin(mins);
                  void saveOptions({
                    monitorIntervalMin: mins,
                    monitorEnabled,
                    monitorTargets,
                    monitorPrefixes: monitorTargets.flatMap((t) => t.prefixes),
                  });
                }}
              >
                {(item) => (
                  <SelectItem key={item.key} textValue={item.label}>
                    {item.label}
                  </SelectItem>
                )}
              </Select>
            </div>
            <p className="text-xs text-gray-400">
              定时检查下列板块，发现未刮削番号自动入队（只补缺）
              {monitorEnabled
                ? monitorRunning
                  ? " · 监控运行中"
                  : " · 已开启"
                : " · 未开启（上方开关）"}
            </p>

            {monitorTargets.length === 0 ? (
              <p className="rounded-md border border-dashed border-gray-200 px-3 py-6 text-center text-xs text-gray-400 dark:border-slate-700">
                点击 + 添加要监控的板块
              </p>
            ) : (
              <div className="grid gap-3 sm:grid-cols-2">
                {monitorTargets.map((t) => (
                  <div
                    key={t.id}
                    className="space-y-2 rounded-lg border border-gray-200 p-3 dark:border-slate-700"
                  >
                    <div className="flex gap-2">
                      <Input
                        className="flex-1"
                        classNames={{ inputWrapper: inputWrap }}
                        isReadOnly
                        radius="sm"
                        size="sm"
                        value={scopePathLabel(t)}
                        variant="flat"
                      />
                    </div>
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-[11px] text-gray-400">
                        {kindLabel(t.mode)}
                      </span>
                      <div className="flex items-center gap-2">
                        <button
                          className="text-xs text-gray-500 hover:text-gray-800 dark:hover:text-white"
                          type="button"
                          onClick={() => setEditTarget({ ...t })}
                        >
                          设置
                        </button>
                        <Button
                          className="bg-gray-900 text-white dark:bg-white dark:text-gray-900"
                          radius="sm"
                          size="sm"
                          onPress={() => {
                            const next = monitorTargets.filter(
                              (x) => x.id !== t.id,
                            );
                            void persistMonitorTargets(next);
                          }}
                        >
                          移除
                        </Button>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className={`${shell} space-y-4 p-4`}>
            <h2 className="text-sm font-semibold text-gray-800 dark:text-slate-100">
              手动爬取板块入队
            </h2>
            <div className="grid gap-2 sm:grid-cols-2">
              <Select
                classNames={{ trigger: inputWrap }}
                items={SCRAPE_AUTO_REGIONS.map((r) => ({
                  key: r,
                  label: r,
                }))}
                label="板块"
                radius="sm"
                selectedKeys={new Set([autoScope.region])}
                size="sm"
                variant="flat"
                onSelectionChange={(keys) => {
                  const k = Array.from(keys)[0];
                  if (typeof k === "string") {
                    patchAutoScope({
                      region: k as ScrapeAutoScope["region"],
                    });
                  }
                }}
              >
                {(item) => (
                  <SelectItem key={item.key} textValue={item.label}>
                    {item.label}
                  </SelectItem>
                )}
              </Select>

              {autoNestedBoards.length > 0 ? (
                <Select
                  classNames={{ trigger: inputWrap }}
                  items={[
                    { key: ALL_BOARD, label: "全部" },
                    ...autoNestedBoards.map((b) => ({
                      key: b.prefix,
                      label: b.label,
                    })),
                  ]}
                  label="二级板块"
                  radius="sm"
                  selectedKeys={new Set([autoScope.board || ALL_BOARD])}
                  size="sm"
                  variant="flat"
                  onSelectionChange={(keys) => {
                    const k = Array.from(keys)[0];
                    if (typeof k !== "string") return;
                    patchAutoScope({
                      board: k === ALL_BOARD ? "" : k,
                    });
                  }}
                >
                  {(item) => (
                    <SelectItem key={item.key} textValue={item.label}>
                      {item.label}
                    </SelectItem>
                  )}
                </Select>
              ) : null}

              <Select
                classNames={{ trigger: inputWrap }}
                items={[
                  { key: ALL_PREFIX, label: "全部厂牌" },
                  ...autoPrefixes.map((p) => ({
                    key: p.prefix,
                    label: p.label,
                  })),
                ]}
                label="厂牌"
                radius="sm"
                selectedKeys={new Set([autoScope.prefix || ALL_PREFIX])}
                size="sm"
                variant="flat"
                onSelectionChange={(keys) => {
                  const k = Array.from(keys)[0];
                  if (typeof k !== "string") return;
                  patchAutoScope({
                    prefix: k === ALL_PREFIX ? "" : k,
                  });
                }}
              >
                {(item) => (
                  <SelectItem key={item.key} textValue={item.label}>
                    {item.label}
                  </SelectItem>
                )}
              </Select>

              <Select
                classNames={{ trigger: inputWrap }}
                isDisabled={!autoScope.prefix}
                items={[
                  { key: ALL_CODES, label: "全部番号" },
                  ...autoScopeCodes.map((c) => ({
                    key: c,
                    label: c,
                  })),
                ]}
                label="番号"
                placeholder={autoScope.prefix ? "全部番号" : "先选厂牌"}
                radius="sm"
                selectedKeys={new Set([autoScope.code || ALL_CODES])}
                size="sm"
                variant="flat"
                onSelectionChange={(keys) => {
                  const k = Array.from(keys)[0];
                  if (typeof k !== "string") return;
                  patchAutoScope({
                    code: k === ALL_CODES ? "" : k,
                  });
                }}
              >
                {(item) => (
                  <SelectItem key={item.key} textValue={item.label}>
                    {item.label}
                  </SelectItem>
                )}
              </Select>
            </div>

            <div className="flex justify-end">
              <Button
                color="primary"
                isLoading={autoEnqueueBusy || optionSaving}
                radius="sm"
                size="sm"
                onPress={() => {
                  void (async () => {
                    const ok = await saveOptions({
                      autoWorker: true,
                      autoScope,
                    });
                    if (!ok) return;
                    await enqueueByScope(autoScope, overwriteDefault);
                  })();
                }}
              >
                按板块入队
              </Button>
            </div>
          </div>
        </div>
      ) : null}

      <Modal
        isOpen={Boolean(editTarget)}
        size="md"
        onClose={() => setEditTarget(null)}
      >
        <ModalContent>
          {(onClose) => (
            <>
              <ModalHeader className="text-sm">设置监控板块</ModalHeader>
              <ModalBody className="gap-3">
                {editTarget ? (
                  <div className="grid gap-2 sm:grid-cols-2">
                    <Select
                      classNames={{ trigger: inputWrap }}
                      items={SCRAPE_AUTO_REGIONS.map((r) => ({
                        key: r,
                        label: r,
                      }))}
                      label="板块"
                      radius="sm"
                      selectedKeys={new Set([editTarget.region])}
                      size="sm"
                      variant="flat"
                      onSelectionChange={(keys) => {
                        const k = Array.from(keys)[0];
                        if (typeof k === "string") {
                          patchEditTarget({
                            region: k as ScrapeAutoScope["region"],
                          });
                        }
                      }}
                    >
                      {(item) => (
                        <SelectItem key={item.key} textValue={item.label}>
                          {item.label}
                        </SelectItem>
                      )}
                    </Select>
                    {editNestedBoards.length > 0 ? (
                      <Select
                        classNames={{ trigger: inputWrap }}
                        items={[
                          { key: ALL_BOARD, label: "全部" },
                          ...editNestedBoards.map((b) => ({
                            key: b.prefix,
                            label: b.label,
                          })),
                        ]}
                        label="二级板块"
                        radius="sm"
                        selectedKeys={
                          new Set([editTarget.board || ALL_BOARD])
                        }
                        size="sm"
                        variant="flat"
                        onSelectionChange={(keys) => {
                          const k = Array.from(keys)[0];
                          if (typeof k !== "string") return;
                          patchEditTarget({
                            board: k === ALL_BOARD ? "" : k,
                          });
                        }}
                      >
                        {(item) => (
                          <SelectItem key={item.key} textValue={item.label}>
                            {item.label}
                          </SelectItem>
                        )}
                      </Select>
                    ) : null}
                    <Select
                      classNames={{ trigger: inputWrap }}
                      items={[
                        { key: ALL_PREFIX, label: "全部厂牌" },
                        ...editPrefixes.map((p) => ({
                          key: p.prefix,
                          label: p.label,
                        })),
                      ]}
                      label="厂牌"
                      radius="sm"
                      selectedKeys={
                        new Set([editTarget.prefix || ALL_PREFIX])
                      }
                      size="sm"
                      variant="flat"
                      onSelectionChange={(keys) => {
                        const k = Array.from(keys)[0];
                        if (typeof k !== "string") return;
                        patchEditTarget({
                          prefix: k === ALL_PREFIX ? "" : k,
                        });
                      }}
                    >
                      {(item) => (
                        <SelectItem key={item.key} textValue={item.label}>
                          {item.label}
                        </SelectItem>
                      )}
                    </Select>
                    <Select
                      classNames={{ trigger: inputWrap }}
                      isDisabled={!editTarget.prefix}
                      items={[
                        { key: ALL_CODES, label: "全部番号" },
                        ...editScopeCodes.map((c) => ({
                          key: c,
                          label: c,
                        })),
                      ]}
                      label="番号"
                      radius="sm"
                      selectedKeys={
                        new Set([editTarget.code || ALL_CODES])
                      }
                      size="sm"
                      variant="flat"
                      onSelectionChange={(keys) => {
                        const k = Array.from(keys)[0];
                        if (typeof k !== "string") return;
                        patchEditTarget({
                          code: k === ALL_CODES ? "" : k,
                        });
                      }}
                    >
                      {(item) => (
                        <SelectItem key={item.key} textValue={item.label}>
                          {item.label}
                        </SelectItem>
                      )}
                    </Select>
                    <Select
                      className="sm:col-span-2"
                      classNames={{ trigger: inputWrap }}
                      items={SCRAPE_KIND_OPTIONS.map((m) => ({
                        key: m.key,
                        label: m.label,
                      }))}
                      label="模式"
                      radius="sm"
                      selectedKeys={new Set([editTarget.mode || "av"])}
                      size="sm"
                      variant="flat"
                      onSelectionChange={(keys) => {
                        const k = Array.from(keys)[0];
                        if (
                          typeof k === "string" &&
                          SCRAPE_KIND_OPTIONS.some((o) => o.key === k)
                        ) {
                          patchEditTarget({ mode: k as CodeKind });
                        }
                      }}
                    >
                      {(item) => (
                        <SelectItem key={item.key} textValue={item.label}>
                          {item.label}
                        </SelectItem>
                      )}
                    </Select>
                    <p className="sm:col-span-2 text-[11px] text-gray-400">
                      按类型走数据源页对应优先级；刮削默认封面优先。
                    </p>
                  </div>
                ) : null}
              </ModalBody>
              <ModalFooter>
                <Button radius="sm" size="sm" variant="flat" onPress={onClose}>
                  取消
                </Button>
                <Button
                  color="primary"
                  isLoading={optionSaving}
                  radius="sm"
                  size="sm"
                  onPress={() => {
                    if (!editTarget) return;
                    void (async () => {
                      const resolved = withResolvedPrefixes(editTarget);
                      const exists = monitorTargets.some(
                        (x) => x.id === resolved.id,
                      );
                      const next = exists
                        ? monitorTargets.map((x) =>
                            x.id === resolved.id ? resolved : x,
                          )
                        : [...monitorTargets, resolved];
                      const ok = await persistMonitorTargets(next);
                      if (!ok) return;
                      setEditTarget(null);
                      Toast.success("监控板块已保存");
                    })();
                  }}
                >
                  保存
                </Button>
              </ModalFooter>
            </>
          )}
        </ModalContent>
      </Modal>

      <Modal
        isOpen={clearConfirmOpen}
        size="sm"
        onClose={() => setClearConfirmOpen(false)}
      >
        <ModalContent>
          {(onClose) => (
            <>
              <ModalHeader className="text-sm">确认清空队列</ModalHeader>
              <ModalBody>
                <p className="text-sm text-gray-600 dark:text-slate-300">
                  将清空等待中的任务，并一并清除已完成 / 失败的历史记录。此操作不可撤销。
                </p>
              </ModalBody>
              <ModalFooter>
                <Button radius="sm" size="sm" variant="light" onPress={onClose}>
                  取消
                </Button>
                <Button
                  color="danger"
                  isLoading={queueActionBusy}
                  radius="sm"
                  size="sm"
                  onPress={() => void clearQueueAction(true)}
                >
                  确认清空
                </Button>
              </ModalFooter>
            </>
          )}
        </ModalContent>
      </Modal>

      {tab === "status" ? (
        <div className="flex flex-col gap-3">
          <div className={`${shell} p-4`}>
            <div className="mb-3 flex items-center justify-between gap-2">
              <div className="flex min-w-0 items-center gap-2">
                <h2 className="text-sm font-semibold text-gray-800 dark:text-slate-100">
                  队列
                </h2>
                <span className="text-[11px] text-gray-400">
                  {workerRunning ? "worker 运行中" : "worker 已停"}
                </span>
              </div>
              <div className="flex shrink-0 gap-2">
                {workerRunning ? (
                  <Button
                    color="danger"
                    isLoading={queueActionBusy}
                    radius="sm"
                    size="sm"
                    variant="flat"
                    onPress={() => void stopCrawl()}
                  >
                    停止爬虫
                  </Button>
                ) : (
                  <Button
                    color="primary"
                    isLoading={queueActionBusy}
                    radius="sm"
                    size="sm"
                    variant="flat"
                    onPress={() => void startCrawl()}
                  >
                    启动爬虫
                  </Button>
                )}
                <Button
                  color="warning"
                  isDisabled={queue.error <= 0}
                  isLoading={queueActionBusy}
                  radius="sm"
                  size="sm"
                  variant="flat"
                  onPress={() => void retryFailedAction()}
                >
                  失败重试
                </Button>
                <Button
                  isLoading={queueActionBusy}
                  radius="sm"
                  size="sm"
                  variant="bordered"
                  onPress={() => setClearConfirmOpen(true)}
                >
                  清空队列
                </Button>
              </div>
            </div>
            <div className="grid grid-cols-4 gap-2 text-center">
              {(
                [
                  {
                    key: "pending",
                    label: "等待",
                    n: queue.pending,
                    color: "text-amber-600",
                  },
                  {
                    key: "running",
                    label: "进行中",
                    n: `${activeJobs}/${scrapeConcurrency}`,
                    color:
                      activeJobs >= scrapeConcurrency
                        ? "text-orange-600"
                        : "text-sky-600",
                    sub:
                      queue.running > activeJobs
                        ? `队列 ${queue.running}`
                        : "并行/上限",
                  },
                  {
                    key: "done",
                    label: "完成",
                    n: queue.done,
                    color: "text-emerald-600",
                  },
                  {
                    key: "error",
                    label: "失败",
                    n: queue.error,
                    color: "text-rose-600",
                  },
                ] as const
              ).map((item) => (
                <div
                  key={item.key}
                  className="rounded-md bg-gray-50 px-2 py-2 dark:bg-slate-800/80"
                >
                  <p className={`text-lg font-semibold ${item.color}`}>
                    {item.n}
                  </p>
                  <p className="text-[11px] text-gray-400">{item.label}</p>
                  {"sub" in item && item.sub ? (
                    <p className="mt-0.5 text-[10px] text-sky-500/90">{item.sub}</p>
                  ) : null}
                </div>
              ))}
            </div>
          </div>

          <div className={`${shell} space-y-3 p-4`}>
            <h2 className="text-sm font-semibold text-gray-800 dark:text-slate-100">
              最新预览
            </h2>
            <MetaPreviewCard
              emptyHint="按板块入队后，这里显示最新刮削的封面 / 片名 / 女优"
              loading={metaLoading && !result?.code}
              payload={result}
            />
          </div>
        </div>
      ) : null}

      {tab === "sources" ? (
        <div className="space-y-4">
          <div className={`${shell} space-y-3 p-4`}>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <h2 className="text-sm font-semibold text-gray-800 dark:text-slate-100">
                  优先级设置（全局）
                </h2>
                <p className="mt-0.5 text-xs text-gray-500 dark:text-slate-400">
                  将番号类型与刮削源匹配。进行多源数据聚合时，最终结果根据优先级进行选取
                </p>
              </div>
              <Button
                color="primary"
                isLoading={prioritySaving || optionSaving}
                radius="sm"
                size="sm"
                onPress={() => void savePriority()}
              >
                保存优先级
              </Button>
            </div>

            <div className="space-y-2">
              {PRIORITY_KIND_ROWS.map((row) => {
                const list = priorityByKind[row.key]?.cover || [];
                const used = new Set(list);
                const addable = sources
                  .filter((s) => !used.has(s.id))
                  .map((s) => ({ key: s.id, label: s.name }));
                return (
                  <div
                    key={row.key}
                    className="flex flex-col gap-2 rounded-md border border-gray-100 px-3 py-2 dark:border-slate-800 sm:flex-row sm:items-center"
                  >
                    <div className="w-24 shrink-0 text-xs font-medium text-gray-600 dark:text-slate-300">
                      {row.label}
                    </div>
                    <div className="flex min-w-0 flex-1 flex-wrap items-center gap-1.5">
                      {list.length === 0 ? (
                        <span className="text-[11px] text-gray-400">
                          暂无源
                        </span>
                      ) : (
                        list.map((id, idx) => (
                          <span
                            key={`${row.key}-${id}`}
                            className="inline-flex items-center gap-0.5 rounded border border-gray-200 bg-gray-50 px-1.5 py-0.5 text-[11px] text-gray-700 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200"
                          >
                            <button
                              className="px-0.5 text-gray-400 hover:text-gray-700 disabled:opacity-30"
                              disabled={idx === 0}
                              type="button"
                              onClick={() =>
                                movePrioritySource(row.key, idx, -1)
                              }
                            >
                              ‹
                            </button>
                            <span>{sourceName(id)}</span>
                            <button
                              className="px-0.5 text-gray-400 hover:text-gray-700 disabled:opacity-30"
                              disabled={idx === list.length - 1}
                              type="button"
                              onClick={() =>
                                movePrioritySource(row.key, idx, 1)
                              }
                            >
                              ›
                            </button>
                            <button
                              className="ml-0.5 text-rose-400 hover:text-rose-600"
                              type="button"
                              onClick={() =>
                                removePrioritySource(row.key, id)
                              }
                            >
                              ×
                            </button>
                          </span>
                        ))
                      )}
                      {addable.length > 0 ? (
                        <Select
                          aria-label={`添加源到${row.label}`}
                          className="w-28"
                          classNames={{ trigger: inputWrap }}
                          items={addable}
                          placeholder="+"
                          radius="sm"
                          size="sm"
                          variant="flat"
                          onSelectionChange={(keys) => {
                            const k = Array.from(keys)[0];
                            if (typeof k === "string") {
                              addPrioritySource(row.key, k);
                            }
                          }}
                        >
                          {(item) => (
                            <SelectItem key={item.key} textValue={item.label}>
                              {item.label}
                            </SelectItem>
                          )}
                        </Select>
                      ) : null}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          <div>
            <div className="mb-2 flex items-center justify-between gap-2">
              <h2 className="text-sm font-semibold text-gray-800 dark:text-slate-100">
                数据源
              </h2>
              <div className="flex items-center gap-2">
                {updatedAt ? (
                  <span className="text-[11px] text-gray-400">
                    {relativeTime(updatedAt)}
                  </span>
                ) : null}
                <Button
                  isLoading={testing}
                  radius="sm"
                  size="sm"
                  variant="flat"
                  onPress={() => void testSources()}
                >
                  测试全部
                </Button>
              </div>
            </div>
            <p className="mb-3 text-xs text-gray-500 dark:text-slate-400">
              开关控制是否参与刮削；点击卡片可改站点 URL。上方可配置各类型优先级。
            </p>

            <div className="space-y-3">
              {(["av", "fc2", "chinese", "other"] as const).map((g) => {
                const list = sources.filter((s) => (s.group || "other") === g);
                if (!list.length) return null;
                return (
                  <div key={g}>
                    <p className="mb-1.5 text-[11px] font-medium text-gray-400">
                      {GROUP_LABEL[g]}
                    </p>
                    <div className="grid grid-cols-2 gap-2 md:grid-cols-3">
                      {list.map((s) => (
                        <button
                          key={s.id}
                          className={`${shell} flex w-full items-start gap-2 p-3 text-left transition hover:border-primary/40`}
                          type="button"
                          onClick={() => openEdit(s)}
                        >
                          <div className="min-w-0 flex-1">
                            <div className="flex items-center gap-1.5">
                              <span
                                className={
                                  s.status === "ok"
                                    ? "h-2 w-2 shrink-0 rounded-full bg-emerald-500"
                                    : s.status === "error"
                                      ? "h-2 w-2 shrink-0 rounded-full bg-rose-500"
                                      : "h-2 w-2 shrink-0 rounded-full bg-gray-300"
                                }
                              />
                              <span className="truncate text-sm font-semibold text-gray-900 dark:text-white">
                                {s.name}
                              </span>
                              {s.cooldownRemainingSec ? (
                                <span className="rounded bg-rose-50 px-1.5 py-0.5 text-[10px] text-rose-600 dark:bg-rose-950/40 dark:text-rose-300">
                                  CD: {s.cooldownRemainingSec}s
                                </span>
                              ) : null}
                            </div>
                            <p className="mt-1 truncate text-[11px] text-gray-400">
                              {s.url}
                            </p>
                          </div>
                          <div
                            className="shrink-0 pt-0.5"
                            onClick={(e) => e.stopPropagation()}
                            onKeyDown={(e) => e.stopPropagation()}
                          >
                            <Switch
                              aria-label={`启用 ${s.name}`}
                              isSelected={s.enabled}
                              size="sm"
                              onValueChange={(v) => void toggleSource(s.id, v)}
                            />
                          </div>
                        </button>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      ) : null}

      {editId ? (
        <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 p-4 sm:items-center">
          <div className={`${shell} w-full max-w-md p-4`}>
            {(() => {
              const cur = sources.find((s) => s.id === editId);
              return (
                <>
                  <h3 className="text-sm font-semibold text-gray-900 dark:text-white">
                    {cur?.name || editId}
                  </h3>
                  <p className="mt-1 text-[11px] text-gray-400">
                    Cookie / 代理对过墙最关键；只服务标题·封面·女优
                  </p>
                  <Input
                    className="mt-3"
                    classNames={{ inputWrapper: inputWrap }}
                    label="站点 URL"
                    radius="sm"
                    size="sm"
                    value={editUrl}
                    variant="flat"
                    onValueChange={setEditUrl}
                  />
                  <Input
                    className="mt-2"
                    classNames={{ inputWrapper: inputWrap }}
                    description="如 existmag=all; age=verified"
                    label="Cookie"
                    radius="sm"
                    size="sm"
                    value={editCookie}
                    variant="flat"
                    onValueChange={setEditCookie}
                  />
                  <Input
                    className="mt-2"
                    classNames={{ inputWrapper: inputWrap }}
                    description="空=默认 Chrome UA"
                    label="User-Agent"
                    radius="sm"
                    size="sm"
                    value={editUserAgent}
                    variant="flat"
                    onValueChange={setEditUserAgent}
                  />
                  <Select
                    className="mt-2"
                    classNames={{ trigger: inputWrap }}
                    label="代理"
                    radius="sm"
                    selectedKeys={new Set([editProxyMode])}
                    size="sm"
                    variant="flat"
                    onSelectionChange={(keys) => {
                      const v = Array.from(keys)[0];
                      if (v === "on" || v === "off" || v === "inherit") {
                        setEditProxyMode(v);
                      }
                    }}
                  >
                    <SelectItem key="inherit">跟随全局</SelectItem>
                    <SelectItem key="on">强制代理</SelectItem>
                    <SelectItem key="off">强制直连</SelectItem>
                  </Select>
                  <div className="mt-2 grid grid-cols-2 gap-2">
                    <Input
                      classNames={{ inputWrapper: inputWrap }}
                      description="0=默认"
                      label="超时 ms"
                      radius="sm"
                      size="sm"
                      type="number"
                      value={editTimeoutMs}
                      variant="flat"
                      onValueChange={setEditTimeoutMs}
                    />
                    <Input
                      classNames={{ inputWrapper: inputWrap }}
                      description="额外重试"
                      label="重试"
                      radius="sm"
                      size="sm"
                      type="number"
                      value={editRetry}
                      variant="flat"
                      onValueChange={setEditRetry}
                    />
                  </div>
                  <label className="mt-3 flex cursor-pointer items-center justify-between gap-3 text-sm text-gray-700 dark:text-slate-200">
                    <span>
                      FlareSolverr 过盾
                      <span className="mt-0.5 block text-[11px] text-gray-400">
                        javdb / 图书馆 / missav 等 CF 站需要
                      </span>
                    </span>
                    <Switch
                      isSelected={editUseFlare}
                      size="sm"
                      onValueChange={setEditUseFlare}
                    />
                  </label>
                  {cur && cur.status !== "unknown" ? (
                    <p
                      className={`mt-2 text-xs ${
                        cur.status === "ok"
                          ? "text-emerald-600 dark:text-emerald-400"
                          : "text-rose-600 dark:text-rose-400"
                      }`}
                    >
                      {cur.status === "ok"
                        ? `连通正常${cur.lastCheckedAt ? ` · ${relativeTime(cur.lastCheckedAt)}` : ""}`
                        : `失败：${zhProbeError(cur.lastError)}${cur.lastCheckedAt ? ` · ${relativeTime(cur.lastCheckedAt)}` : ""}`}
                    </p>
                  ) : (
                    <p className="mt-2 text-xs text-gray-400">尚未测试</p>
                  )}
                  <div className="mt-4 flex justify-end gap-2">
                    <Button
                      radius="sm"
                      size="sm"
                      variant="flat"
                      onPress={() => setEditId(null)}
                    >
                      取消
                    </Button>
                    <Button
                      isLoading={testing}
                      radius="sm"
                      size="sm"
                      variant="flat"
                      onPress={() => void testSources(editId)}
                    >
                      测试
                    </Button>
                    <Button
                      color="primary"
                      isLoading={editSaving}
                      radius="sm"
                      size="sm"
                      onPress={() => void saveEdit()}
                    >
                      保存
                    </Button>
                  </div>
                </>
              );
            })()}
          </div>
        </div>
      ) : null}
    </div>
  );
}
