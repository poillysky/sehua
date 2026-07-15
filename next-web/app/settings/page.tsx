"use client";

import { useCallback, useEffect, useState } from "react";
import NextLink from "next/link";
import { Button, Input, Spinner, Textarea } from "@nextui-org/react";

import { SiteLogoLink } from "@/components/SiteLogoLink";
import { setClipboard, Toast } from "@/utils";

type Status = {
  configured: boolean;
  folderCid: string;
  folderName: string;
  label: string;
  cookieHint: string;
  updatedAt: string;
};

type FolderItem = { cid: string; name: string };
type FolderPath = { cid: string; name: string };

const shell =
  "overflow-hidden rounded-lg border border-gray-200 bg-white shadow-sm dark:border-slate-700 dark:bg-slate-900";
const band = "bg-gray-50 dark:bg-slate-800";
const line = "h-px w-full bg-gray-200 dark:bg-slate-700";
const inputWrap =
  "bg-gray-50 dark:bg-slate-800/80 border border-gray-200 dark:border-slate-700 shadow-none";

function SectionTitle({
  step,
  title,
  hint,
}: {
  step: string;
  title: string;
  hint?: string;
}) {
  return (
    <div className="mb-3 flex items-start gap-2.5">
      <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary/15 text-xs font-semibold text-primary">
        {step}
      </span>
      <div className="min-w-0 pt-0.5">
        <h2 className="text-sm font-semibold text-gray-800 dark:text-slate-100">
          {title}
        </h2>
        {hint ? (
          <p className="mt-0.5 text-xs text-gray-500 dark:text-slate-400">{hint}</p>
        ) : null}
      </div>
    </div>
  );
}

export default function SettingsPage() {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [browsing, setBrowsing] = useState(false);
  const [status, setStatus] = useState<Status | null>(null);
  const [cookie, setCookie] = useState("");
  const [folderCid, setFolderCid] = useState("0");
  const [folderName, setFolderName] = useState("");
  const [label, setLabel] = useState("");
  const [quotaText, setQuotaText] = useState("");
  const [folderPath, setFolderPath] = useState<FolderPath[]>([]);
  const [folders, setFolders] = useState<FolderItem[]>([]);
  const [showBrowser, setShowBrowser] = useState(false);
  const [showCookieEdit, setShowCookieEdit] = useState(false);
  const [showCidEdit, setShowCidEdit] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);

    try {
      const res = await fetch("/api/115/config", { cache: "no-store" });
      const json = await res.json();
      const data = json.data as Status;

      setStatus(data);
      setFolderCid(data.folderCid || "0");
      setFolderName(data.folderName || "");
      setLabel(data.label || "");
      setCookie("");
      setShowCookieEdit(!data.configured);
    } catch (err) {
      Toast.error(err instanceof Error ? err.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const browseFolders = async (cid = "0") => {
    setBrowsing(true);

    try {
      const res = await fetch("/api/115/folders", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          cid,
          cookie: cookie.trim() || undefined,
        }),
        cache: "no-store",
      });
      const json = await res.json();

      if (!res.ok) {
        throw new Error(json.message || "获取目录失败");
      }

      const data = json.data as {
        path: FolderPath[];
        folders: FolderItem[];
      };

      setFolderPath(data.path || []);
      setFolders(data.folders || []);
      setShowBrowser(true);
    } catch (err) {
      Toast.error(err instanceof Error ? err.message : "获取目录失败");
    } finally {
      setBrowsing(false);
    }
  };

  const onSave = async () => {
    setSaving(true);

    try {
      const payload: Record<string, unknown> = {
        folderCid,
        folderName,
        label,
        validate: true,
      };

      if (cookie.trim()) {
        payload.cookie = cookie.trim();
      }

      const res = await fetch("/api/115/config", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const json = await res.json();

      if (!res.ok) {
        throw new Error(json.message || "保存失败");
      }

      const q = json.data?.quota;
      const qt = json.data?.quotaTotal;

      if (q != null || qt != null) {
        setQuotaText(`离线配额 ${q ?? "?"} / ${qt ?? "?"}`);
      }

      Toast.success(json.message || "已保存");
      setCookie("");
      setShowCookieEdit(false);
      setShowCidEdit(false);
      await load();
    } catch (err) {
      Toast.error(err instanceof Error ? err.message : "保存失败");
    } finally {
      setSaving(false);
    }
  };

  const onTest = async () => {
    setTesting(true);

    try {
      const res = await fetch("/api/115/validate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          cookie: cookie.trim() || undefined,
          folderCid,
        }),
      });
      const json = await res.json();

      if (!res.ok) {
        throw new Error(json.message || "测试失败");
      }

      const parts = [json.message];

      if (json.data?.folderName) parts.push(json.data.folderName);
      if (json.data?.quota != null || json.data?.quotaTotal != null) {
        setQuotaText(
          `离线配额 ${json.data.quota ?? "?"} / ${json.data.quotaTotal ?? "?"}`,
        );
        parts.push(
          `配额 ${json.data.quota ?? "?"} / ${json.data.quotaTotal ?? "?"}`,
        );
      }

      Toast.success(parts.join(" · "));
      if (json.data?.folderName) setFolderName(json.data.folderName);
    } catch (err) {
      Toast.error(err instanceof Error ? err.message : "测试失败");
    } finally {
      setTesting(false);
    }
  };

  const selectFolder = (item: FolderItem) => {
    setFolderCid(item.cid);
    setFolderName(item.name);
    setShowCidEdit(false);
    Toast.success(`已选择「${item.name}」`);
  };

  const displayName = folderName || (folderCid === "0" ? "根目录" : "自定义目录");
  const configured = Boolean(status?.configured);

  return (
    <section className="mx-auto flex w-full max-w-xl flex-col gap-4 px-3 py-4 md:py-8">
      <header className="flex items-center gap-3">
        <SiteLogoLink />
        <div className="min-w-0 flex-1">
          <h1 className="text-lg font-semibold text-gray-800 dark:text-slate-100">
            115 网盘设置
          </h1>
          <p className="text-xs text-gray-500 dark:text-slate-400">
            转存到云下载 · 配置仅保存在本机
          </p>
        </div>
        <Button
          as={NextLink}
          className="shrink-0"
          href="/"
          radius="sm"
          size="sm"
          variant="light"
        >
          首页
        </Button>
      </header>

      {loading ? (
        <div className="flex flex-col items-center gap-3 py-24">
          <Spinner color="primary" size="lg" />
          <p className="text-sm text-gray-500">加载中…</p>
        </div>
      ) : (
        <>
          {/* 总览 */}
          <div className={shell}>
            <div className={`${band} px-4 py-3`}>
              <div className="flex items-center justify-between gap-2">
                <span
                  className={
                    configured
                      ? "rounded bg-primary/12 px-2 py-0.5 text-xs font-medium text-primary"
                      : "rounded bg-warning/15 px-2 py-0.5 text-xs font-medium text-warning-600 dark:text-warning"
                  }
                >
                  {configured ? "已就绪" : "待配置"}
                </span>
                {quotaText ? (
                  <span className="text-xs text-gray-500 dark:text-slate-400">
                    {quotaText}
                  </span>
                ) : null}
              </div>
              <div className="mt-3">
                <p className="text-xs text-gray-500 dark:text-slate-400">
                  当前转存目录
                </p>
                <p className="mt-1 truncate text-xl font-semibold tracking-tight text-gray-900 dark:text-white">
                  {displayName}
                </p>
                <div className="mt-1.5 flex flex-wrap items-center gap-2">
                  <code className="max-w-full truncate rounded bg-white/80 px-1.5 py-0.5 font-mono text-[11px] text-gray-600 dark:bg-slate-900/60 dark:text-slate-300">
                    CID {folderCid || "0"}
                  </code>
                  <button
                    className="text-[11px] text-primary hover:underline"
                    type="button"
                    onClick={() => {
                      setClipboard(folderCid || "0");
                      Toast.success("CID 已复制");
                    }}
                  >
                    复制
                  </button>
                  {configured && status?.cookieHint ? (
                    <span className="text-[11px] text-gray-400">
                      · Cookie {status.cookieHint}
                      {label ? ` · ${label}` : ""}
                    </span>
                  ) : null}
                </div>
              </div>
            </div>
          </div>

          {/* ① 目录 */}
          <div className={`${shell} p-4`}>
            <SectionTitle
              hint="点「浏览」选择文件夹，或展开手动填写 CID"
              step="1"
              title="转存目录"
            />

            <div className="flex flex-wrap gap-2">
              <Button
                color="primary"
                isLoading={browsing}
                radius="sm"
                variant="flat"
                onPress={() => void browseFolders(folderCid || "0")}
              >
                {showBrowser ? "刷新目录" : "浏览 115 目录"}
              </Button>
              <Button
                radius="sm"
                variant="light"
                onPress={() => {
                  setFolderCid("0");
                  setFolderName("根目录");
                }}
              >
                使用根目录
              </Button>
              <Button
                radius="sm"
                variant="light"
                onPress={() => setShowCidEdit((v) => !v)}
              >
                {showCidEdit ? "收起 CID" : "手动填 CID"}
              </Button>
            </div>

            {showCidEdit ? (
              <div className="mt-3 grid gap-3 sm:grid-cols-2">
                <Input
                  classNames={{ inputWrapper: inputWrap }}
                  label="目录 CID"
                  radius="sm"
                  size="sm"
                  value={folderCid}
                  variant="flat"
                  onValueChange={setFolderCid}
                />
                <Input
                  classNames={{ inputWrapper: inputWrap }}
                  label="备注名（可选）"
                  placeholder="我的 115"
                  radius="sm"
                  size="sm"
                  value={label}
                  variant="flat"
                  onValueChange={setLabel}
                />
              </div>
            ) : null}

            {showBrowser ? (
              <div className={`mt-4 ${shell} !shadow-none`}>
                <div
                  className={`${band} flex items-center justify-between gap-2 px-3 py-2`}
                >
                  <nav className="flex min-w-0 flex-1 flex-wrap items-center gap-x-0.5 text-xs text-gray-600 dark:text-slate-300">
                    {folderPath.map((p, idx) => (
                      <span
                        key={`${p.cid}-${idx}`}
                        className="inline-flex max-w-full items-center"
                      >
                        {idx > 0 ? (
                          <span className="mx-0.5 text-gray-300 dark:text-slate-600">
                            /
                          </span>
                        ) : null}
                        <button
                          className="max-w-[7rem] truncate rounded px-0.5 hover:bg-primary/10 hover:text-primary"
                          type="button"
                          onClick={() => void browseFolders(p.cid)}
                        >
                          {p.name}
                        </button>
                      </span>
                    ))}
                  </nav>
                  <Button
                    className="h-6 min-h-6 shrink-0 px-2 text-xs"
                    radius="sm"
                    size="sm"
                    variant="light"
                    onPress={() => setShowBrowser(false)}
                  >
                    收起
                  </Button>
                </div>
                <div className={line} />
                <div className="max-h-56 overflow-y-auto">
                  {browsing ? (
                    <div className="flex justify-center py-10">
                      <Spinner size="sm" />
                    </div>
                  ) : folders.length === 0 ? (
                    <p className="px-3 py-8 text-center text-sm text-gray-400">
                      此层没有子文件夹，可点上方「选用」或使用当前路径
                    </p>
                  ) : (
                    <ul>
                      {folders.map((f) => {
                        const selected = f.cid === folderCid;

                        return (
                          <li
                            key={f.cid}
                            className={`flex items-center gap-2 border-b border-gray-100 px-3 py-2.5 last:border-0 dark:border-slate-800 ${
                              selected ? "bg-primary/5" : ""
                            }`}
                          >
                            <button
                              className="min-w-0 flex-1 truncate text-left text-sm text-gray-800 hover:text-primary dark:text-slate-100"
                              type="button"
                              onClick={() => void browseFolders(f.cid)}
                            >
                              {f.name}
                            </button>
                            <Button
                              className="h-7 min-h-7 shrink-0 px-2.5 text-xs"
                              color={selected ? "success" : "primary"}
                              radius="sm"
                              size="sm"
                              variant="flat"
                              onPress={() => selectFolder(f)}
                            >
                              {selected ? "已选" : "选用"}
                            </Button>
                          </li>
                        );
                      })}
                    </ul>
                  )}
                </div>
                {folderPath.length > 0 ? (
                  <>
                    <div className={line} />
                    <div className={`${band} flex justify-end px-3 py-2`}>
                      <Button
                        className="h-7 min-h-7 text-xs"
                        color="primary"
                        radius="sm"
                        size="sm"
                        variant="flat"
                        onPress={() => {
                          const cur = folderPath[folderPath.length - 1];

                          if (cur) {
                            selectFolder({ cid: cur.cid, name: cur.name });
                          }
                        }}
                      >
                        选用当前路径
                      </Button>
                    </div>
                  </>
                ) : null}
              </div>
            ) : null}
          </div>

          {/* ② Cookie */}
          <div className={`${shell} p-4`}>
            <SectionTitle
              hint={
                configured
                  ? "已保存到本机；过期或失效时再更换"
                  : "浏览器登录 115 后复制 Cookie（UID / CID / SEID，建议含 KID）"
              }
              step="2"
              title="登录 Cookie"
            />

            {configured && !showCookieEdit ? (
              <div className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-gray-200 bg-gray-50 px-3 py-3 dark:border-slate-700 dark:bg-slate-800/80">
                <div className="min-w-0 text-sm text-gray-700 dark:text-slate-200">
                  <span className="font-medium">已保存</span>
                  <span className="ml-2 text-xs text-gray-500">
                    {status?.cookieHint || "••••"}
                  </span>
                </div>
                <Button
                  radius="sm"
                  size="sm"
                  variant="flat"
                  onPress={() => setShowCookieEdit(true)}
                >
                  更换 Cookie
                </Button>
              </div>
            ) : (
              <div className="space-y-2">
                <Textarea
                  classNames={{ inputWrapper: inputWrap }}
                  minRows={3}
                  placeholder="UID=...; CID=...; SEID=...; KID=..."
                  radius="sm"
                  value={cookie}
                  variant="flat"
                  onValueChange={setCookie}
                />
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="text-[11px] text-gray-400">
                    {configured
                      ? "粘贴新 Cookie 后点下方保存；取消则不修改"
                      : "粘贴完整 Cookie 字符串"}
                  </p>
                  {configured ? (
                    <Button
                      radius="sm"
                      size="sm"
                      variant="light"
                      onPress={() => {
                        setCookie("");
                        setShowCookieEdit(false);
                      }}
                    >
                      取消
                    </Button>
                  ) : null}
                </div>
              </div>
            )}
          </div>

          {/* 操作 */}
          <div
            className={`${shell} sticky bottom-3 z-10 ${band} flex flex-col gap-2 border-primary/20 p-3 sm:flex-row sm:items-center`}
          >
            <Button
              className="sm:flex-1"
              color="primary"
              isLoading={saving}
              radius="sm"
              onPress={() => void onSave()}
            >
              保存并验证
            </Button>
            <Button
              className="sm:w-28"
              isLoading={testing}
              radius="sm"
              variant="flat"
              onPress={() => void onTest()}
            >
              测试连通
            </Button>
          </div>

          <p className="px-1 text-center text-[11px] leading-relaxed text-gray-400 dark:text-slate-500">
            配置写入 data/p115-config.json。带密码时会轮询离线任务（最长约 30
            秒），转存完成后立即云解压到同名文件夹（保留压缩包）。需 VIP；zip/rar/7z
            ≤20GB。
          </p>
        </>
      )}
    </section>
  );
}
