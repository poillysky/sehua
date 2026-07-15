const mainNav = document.querySelectorAll(".main-nav .nav-btn, .header-actions .nav-btn[data-page]");
const pages = document.querySelectorAll(".page:not(.overlay-page)");
const overlayPages = document.querySelectorAll(".overlay-page");
const configTabs = document.querySelectorAll(".settings-nav-item");
const configPanels = document.querySelectorAll(".settings-panel");
const crawlerTabs = document.querySelectorAll(".crawler-tab");
const crawlerPanels = document.querySelectorAll(".crawler-panel");
const detailTabs = document.querySelectorAll(".detail-tab");

let cachedSettings = {};
let allResources = [];
let filteredResources = [];
let selectedResourceId = null;
let selectedSourceKeys = new Set();
let selectedLinkKinds = new Set();
let sourceFilterAll = true;
let categoryFilterAll = true;
let cachedFilterDimensions = null;
let currentDetailTab = "verdict";
let currentUser = null;
let cachedForums = [];
let cachedForumConfigs = {};
let cachedBoardCrawl = null;
let activeForumId = null;
let activeForumTab = "overview";
let boardSortSuppressClickUntil = 0;
let boardSortDragState = null;
let boardStatsRefreshing = false;
let lastActivityId = 0;
let crawlerPollTimer = null;
let crawlerPollRunning = false;
let crawlerBurstTimer = null;
let forumTopologyTimer = null;
let cachedForumTopology = null;
let systemMessages = [];
let forumLinkStatus = {};
let forumLinkProbeGen = {};
let cachedSystemInfo = {};
let cachedUsers = [];
let notifyTimer = null;

const MAX_SYSTEM_MESSAGES = 50;
const NOTIFY_ICONS = {
  success: "✓",
  error: "✕",
  info: "i",
  warn: "!",
};

const ROLE_LABELS = { admin: "管理员", operator: "操作员", viewer: "只读" };

function hasPerm(permission) {
  if (!currentUser) return false;
  const perms = currentUser.permissions || [];
  return perms.includes("*") || perms.includes(permission);
}

function roleLabel(name) {
  return ROLE_LABELS[name] || name;
}

function formatApiError(data) {
  if (typeof data.detail === "string") return data.detail;
  if (Array.isArray(data.detail)) {
    return data.detail
      .map((item) => {
        const field = Array.isArray(item.loc) ? item.loc.filter((part) => part !== "body").join(".") : "";
        const msg = item.msg || "";
        return field ? `${field}: ${msg}` : msg;
      })
      .join("；");
  }
  return data.message || "请求失败";
}

async function api(url, options = {}) {
  const isForm = options.body instanceof FormData;
  const res = await fetch(url, {
    credentials: "include",
    headers: isForm ? {} : { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const data = await res.json().catch(() => ({}));
  if (res.status === 401) {
    location.href = "/login?next=" + encodeURIComponent(location.pathname);
    throw new Error("未登录");
  }
  if (!res.ok) throw new Error(formatApiError(data));
  return data;
}

function formatClockTime(date = new Date()) {
  return date.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function pushSystemMessage(message, { type = "success", detail = "" } = {}) {
  systemMessages.unshift({
    id: `${Date.now()}-${Math.random().toString(16).slice(2, 8)}`,
    type,
    message,
    detail,
    time: new Date(),
  });
  if (systemMessages.length > MAX_SYSTEM_MESSAGES) systemMessages.length = MAX_SYSTEM_MESSAGES;
  renderSystemMessageList();
  updateSystemMsgBadge();
}

function updateSystemMsgBadge() {
  const badge = document.getElementById("systemMsgBadge");
  if (!badge) return;
  const count = systemMessages.length;
  badge.hidden = count === 0;
  badge.textContent = count > 99 ? "99+" : String(count);
}

function renderSystemMessageList() {
  const list = document.getElementById("systemMessageList");
  if (!list) return;
  if (!systemMessages.length) {
    list.innerHTML = `<li class="system-message-empty">暂无操作记录</li>`;
    return;
  }
  list.innerHTML = systemMessages
    .map(
      (item) => `<li class="system-message-item system-message-${escapeHtml(item.type)}">
        <div class="system-message-main">
          <span class="system-message-icon" aria-hidden="true">${NOTIFY_ICONS[item.type] || NOTIFY_ICONS.info}</span>
          <div class="system-message-text">
            <strong>${escapeHtml(item.message)}</strong>
            ${item.detail ? `<span class="system-message-detail">${escapeHtml(item.detail)}</span>` : ""}
          </div>
        </div>
        <time class="system-message-time">${formatClockTime(item.time)}</time>
      </li>`
    )
    .join("");
}

function renderSystemInfoModal() {
  const versionEl = document.getElementById("systemInfoVersion");
  const dbEl = document.getElementById("systemInfoDb");
  const titleEl = document.getElementById("systemInfoTitle");
  const healthEl = document.getElementById("systemInfoHealth");
  if (versionEl) versionEl.textContent = `v${cachedSystemInfo.version || "1.0.0"}`;
  if (titleEl) titleEl.textContent = cachedSettings.collector_title || "ED2K 收集器";
  if (dbEl) {
    const db = cachedSystemInfo.database || {};
    dbEl.textContent = db.host ? `${db.host}:${db.port}/${db.database}` : cachedSystemInfo.dbLabel || "-";
  }
  if (healthEl) {
    healthEl.textContent = cachedSystemInfo.health === "ok" ? "正常" : "异常";
  }
  renderSystemMessageList();
}

function openSystemInfoModal() {
  renderSystemInfoModal();
  openModal("systemInfoModal");
}

function showNotifyToast(message, type = "success", detail = "") {
  const el = document.getElementById("notifyToast");
  if (!el) return;
  const iconEl = el.querySelector(".notify-toast-icon");
  const titleEl = el.querySelector(".notify-toast-title");
  const detailEl = el.querySelector(".notify-toast-detail");
  el.className = `notify-toast notify-${type}`;
  if (iconEl) iconEl.textContent = NOTIFY_ICONS[type] || NOTIFY_ICONS.info;
  if (titleEl) titleEl.textContent = message;
  if (detailEl) {
    detailEl.textContent = detail || "";
    detailEl.hidden = !detail;
  }
  el.hidden = false;
  el.classList.add("show");
  if (notifyTimer) clearTimeout(notifyTimer);
  notifyTimer = setTimeout(() => {
    el.classList.remove("show");
    setTimeout(() => {
      el.hidden = true;
    }, 220);
  }, detail ? 4200 : 3000);
}

function notify(message, isErrorOrOptions = false) {
  let type = "success";
  let detail = "";
  if (typeof isErrorOrOptions === "boolean") {
    type = isErrorOrOptions ? "error" : "success";
  } else if (isErrorOrOptions && typeof isErrorOrOptions === "object") {
    type = isErrorOrOptions.type || "success";
    detail = isErrorOrOptions.detail || "";
  }
  pushSystemMessage(message, { type, detail });
  showNotifyToast(message, type, detail);
}

function toast(msg, isError = false) {
  notify(msg, isError);
}

function escapeHtml(text) {
  return String(text ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function formatSize(bytes) {
  const n = Number(bytes);
  if (!n) return "-";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let v = n;
  let i = 0;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i += 1;
  }
  return `${v.toFixed(i === 0 ? 0 : 2)} ${units[i]}`;
}

function formatTime(iso) {
  if (!iso) return "-";
  try {
    return new Date(iso).toLocaleString("zh-CN", {
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

function statusTag(status) {
  const map = {
    active: "tag-active",
    pending: "tag-pending",
    done: "tag-done",
    failed: "tag-failed",
    login_required: "tag-login",
    disabled: "tag-disabled",
  };
  const label = {
    active: "活跃",
    pending: "待处理",
    done: "成功",
    failed: "失败",
    login_required: "需登录",
    disabled: "禁用",
  }[status] || status;
  return `<span class="tag ${map[status] || "tag-disabled"}">${escapeHtml(label)}</span>`;
}

function threadTitle(url) {
  const match = url.match(/thread-(\d+)-/);
  if (match) return `帖子 #${match[1]}`;
  try {
    const path = new URL(url).pathname;
    return path.length > 40 ? `${path.slice(0, 40)}…` : path;
  } catch {
    return url.length > 48 ? `${url.slice(0, 48)}…` : url;
  }
}

function linkTypeTag(type) {
  if (type === "magnet") return '<span class="tag tag-magnet">magnet</span>';
  if (type === "ed2k") return '<span class="tag tag-ed2k">ed2k</span>';
  if (type === "stub") return '<span class="tag tag-stub">占位</span>';
  if (type === "skipped") return '<span class="tag tag-skipped">跳过</span>';
  if (type === "failed") return '<span class="tag tag-failed">失败</span>';
  return `<span class="tag tag-disabled">${escapeHtml(type)}</span>`;
}

function sourceTypeLabel(type) {
  return { web: "论坛", upload: "人工导入", telegram: "TG 群组" }[type] || type;
}

function sourceIcon(type) {
  return { web: "🌐", upload: "📥", telegram: "✈" }[type] || "📄";
}

function isForumCrawlerTabActive() {
  return document.getElementById("crawler-forum")?.classList.contains("active");
}

function showCrawlerTab(tabId) {
  crawlerTabs.forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.crawler === tabId);
  });
  crawlerPanels.forEach((panel) => {
    panel.classList.toggle("active", panel.id === `crawler-${tabId}`);
  });
  if (tabId === "forum") {
    const page = document.getElementById("page-crawler");
    if (page?.classList.contains("active")) {
      refreshCrawler().catch((e) => toast(e.message, true));
    }
  }
}

function parseTestWarnings(data) {
  const warnings = [];
  if (data.interstitial) warnings.push("站点软文拦截（名人名言页），非真实帖正文");
  if (data.mobile_shell) warnings.push("检测到手机版空壳页，已尝试转桌面链接");
  if (data.login_required) warnings.push("帖子需要论坛登录");
  if (data.reply_required) warnings.push("帖子需要回复后才可见资源");
  if (data.attachment_denied) warnings.push("附件无下载权限");
  if (data.attachment_failed) warnings.push("附件下载失败");
  if (data.attachment_downloaded && !data.attachment_text_len && data.attachments?.length) {
    warnings.push("附件已下载但解压为空（可能缺少 unrar/7z，或附件非文本链接）");
  }
  if (!data.final_ed2k_count && !data.final_magnet_count) {
    warnings.push("未发现可入库的 ED2K 或 magnet 链接");
  }
  return warnings;
}

function importVerdictClass(verdict) {
  if (verdict === "import") return "pt-verdict-import";
  if (verdict === "stub") return "pt-verdict-stub";
  if (verdict === "interstitial") return "pt-verdict-warn";
  return "pt-verdict-failed";
}

function renderImportVerdict(data) {
  const verdict = data.import_verdict || "failed";
  const label = data.import_verdict_label || "异常标记";
  const outcome = data.import_outcome || "";
  const count = data.import_link_count ?? 0;
  const detail =
    verdict === "import" && count > 0
      ? `预计写入 ${count} 条资源`
      : outcome;
  return `
    <div class="pt-verdict ${importVerdictClass(verdict)}">
      <span class="pt-verdict-label">${escapeHtml(label)}</span>
      <span class="pt-verdict-outcome">${escapeHtml(detail)}</span>
    </div>
  `;
}

function renderParseTestLinks(title, items) {
  if (!items?.length) return "";
  const rows = items
    .map(
      (item) => `
      <div class="pt-link">
        <div class="pt-link-name">${escapeHtml(item.filename || item.infohash || item.hash || "链接")}</div>
        <code class="pt-link-uri">${escapeHtml(item.link || "")}</code>
      </div>`
    )
    .join("");
  return `<section class="pt-block"><div class="pt-block-title">${escapeHtml(title)} <span class="pt-count">${items.length}</span></div>${rows}</section>`;
}

function renderParseTestResult(data) {
  const warnings = parseTestWarnings(data);
  const title = data.title || data.page_title || "（无标题）";
  const resourceName = (data.resource_name || "").trim();
  const showResourceName =
    resourceName && resourceName !== title.trim() && !title.includes(resourceName);

  const tags = [
    data.board_name ? `<span class="tag tag-active">${escapeHtml(data.board_name)}</span>` : "",
    data.board_fid ? `<span class="tag tag-disabled">fid ${escapeHtml(data.board_fid)}</span>` : "",
    data.link_kind ? linkTypeTag(data.link_kind) : "",
    data.url_converted ? '<span class="tag tag-disabled">桌面链接</span>' : "",
    `<span class="tag tag-disabled">${Number(data.html_len || 0).toLocaleString()} B</span>`,
  ]
    .filter(Boolean)
    .join("");

  const stats = [
    ["ED2K", data.final_ed2k_count ?? 0],
    ["magnet", data.final_magnet_count ?? 0],
    ["正文ED2K", data.body_ed2k_count ?? 0],
    ["正文磁力", data.body_magnet_count ?? 0],
    ["附件", data.attachments?.length ?? 0],
    ["解压密码", data.extract_password ? "有" : "无"],
  ]
    .map(
      ([label, val]) => {
        const display =
          label === "解压密码" && data.extract_password
            ? data.extract_password
            : val;
        return `<span class="pt-stat"><em>${escapeHtml(label)}</em><strong>${escapeHtml(String(display))}</strong></span>`;
      }
    )
    .join("");

  const rows = [
    showResourceName ? ["资源名称", resourceName, true] : null,
    ["资源数量", data.resource_count],
    ["文件大小", data.file_size],
    ["有无水印", data.watermark],
    ["有无码", data.coded],
    ["女优", data.actress],
    ["解压密码", data.extract_password, true],
    ["抓取 URL", data.fetch_url, true],
    ["附件来源", data.attachment_source],
  ]
    .filter(Boolean)
    .filter(([, val]) => val !== undefined && val !== null && String(val).trim() !== "")
    .map(
      ([label, val, full]) =>
        `<div class="pt-row${full ? " full" : ""}"><dt>${escapeHtml(label)}</dt><dd${label === "解压密码" ? ' class="mono"' : ""}>${escapeHtml(String(val))}</dd></div>`
    )
    .join("");

  const attachments = (data.attachments || [])
    .map((a) => `<span class="pt-chip">${escapeHtml(a.kind || "?")} · ${escapeHtml(a.name || "")}</span>`)
    .join("");

  const warnHtml = warnings.length
    ? `<ul class="pt-warns">${warnings.map((w) => `<li>${escapeHtml(w)}</li>`).join("")}</ul>`
    : "";

  return `
    <div class="pt-result">
      ${renderImportVerdict(data)}
      ${warnHtml}
      <header class="pt-hero">
        <h4 class="pt-title">${escapeHtml(title)}</h4>
        <div class="pt-tags">${tags}</div>
        <div class="pt-stats">${stats}</div>
      </header>
      ${rows ? `<dl class="pt-meta">${rows}</dl>` : ""}
      ${
        data.description
          ? `<section class="pt-block"><div class="pt-block-title">简介</div><pre class="pt-pre">${escapeHtml(data.description)}</pre></section>`
          : ""
      }
      ${
        attachments
          ? `<section class="pt-block"><div class="pt-block-title">附件 <span class="pt-count">${data.attachments.length}</span></div><div class="pt-chips">${attachments}</div></section>`
          : ""
      }
      ${renderParseTestLinks("ED2K 链接", data.ed2k_links)}
      ${renderParseTestLinks("Magnet 链接", data.magnets)}
      ${
        data.attachment_text_preview
          ? `<section class="pt-block"><div class="pt-block-title">附件解压预览</div><pre class="pt-pre">${escapeHtml(data.attachment_text_preview)}</pre></section>`
          : ""
      }
    </div>
  `;
}

function setParseTestStatus(text, tone = "") {
  const statusEl = document.getElementById("parseTestStatus");
  if (!statusEl) return;
  statusEl.textContent = text;
  statusEl.classList.remove("is-loading", "is-done", "is-warn");
  if (tone) statusEl.classList.add(tone);
}

function renderParseTestLoading() {
  return `
    <div class="parse-test-loading">
      <div class="parse-test-loading-spinner" aria-hidden="true"></div>
      <p>正在抓取页面并解析，请稍候…</p>
    </div>
  `;
}

async function runParseTest(event) {
  event.preventDefault();
  const btn = document.getElementById("parseTestBtn");
  const resultEl = document.getElementById("parseTestResult");
  const url = document.getElementById("parseTestUrl")?.value.trim();
  if (!url) {
    toast("请输入帖子 URL", true);
    return;
  }
  const fid = document.getElementById("parseTestFid")?.value.trim() || "";
  const proxy = document.getElementById("parseTestProxy")?.value.trim() || "";
  const forumId = getActiveForumId();
  const prevText = btn?.textContent || "开始解析";
  if (btn) {
    btn.disabled = true;
    btn.textContent = "解析中...";
  }
  setParseTestStatus("解析中...", "is-loading");
  if (resultEl) resultEl.innerHTML = renderParseTestLoading();

  try {
    const data = await api(`/api/forum/${forumId}/parse-thread`, {
      method: "POST",
      body: JSON.stringify({ url, fid, proxy }),
    });
    if (resultEl) {
      resultEl.innerHTML = renderParseTestResult(data);
    }
    const hasLinks = data.final_ed2k_count || data.final_magnet_count;
    const verdict = data.import_verdict || "failed";
    const verdictTone =
      verdict === "import"
        ? "is-done"
        : verdict === "failed"
          ? "is-warn"
          : "is-warn";
    setParseTestStatus(
      `${data.import_verdict_label || "异常标记"} · ${data.import_outcome || ""}`,
      verdictTone
    );
    notify(`${data.import_verdict_label || "解析完成"}`, {
      type: verdict === "import" ? "success" : "warn",
      detail: data.import_outcome || data.title || url,
    });
  } catch (err) {
    setParseTestStatus("解析失败", "is-warn");
    if (resultEl) {
      resultEl.innerHTML = `<ul class="pt-warns"><li>${escapeHtml(err.message || "解析失败")}</li></ul>`;
    }
    toast(err.message, true);
  } finally {
    if (btn) {
      btn.disabled = !hasPerm("settings.read");
      btn.textContent = prevText;
    }
  }
}

function showPage(pageId) {
  pages.forEach((p) => p.classList.toggle("active", p.id === `page-${pageId}`));
  overlayPages.forEach((p) => p.classList.toggle("active", p.id === `page-${pageId}`));
  document.querySelectorAll(".main-nav .nav-btn").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.page === pageId && pageId !== "settings");
  });
  if (pageId === "crawler") {
    lastActivityId = 0;
    refreshCrawler().catch((e) => toast(e.message, true));
    startCrawlerPolling();
  } else {
    stopCrawlerPolling();
  }
  if (pageId === "settings") {
    loadForumRules().catch(() => {});
    loadBoardConfig().catch(() => {});
    if (hasPerm("users.manage")) loadUsers().catch(() => {});
  }
  if (pageId === "data-mgmt") {
    loadDataOverview().catch((e) => toast(e.message, true));
  }
}

function renderDataOverview(data) {
  const overview = data?.overview || {};
  const set = (id, value) => {
    const el = document.getElementById(id);
    if (el) el.textContent = Number(value || 0).toLocaleString();
  };
  set("dataCountResources", overview.resources);
  set("dataCountResourceSources", overview.resource_sources);
  set("dataCountImportJobs", overview.import_jobs);
  set("dataCountCrawlPages", overview.crawl_pages);
  set("dataCountCrawlPending", overview.crawl_pending);
  set("dataCountCrawlBoards", overview.crawl_boards);
  set("dataCountActivityLogs", overview.activity_logs);

  const hint = document.getElementById("dataMgmtCrawlerHint");
  if (!hint) return;
  if (data?.crawler_running) {
    hint.hidden = false;
    hint.textContent = "爬虫正在执行中，请先关闭爬虫并等待当前轮次结束后再清空数据。";
  } else if (data?.crawler_enabled) {
    hint.hidden = false;
    hint.textContent = "爬虫开关当前为开启状态，清空时会自动关闭爬虫。";
  } else {
    hint.hidden = true;
    hint.textContent = "";
  }
}

async function loadDataOverview() {
  const data = await api("/api/system/data-overview");
  renderDataOverview(data);
  return data;
}

async function resetAllData(confirmText) {
  return api("/api/system/reset", {
    method: "POST",
    body: JSON.stringify({ confirm: confirmText }),
  });
}

function applyPermissions() {
  const settingsBtn = document.querySelector('.header-actions .nav-btn[data-page="settings"]');
  if (settingsBtn) settingsBtn.hidden = !hasPerm("settings.read");

  const parseTestNavBtn = document.getElementById("parseTestNavBtn");
  if (parseTestNavBtn) parseTestNavBtn.hidden = !hasPerm("settings.read");

  const dataMgmtNavBtn = document.getElementById("dataMgmtNavBtn");
  if (dataMgmtNavBtn) dataMgmtNavBtn.hidden = !hasPerm("settings.write");

  const importBtn = document.getElementById("importQuickBtn");
  if (importBtn) importBtn.hidden = !hasPerm("import");

  const crawlBtn = document.getElementById("runCrawlBtn");
  if (crawlBtn) crawlBtn.hidden = !hasPerm("crawl.run");

  const canCrawlRun = hasPerm("crawl.run");
  const toggleWrap = document.getElementById("crawlerToggleWrap");
  const crawlerSwitch = document.getElementById("crawlerSwitch");
  if (toggleWrap) toggleWrap.hidden = !canCrawlRun;
  if (crawlerSwitch) crawlerSwitch.disabled = !canCrawlRun;

  const canWrite = hasPerm("settings.write");
  const canSettingsRead = hasPerm("settings.read");
  document.querySelectorAll("#telegramForm button[type='submit'], #settingsForm button[type='submit'], .forum-save-btn").forEach((btn) => {
    btn.disabled = !canWrite;
  });
  const testProxyBtn = document.getElementById("testProxyBtn");
  if (testProxyBtn) testProxyBtn.disabled = !canSettingsRead;
  const parseTestBtn = document.getElementById("parseTestBtn");
  if (parseTestBtn) parseTestBtn.disabled = !canSettingsRead;
  document.querySelectorAll(".forum-cookie-field").forEach((el) => {
    if (!canWrite) el.setAttribute("disabled", "disabled");
    else el.removeAttribute("disabled");
  });
  document.querySelectorAll("#parseTestForm input, #parseTestForm textarea").forEach((el) => {
    if (!canSettingsRead) el.setAttribute("disabled", "disabled");
    else el.removeAttribute("disabled");
  });

  const canDataReset = hasPerm("settings.write");
  const dataResetBtn = document.getElementById("dataResetBtn");
  if (dataResetBtn) dataResetBtn.disabled = !canDataReset;
  const dataResetConfirm = document.getElementById("dataResetConfirm");
  if (dataResetConfirm) {
    if (!canDataReset) dataResetConfirm.setAttribute("disabled", "disabled");
    else dataResetConfirm.removeAttribute("disabled");
  }
  const refreshDataOverviewBtn = document.getElementById("refreshDataOverview");
  if (refreshDataOverviewBtn) refreshDataOverviewBtn.disabled = !canDataReset;

  document.querySelectorAll("#telegramForm input, #settingsForm input, .forum-config-form input, .forum-config-form textarea, #createUserForm input, #createUserForm select").forEach((el) => {
    if (el.dataset.keepDisabled) return;
    if (!canWrite) el.setAttribute("disabled", "disabled");
    else el.removeAttribute("disabled");
  });
  document.querySelectorAll('input[name="active_forum_id"]').forEach((el) => {
    const forum = cachedForums.find((f) => f.id === el.value);
    if (!canWrite || forum?.status !== "active") el.setAttribute("disabled", "disabled");
    else el.removeAttribute("disabled");
  });
  document.querySelectorAll("#createUserForm input, #createUserForm select, #editUserForm input, #editUserForm select").forEach((el) => {
    if (!hasPerm("users.manage")) el.setAttribute("disabled", "disabled");
    else el.removeAttribute("disabled");
  });
  document.querySelectorAll("#createUserForm button[type='submit'], #editUserForm button[type='submit']").forEach((btn) => {
    btn.disabled = !hasPerm("users.manage");
  });

  const usersTab = document.getElementById("usersConfigTab");
  if (usersTab) usersTab.hidden = !hasPerm("users.manage");

  const createUserBtn = document.getElementById("openCreateUserBtn");
  if (createUserBtn) createUserBtn.hidden = !hasPerm("users.manage");

  const accountLabel = document.getElementById("accountLabel");
  const accountAvatar = document.getElementById("accountAvatar");
  if (currentUser) {
    const name = currentUser.display_name || currentUser.username;
    if (accountLabel) accountLabel.textContent = name;
    if (accountAvatar) accountAvatar.textContent = name.charAt(0).toUpperCase();
  }
}

function renderAccountInfo() {
  const el = document.getElementById("accountInfo");
  if (!el || !currentUser) return;
  el.innerHTML = `
    <div class="detail-grid">
      <div class="detail-field"><span class="lbl">用户名</span><span class="val">${escapeHtml(currentUser.username)}</span></div>
      <div class="detail-field"><span class="lbl">显示名</span><span class="val">${escapeHtml(currentUser.display_name || "-")}</span></div>
      <div class="detail-field full"><span class="lbl">角色</span><span class="val">${(currentUser.roles || []).map((r) => `<span class="tag tag-active">${escapeHtml(roleLabel(r))}</span>`).join(" ")}</span></div>
    </div>`;
}

async function initAuth() {
  const status = await fetch("/api/auth/status", { credentials: "include" }).then((r) => r.json());
  if (status.auth_required && !status.authenticated) {
    location.href = "/login?next=" + encodeURIComponent(location.pathname);
    return false;
  }
  if (status.user) {
    currentUser = status.user;
  } else {
    const me = await api("/api/auth/me");
    currentUser = me.user;
  }
  applyPermissions();
  renderAccountInfo();
  return true;
}

async function loadUsers() {
  const data = await api("/api/auth/users");
  cachedUsers = data.users || [];
  const tbody = document.getElementById("usersTableBody");
  if (!tbody) return;
  tbody.innerHTML = cachedUsers
    .map((user) => {
      const roles = (user.roles || []).map((r) => roleLabel(r)).join("、");
      const status = user.is_active ? '<span class="tag tag-active">启用</span>' : '<span class="tag tag-disabled">禁用</span>';
      const isSelf = currentUser && user.id === currentUser.id;
      return `<tr>
        <td>${escapeHtml(user.username)}</td>
        <td>${escapeHtml(user.display_name || "-")}</td>
        <td>${escapeHtml(roles)}</td>
        <td>${status}</td>
        <td>${formatTime(user.last_login_at)}</td>
        <td class="table-actions">
          <button type="button" class="btn-link" data-user-open-edit="${user.id}">编辑</button>
          <button type="button" class="btn-link" data-user-toggle="${user.id}" data-user-active="${user.is_active}">${user.is_active ? "禁用" : "启用"}</button>
          <button type="button" class="btn-link danger" data-user-delete="${user.id}" ${isSelf ? 'disabled title="不能删除当前登录账号"' : ""}>删除</button>
        </td>
      </tr>`;
    })
    .join("");
}

function openEditUserModal(userId) {
  const user = cachedUsers.find((item) => item.id === userId);
  if (!user) return;
  document.getElementById("editUserId").value = String(user.id);
  document.getElementById("editUsername").value = user.username;
  document.getElementById("editDisplayName").value = user.display_name || "";
  document.getElementById("editPassword").value = "";
  document.getElementById("editRoles").value = (user.roles || [])[0] || "viewer";
  const activeInput = document.getElementById("editIsActive");
  activeInput.checked = !!user.is_active;
  activeInput.disabled = currentUser && user.id === currentUser.id;
  openModal("editUserModal");
}

function openModal(id) {
  document.getElementById(id).hidden = false;
}

function closeModal(id) {
  document.getElementById(id).hidden = true;
  if (id === "forumConfigModal") {
    stopForumTopologyPoll();
    activeForumId = null;
    activeForumTab = "overview";
  }
}

function setSettingsForm(settings, { syncForumConfig = true } = {}) {
  cachedSettings = settings;
  const title = settings.collector_title || "ED2K 收集器";
  document.getElementById("collectorTitle").textContent = title;
  document.title = title;

  const map = [
    ["tg_enabled", "checked", false],
    ["tg_api_id", "value", ""],
    ["tg_api_hash", "value", ""],
    ["tg_groups", "value", ""],
    ["tg_session", "value", "ed2k"],
    ["next_web_url", "value", "http://localhost:3008"],
    ["collector_title", "value", title],
    ["web_crawler_proxy", "value", ""],
  ];
  for (const [id, prop, fallback] of map) {
    const el = document.getElementById(id);
    if (!el) continue;
    const val = settings[id] ?? fallback;
    if (prop === "checked") el.checked = !!val;
    else el[prop] = val;
  }

  const searchUrl = settings.next_web_url || "http://localhost:3008";
  const previewLink = document.getElementById("previewSearchWeb");
  if (previewLink) previewLink.href = searchUrl;

  if (settings.active_forum_id) {
    document.querySelectorAll('input[name="active_forum_id"]').forEach((radio) => {
      radio.checked = radio.value === settings.active_forum_id;
    });
    rerenderForumIcons();
  }

  if (!syncForumConfig) return;

  const forumId = settings.active_forum_id || cachedSettings.active_forum_id || "sehuatang";
  const forumCfg = extractForumConfigFromSettings(settings);
  cachedForumConfigs[forumId] = {
    ...(cachedForumConfigs[forumId] || {}),
    ...forumCfg,
  };
  const forum = cachedForums.find((f) => f.id === forumId);
  if (forum) {
    forum.crawler_config = {
      ...(forum.crawler_config || {}),
      ...forumCfg,
    };
  }
}

function normalizeCookieInput(raw) {
  return String(raw || "")
    .replace(/\r\n/g, "\n")
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .join("; ")
    .replace(/;\s*;/g, "; ")
    .replace(/^;\s*|;\s*$/g, "")
    .trim();
}

function settingChecked(id, fallback = false) {
  const el = document.getElementById(id);
  if (el) return el.checked;
  if (cachedSettings[id] !== undefined) return !!cachedSettings[id];
  return fallback;
}

function settingNumber(id, fallback) {
  const el = document.getElementById(id);
  if (el) return Number(el.value || fallback);
  if (cachedSettings[id] !== undefined) return Number(cachedSettings[id]);
  return fallback;
}

function settingText(id, fallback = "") {
  const el = document.getElementById(id);
  if (el) return el.value.trim();
  if (cachedSettings[id] !== undefined) return String(cachedSettings[id] ?? fallback);
  return fallback;
}

function collectGlobalSettings() {
  return {
    tg_enabled: settingChecked("tg_enabled", false),
    tg_api_id: settingText("tg_api_id"),
    tg_api_hash: settingText("tg_api_hash"),
    tg_groups: settingText("tg_groups"),
    tg_session: settingText("tg_session", "ed2k") || "ed2k",
    next_web_url: settingText("next_web_url", "http://localhost:3008"),
    collector_title: settingText("collector_title", "ED2K Collector") || "ED2K Collector",
    web_crawler_proxy: settingText("web_crawler_proxy"),
    active_forum_id: getActiveForumId(),
  };
}

function collectSettings() {
  return {
    ...collectGlobalSettings(),
    ...forumCrawlerPayload(getActiveForumId()),
  };
}

function getActiveForumId() {
  const checked = document.querySelector('input[name="active_forum_id"]:checked');
  if (checked) return checked.value;
  return cachedSettings.active_forum_id || "sehuatang";
}

function forumCrawlerPayload(forumId) {
  const cfg = cachedForumConfigs[forumId] || {};
  return extractForumConfigFromSettings(cfg);
}

function extractForumConfigFromSettings(settings) {
  return {
    web_crawler_enabled: settings.web_crawler_enabled ?? true,
    web_crawler_hot_mode: false,
    web_crawler_auto_discover: settings.web_crawler_auto_discover ?? false,
    web_crawl_urls: settings.web_crawl_urls ?? "",
    web_crawler_cookie: settings.web_crawler_cookie ?? "safe=1",
    web_crawler_max_boards_per_run: Number(settings.web_crawler_max_boards_per_run ?? 8),
    web_crawler_list_pages_per_board: Number(settings.web_crawler_list_pages_per_board ?? 15),
    web_crawler_max_threads_per_run: Number(settings.web_crawler_max_threads_per_run ?? 0),
    web_crawler_interval_minutes: Number(settings.web_crawler_interval_minutes ?? 30),
    web_crawler_request_delay: Number(settings.web_crawler_request_delay ?? 2),
    web_crawler_fetch_failure_threshold: Number(settings.web_crawler_fetch_failure_threshold ?? 5),
    web_crawler_fetch_cooldown_seconds: Number(settings.web_crawler_fetch_cooldown_seconds ?? 45),
    web_crawler_fetch_max_cooldowns: Number(settings.web_crawler_fetch_max_cooldowns ?? 3),
    web_crawler_autothrottle_max_delay: Number(settings.web_crawler_autothrottle_max_delay ?? 60),
    web_crawler_autothrottle_window: Number(settings.web_crawler_autothrottle_window ?? 20),
    web_crawler_board_refresh_hours: Number(settings.web_crawler_board_refresh_hours ?? 12),
    web_crawler_max_list_pages: Number(settings.web_crawler_max_list_pages ?? 0),
    web_crawler_fetch_retries: Number(settings.web_crawler_fetch_retries ?? 3),
    web_crawler_thread_timeout: Number(settings.web_crawler_thread_timeout ?? 120),
    web_crawler_timeout: Number(settings.web_crawler_timeout ?? 30),
    web_crawler_target_imports: Number(settings.web_crawler_target_imports ?? 0),
    web_crawler_ua: settings.web_crawler_ua ?? "",
    web_crawler_require_structured_desc: false,
    web_crawler_one_link_per_thread: settings.web_crawler_one_link_per_thread ?? true,
  };
}

function fillForumConfigForm(form, config) {
  if (!form) return;
  const merged = { ...extractForumConfigFromSettings(config || {}), ...(config || {}) };
  form.querySelectorAll("[data-forum-key]").forEach((el) => {
    const key = el.dataset.forumKey;
    if (!(key in merged)) return;
    const val = merged[key];
    if (el.type === "checkbox") el.checked = !!val;
    else el.value = val ?? "";
  });
  const oneLink = form.querySelector('[data-forum-key="web_crawler_one_link_per_thread"]');
  if (oneLink) oneLink.checked = true;
}

function collectForumConfigForm(form) {
  const defaults = extractForumConfigFromSettings({});
  const cfg = {};
  form.querySelectorAll("[data-forum-key]").forEach((el) => {
    const key = el.dataset.forumKey;
    if (el.dataset.keepDisabled) return;
    if (el.type === "checkbox") cfg[key] = el.checked;
    else if (key === "web_crawler_cookie") {
      cfg[key] = normalizeCookieInput(el.value) || "safe=1";
    } else if (el.type === "number") {
      const raw = el.value.trim();
      if (!raw) return;
      const num = el.step && el.step.includes(".") ? parseFloat(raw) : Number(raw);
      if (!Number.isFinite(num)) return;
      cfg[key] = num;
    } else if (el.type !== "hidden") cfg[key] = el.value.trim();
  });
  cfg.web_crawler_require_structured_desc = false;
  cfg.web_crawler_one_link_per_thread = true;
  cfg.web_crawler_max_threads_per_run = 0;
  if (cfg.web_crawler_max_boards_per_run == null) cfg.web_crawler_max_boards_per_run = defaults.web_crawler_max_boards_per_run;
  if (cfg.web_crawler_interval_minutes == null) cfg.web_crawler_interval_minutes = defaults.web_crawler_interval_minutes;
  return cfg;
}

function syncForumConfigsFromRules(data) {
  cachedForumConfigs = { ...(data.forum_configs || {}) };
  for (const forum of data.forums || []) {
    if (forum.crawler_config) cachedForumConfigs[forum.id] = forum.crawler_config;
  }
}

function refreshForumModalAfterSave(forumId, config) {
  const forum = cachedForums.find((f) => f.id === forumId);
  if (!forum || activeForumId !== forumId) return;

  forum.crawler_config = config;
  cachedForumConfigs[forumId] = config;

  const form = document.querySelector(".forum-config-form");
  if (form) fillForumConfigForm(form, config);

  const overviewPanel = document.querySelector('.forum-tab-panel[data-forum-tab="overview"]');
  if (overviewPanel) overviewPanel.innerHTML = renderForumOverviewTab(forum);

  applyPermissions();

  if (activeForumTab === "topology") {
    cachedForumTopology = null;
    loadForumTopology(forumId, true).catch(() => {});
  }
}

function renderCapabilities(caps) {
  const labels = {
    ed2k_import: "ED2K 导入",
    forum_crawler: "论坛爬虫",
    playwright: "Playwright",
    magnet_storage: "Magnet 入库",
    telegram: "Telegram",
  };
  const el = document.getElementById("capabilityGrid");
  if (!el) return;
  el.innerHTML = Object.entries(labels)
    .map(([key, label]) => {
      const on = !!caps[key];
      return `<div class="capability-item ${on ? "cap-on" : "cap-off"}">
        <span class="capability-dot" aria-hidden="true"></span>
        <span class="capability-name">${escapeHtml(label)}</span>
        <span class="capability-state">${on ? "可用" : "待实现"}</span>
      </div>`;
    })
    .join("");
}

function forumStatusTag(status) {
  const map = {
    active: { cls: "tag-active", label: "运行中" },
    planned: { cls: "tag-pending", label: "待定" },
  };
  const item = map[status] || { cls: "tag-disabled", label: status };
  return `<span class="tag ${item.cls}">${escapeHtml(item.label)}</span>`;
}

function renderForumPolicyList(forum) {
  return `<ul class="forum-policy-list">
    ${(forum.policies || []).map((p) => `<li>${escapeHtml(p)}</li>`).join("")}
    ${forum.skip_fids ? `<li>跳过 fid：<code>${escapeHtml((forum.skip_fids || []).join(", ") || "无")}</code></li>` : ""}
    ${forum.skip_name_keywords ? `<li>跳过名称关键词：<code>${escapeHtml((forum.skip_name_keywords || []).join(" / "))}</code></li>` : ""}
    ${forum.skip_categories?.length ? `<li>跳过分区：<code>${escapeHtml((forum.skip_categories || []).join("、"))}</code></li>` : ""}
    ${forum.list_url_pattern ? `<li>列表 URL 格式：<code>${escapeHtml(forum.list_url_pattern)}</code></li>` : ""}
  </ul>`;
}

function linkStatusText(state) {
  if (state === "ok") return "链接正常";
  if (state === "fail") return "链接失败";
  return "检测中...";
}

function renderForumLinkStatusBadge(forumId, isAvailable) {
  if (!isAvailable) return "";
  const status = forumLinkStatus[forumId] || { state: "pending" };
  return `<span class="forum-link-status forum-link-status-${status.state}" role="button" tabindex="0" data-forum-link-status="${escapeHtml(forumId)}" title="${escapeHtml(status.detail || "点击重新检测论坛链接")}">${escapeHtml(linkStatusText(status.state))}</span>`;
}

function updateForumLinkStatusBadge(forumId) {
  const el = document.querySelector(`[data-forum-link-status="${forumId}"]`);
  if (!el) return;
  const status = forumLinkStatus[forumId] || { state: "pending" };
  el.textContent = linkStatusText(status.state);
  el.className = `forum-link-status forum-link-status-${status.state}`;
  el.title = status.detail || "点击重新检测论坛链接";
}

function setForumLinkTesting(forumId, detail = "正在检测...") {
  forumLinkStatus[forumId] = { state: "testing", detail };
  updateForumLinkStatusBadge(forumId);
}

async function probeForumLinkStatus(forumId) {
  if (!hasPerm("settings.read")) return;
  const gen = (forumLinkProbeGen[forumId] || 0) + 1;
  forumLinkProbeGen[forumId] = gen;
  setForumLinkTesting(forumId);
  try {
    const data = await api(`/api/forum/${forumId}/link-test`, { method: "POST", body: "{}" });
    if (forumLinkProbeGen[forumId] !== gen) return;
    forumLinkStatus[forumId] = {
      state: data.ok ? "ok" : "fail",
      detail: data.elapsed_ms != null
        ? `${data.elapsed_ms}ms · HTTP ${data.status_code ?? "-"}`
        : (data.message || data.test_url || ""),
    };
  } catch (err) {
    if (forumLinkProbeGen[forumId] !== gen) return;
    forumLinkStatus[forumId] = { state: "fail", detail: err.message };
  }
  if (forumLinkProbeGen[forumId] !== gen) return;
  updateForumLinkStatusBadge(forumId);
}

async function autoProbeForumLinkStatuses() {
  const forums = cachedForums.filter((f) => f.status === "active");
  await Promise.all(forums.map((f) => probeForumLinkStatus(f.id)));
}

function renderForumIconTile(forum) {
  const isAvailable = forum.status === "active";
  const activeForumId = cachedSettings.active_forum_id || "sehuatang";
  const isEnabled = activeForumId === forum.id;
  const boardCount = forum.board_count ?? (forum.boards || []).length;
  const magnetCount = (forum.boards || []).filter((b) => b.primary_link === "magnet").length;
  const ed2kCount = (forum.boards || []).filter((b) => b.primary_link === "ed2k").length;

  return `<div class="forum-icon-wrap ${isEnabled ? "forum-icon-wrap-enabled" : ""} ${isAvailable ? "" : "forum-icon-wrap-planned"}">
    <div class="forum-icon-toolbar">
      <label class="forum-enable-radio" title="设为启用论坛">
        <input type="radio" name="active_forum_id" value="${escapeHtml(forum.id)}" ${isEnabled ? "checked" : ""} ${isAvailable ? "" : "disabled"} />
        <span class="forum-enable-dot" aria-hidden="true"></span>
        <span>启用</span>
      </label>
      ${isAvailable ? renderForumLinkStatusBadge(forum.id, isAvailable) : ""}
    </div>
    <button type="button" class="forum-icon-tile" data-forum-open="${escapeHtml(forum.id)}" ${isAvailable ? "" : "disabled"}>
      <span class="forum-icon-tile-icon" aria-hidden="true">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75"><circle cx="12" cy="12" r="9"/><path d="M2 12h20M12 3a15 15 0 0 1 0 18M12 3a15 15 0 0 0 0 18"/></svg>
      </span>
      <span class="forum-icon-tile-name">${escapeHtml(forum.name)}</span>
      ${isAvailable
        ? `<span class="forum-icon-tile-meta">${boardCount} 板块 · BT ${magnetCount} · ED2K ${ed2kCount}</span>`
        : `<span class="forum-icon-tile-meta">待定</span>`}
      ${forum.crawler_registered === false
        ? '<span class="tag tag-pending">爬虫待开发</span>'
        : isEnabled
          ? '<span class="tag tag-active forum-enabled-tag">当前启用</span>'
          : '<span class="tag tag-done">爬虫已接入</span>'}
    </button>
  </div>`;
}

function renderForumActiveSummary() {
  const activeId = cachedSettings.active_forum_id || "sehuatang";
  const forum = cachedForums.find((f) => f.id === activeId);
  if (!forum) return '<span class="hint">未选择启用论坛</span>';
  const crawlerNote = forum.crawler_registered
    ? "调度器将运行该论坛的专用爬虫程序"
    : "该论坛尚无专用爬虫，爬取任务会被跳过";
  return `<span class="tag tag-active">${escapeHtml(forum.name)}</span><span class="forum-active-note">当前启用 · ${escapeHtml(crawlerNote)}</span>`;
}

function rerenderForumIcons() {
  const grid = document.getElementById("forumIconGrid");
  if (!grid || !cachedForums.length) return;
  grid.innerHTML = cachedForums.map((forum) => renderForumIconTile(forum)).join("");
  const summary = document.getElementById("forumActiveSummary");
  if (summary) summary.innerHTML = renderForumActiveSummary();
  applyPermissions();
}

function boardsGroupedByCategory(boards) {
  const groups = new Map();
  for (const board of boards || []) {
    const key = board.category || "其他";
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(board);
  }
  return groups;
}

function crawlStatusForBoard(fid) {
  const board = (cachedBoardCrawl?.boards || []).find((b) => String(b.fid) === String(fid));
  return board || null;
}

function sortedBoardGroups(boards) {
  const order = ["综合讨论区", "原创BT电影"];
  const groups = boardsGroupedByCategory(boards);
  const result = [];
  for (const category of order) {
    if (groups.has(category)) {
      result.push([category, groups.get(category)]);
      groups.delete(category);
    }
  }
  for (const entry of groups.entries()) result.push(entry);
  return result;
}

function boardsInDisplayOrder(forum) {
  const order = cachedForumConfigs[forum.id]?.board_order || cachedBoardCrawl?.board_order || [];
  const boards = [...(forum.boards || [])];
  if (!order.length) {
    return sortedBoardGroups(boards).flatMap(([, items]) => items);
  }
  const byFid = new Map(boards.map((b) => [String(b.fid), b]));
  const sorted = [];
  for (const fid of order) {
    const board = byFid.get(String(fid));
    if (board) sorted.push(board);
    byFid.delete(String(fid));
  }
  for (const board of byFid.values()) sorted.push(board);
  return sorted;
}

function renderForumBoardDetailRows(boards, forumId) {
  const canSort = canManageBoardOrder();
  return (boards || [])
    .map((b) => {
      const crawl = crawlStatusForBoard(b.fid);
      const crawled = crawl?.crawled_thread_count ?? 0;
      return `<tr class="forum-board-row" data-board-fid="${escapeHtml(String(b.fid))}" data-forum-id="${escapeHtml(forumId)}">
        <td class="board-sort-cell">${canSort ? '<span class="board-drag-handle" role="button" tabindex="-1" title="拖拽调整爬取优先级" aria-label="拖拽排序">⋮⋮</span>' : ""}</td>
        <td class="board-col-fid"><code>${escapeHtml(b.fid)}</code></td>
        <td class="board-col-name">${escapeHtml(b.name)}${b.hot ? ' <span class="tag tag-active">热门</span>' : ""}</td>
        <td class="board-col-link">${linkTypeTag(b.primary_link)}</td>
        <td class="board-col-count">${crawl ? escapeHtml(String(crawled)) : "-"}</td>
        <td class="board-col-time">${crawl ? formatTime(crawl.last_crawled_at) : "-"}</td>
      </tr>`;
    })
    .join("");
}

function renderForumBoardsTable(forum) {
  const boards = boardsInDisplayOrder(forum);
  const bodyRows = renderForumBoardDetailRows(boards, forum.id);

  return `<div class="table-wrap forum-boards-table-wrap">
    <table class="data-table settings-table compact forum-boards-table">
      <colgroup>
        <col class="col-sort" />
        <col class="col-fid" />
        <col class="col-name" />
        <col class="col-link" />
        <col class="col-count" />
        <col class="col-time" />
      </colgroup>
      <thead>
        <tr>
          <th class="board-sort-cell"></th>
          <th class="board-col-fid">fid</th>
          <th class="board-col-name">名称</th>
          <th class="board-col-link">主链接</th>
          <th class="board-col-count" title="已爬取帖子数">已爬取</th>
          <th class="board-col-time">上次爬取</th>
        </tr>
      </thead>
      <tbody data-forum-boards="${escapeHtml(forum.id)}">${bodyRows}</tbody>
    </table>
  </div>`;
}

function canManageBoardOrder() {
  return hasPerm("settings.write") || hasPerm("crawl.run");
}

function repositionBoardRow(tbody, row, clientY) {
  const rows = [...tbody.querySelectorAll(".forum-board-row")];
  let insertBefore = null;

  for (const other of rows) {
    if (other === row) continue;
    const rect = other.getBoundingClientRect();
    if (clientY < rect.top + rect.height / 2) {
      insertBefore = other;
      break;
    }
  }

  if (insertBefore) {
    if (row !== insertBefore && row.nextElementSibling !== insertBefore) {
      tbody.insertBefore(row, insertBefore);
      return true;
    }
    return false;
  }

  const last = rows[rows.length - 1];
  if (last && last !== row) {
    tbody.appendChild(row);
    return true;
  }
  return false;
}

function initBoardSortInteractions() {
  if (window.__boardSortReady) return;
  window.__boardSortReady = true;

  document.addEventListener(
    "pointerdown",
    (e) => {
      if (e.button !== 0) return;
      const handle = e.target.closest(".board-drag-handle");
      if (!handle || !canManageBoardOrder()) return;

      const row = handle.closest(".forum-board-row");
      const tbody = row?.closest("tbody[data-forum-boards]");
      if (!row || !tbody) return;

      e.preventDefault();
      e.stopPropagation();

      try {
        handle.setPointerCapture(e.pointerId);
      } catch {
        /* ignore unsupported capture */
      }

      const panel = tbody.closest(".forum-tab-panel");
      boardSortDragState = {
        row,
        tbody,
        panel,
        pointerId: e.pointerId,
        moved: false,
        scrollTop: panel?.scrollTop ?? 0,
      };
      row.classList.add("dragging");
      document.body.classList.add("board-sort-active");
    },
    true,
  );

  document.addEventListener("pointermove", (e) => {
    const state = boardSortDragState;
    if (!state || e.pointerId !== state.pointerId) return;

    e.preventDefault();
    if (repositionBoardRow(state.tbody, state.row, e.clientY)) {
      state.moved = true;
    }
    if (state.panel) {
      state.panel.scrollTop = state.scrollTop;
    }
  });

  const finishBoardDrag = async (e) => {
    const state = boardSortDragState;
    if (!state || e.pointerId !== state.pointerId) return;

    const handle = state.row.querySelector(".board-drag-handle");
    try {
      handle?.releasePointerCapture(e.pointerId);
    } catch {
      /* ignore */
    }

    state.row.classList.remove("dragging");
    document.body.classList.remove("board-sort-active");

    const { moved, tbody } = state;
    boardSortDragState = null;

    if (!moved) return;

    boardSortSuppressClickUntil = Date.now() + 500;
    const forumId = tbody.dataset.forumBoards;
    if (!forumId) return;

    const order = [...tbody.querySelectorAll(".forum-board-row")].map((item) => item.dataset.boardFid);
    try {
      await saveBoardOrder(forumId, order, { silent: true });
    } catch (err) {
      toast(err.message, true);
      if (activeForumId === forumId) {
        await openForumModal(forumId, true);
      }
    }
  };

  document.addEventListener("pointerup", finishBoardDrag);
  document.addEventListener("pointercancel", finishBoardDrag);
}

async function saveBoardOrder(forumId, order, { silent = false } = {}) {
  const data = await api(`/api/forum/${forumId}/board-order`, {
    method: "PUT",
    body: JSON.stringify({ order }),
  });
  cachedForumConfigs[forumId] = {
    ...(cachedForumConfigs[forumId] || {}),
    ...(data.crawler_config || {}),
    board_order: data.board_order || order,
  };
  cachedBoardCrawl = { ...(cachedBoardCrawl || {}), board_order: data.board_order || order };
  const forum = cachedForums.find((f) => f.id === forumId);
  if (forum) {
    forum.crawler_config = { ...(forum.crawler_config || {}), board_order: data.board_order || order };
    forum.boards = sortBoardsByOrder(forum.boards || [], data.board_order || order);
  }
  if (!silent) toast("板块顺序已保存");
}

function sortBoardsByOrder(boards, order) {
  if (!order?.length) return boards;
  const byFid = new Map((boards || []).map((b) => [String(b.fid), b]));
  const sorted = [];
  for (const fid of order) {
    const board = byFid.get(String(fid));
    if (board) sorted.push(board);
    byFid.delete(String(fid));
  }
  for (const board of byFid.values()) sorted.push(board);
  return sorted;
}

function renderForumBoardsTab(forum) {
  return `<div class="forum-tab-content">
    <section class="forum-modal-block forum-boards-block">
      <div class="forum-boards-toolbar">
        <p class="hint">共 ${(forum.boards || []).length} 个白名单板块 · BT ${(forum.boards || []).filter((b) => b.primary_link === "magnet").length} · ED2K ${(forum.boards || []).filter((b) => b.primary_link === "ed2k").length} · 拖拽调整爬取优先级（越靠上越优先）</p>
        <button type="button" class="btn secondary sm board-refresh-btn" data-forum-refresh-boards="${escapeHtml(forum.id)}">
          <span class="btn-spinner" aria-hidden="true"></span>
          <span class="btn-label">刷新已爬取数</span>
        </button>
      </div>
      ${renderForumBoardsTable(forum)}
    </section>
  </div>`;
}

function renderFormatGuideCards(guides) {
  return (guides || [])
      .map(
      (guide) => `<article class="format-guide-card ${guide.primary_link === "ed2k" ? "format-ed2k" : "format-magnet"}">
      <div class="format-guide-head">
        <h4>${escapeHtml(guide.title)}</h4>
        ${linkTypeTag(guide.primary_link)}
      </div>
      <p class="format-guide-summary">${escapeHtml(guide.summary)}</p>
      <div class="format-guide-block">
        <span class="format-guide-label">描述字段</span>
        <ul class="format-guide-list">${(guide.fields || []).map((f) => `<li>${escapeHtml(f)}</li>`).join("")}</ul>
      </div>
      <div class="format-guide-block">
        <span class="format-guide-label">注意事项</span>
        <ul class="format-guide-list muted">${(guide.notes || []).map((n) => `<li>${escapeHtml(n)}</li>`).join("")}</ul>
      </div>
    </article>`
      )
      .join("");
  }

function showForumModalTab(tabId) {
  activeForumTab = tabId;
  const bodyEl = document.getElementById("forumModalBody");
  if (!bodyEl) return;
  bodyEl.querySelectorAll(".forum-tab").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.forumTab === tabId);
  });
  bodyEl.querySelectorAll(".forum-tab-panel").forEach((panel) => {
    panel.classList.toggle("active", panel.dataset.forumTab === tabId);
  });
  if (tabId === "topology" && activeForumId) {
    loadForumTopology(activeForumId).catch((err) => toast(err.message, true));
    startForumTopologyPoll();
  } else {
    stopForumTopologyPoll();
  }
}

const TOPO_BOARD_PHASE = {
  active: { label: "执行中", cls: "tag-active" },
  waiting: { label: "等待", cls: "tag-pending" },
  done: { label: "完成", cls: "tag-done" },
  disabled: { label: "禁用", cls: "tag-disabled" },
  login_required: { label: "需登录", cls: "tag-warn" },
};

function topoRuntimeBadge(data) {
  if (!data.is_active_forum) return '<span class="tag tag-disabled">非当前论坛</span>';
  if (!data.crawler_registered) return '<span class="tag tag-disabled">未接入</span>';
  const rt = data.runtime || {};
  if (rt.running) return '<span class="tag tag-active crawl-topo-pulse">运行中</span>';
  if (rt.enabled) return '<span class="tag tag-pending">待命</span>';
  return '<span class="tag tag-disabled">已关闭</span>';
}

function topoSummaryLine(data) {
  const rt = data.runtime || {};
  const listPages = rt.list_pages_per_board ?? cachedSettings.web_crawler_list_pages_per_board ?? 15;
  const crawled = rt.run_crawled_threads ?? 0;
  const links = rt.run_links_imported ?? 0;
  const parts = ["连续执行", `发帖时间序 · 向前 ${listPages} 页/板`];
  if (rt.running) {
    parts.push(`本轮已处理 ${formatCount(crawled)} 帖`);
    if (links > 0) parts.push(`入库 ${formatCount(links)} 条`);
  }
  if (data.global_pending) parts.push(`待处理 ${formatCount(data.global_pending)}`);
  return parts.join(" · ");
}

function fcProcess(text, sub = "") {
  return `<div class="fc-node fc-process">
    <span class="fc-text">${escapeHtml(text)}</span>
    ${sub ? `<span class="fc-sub">${escapeHtml(sub)}</span>` : ""}
  </div>`;
}

function fcDecision(text) {
  return `<div class="fc-node fc-decision"><span class="fc-text">${escapeHtml(text)}</span></div>`;
}

function fcTerminal(text, sub = "", kind = "muted") {
  return `<div class="fc-node fc-terminal fc-terminal--${kind}">
    <span class="fc-text">${escapeHtml(text)}</span>
    ${sub ? `<span class="fc-sub">${escapeHtml(sub)}</span>` : ""}
  </div>`;
}

function fcArrowDown() {
  return '<div class="fc-arrow fc-arrow-down" aria-hidden="true"></div>';
}

function fcArrowRight() {
  return '<div class="fc-arrow fc-arrow-right" aria-hidden="true"></div>';
}

function fcBranch(label, content, opts = {}) {
  const mainCls = opts.main ? " fc-branch--main" : "";
  return `<div class="fc-branch${mainCls}">
    <div class="fc-branch-stem" aria-hidden="true"></div>
    <span class="fc-branch-label">${escapeHtml(label)}</span>
    <div class="fc-arrow fc-arrow-down fc-arrow-down--sm" aria-hidden="true"></div>
    <div class="fc-branch-body">${content}</div>
  </div>`;
}

function fcBranchTail() {
  return '<div class="fc-branch-tail" aria-hidden="true"></div>';
}

function fcMergeArrowDown() {
  return '<div class="fc-arrow fc-arrow-down fc-arrow-down--merge" aria-hidden="true"></div>';
}

function fcSplitMergeGrid(lanes, options = {}) {
  const isPair = options.pair !== false && lanes.length === 2;
  const pairCls = isPair ? " fc-split-grid--pair" : "";
  const colCls = lanes.length === 3 ? " fc-split-grid--3" : "";
  return `<div class="fc-split-grid fc-split-merge-grid${colCls}${pairCls}">
    <div class="fc-split-bar" aria-hidden="true"></div>
    ${lanes.join("")}
    <div class="fc-merge-bar" aria-hidden="true"></div>
  </div>`;
}

function fcJunction(lanes, options = 0) {
  const opts = typeof options === "number" ? { cols: options || lanes.length } : options;
  const isPair = Boolean(opts.pair || lanes.length === 2);
  const cols = isPair ? 3 : opts.cols || lanes.length;
  const colCls = cols === 3 ? " fc-split-grid--3" : cols === 2 ? " fc-split-grid--2" : "";
  const pairCls = isPair ? " fc-split-grid--pair" : "";
  return `<div class="fc-split-grid${colCls}${pairCls}">
    <div class="fc-split-bar" aria-hidden="true"></div>
    ${lanes.join("")}
  </div>`;
}

function fcSpine(content) {
  return `<div class="fc-spine">${content}</div>`;
}

function renderTopoPipeline(data) {
  const nodes = data.pipeline || [];
  const enabled = !!(data.runtime || {}).enabled;
  return `<div class="fc-hflow" aria-label="总览流程">
    ${nodes
      .map((node, idx) => {
        const statusCls = node.status || "idle";
        const arrow = idx < nodes.length - 1 ? fcArrowRight() : "";
        const showDetail = enabled || node.id === "switch";
        const detail = showDetail && node.detail ? node.detail : "";
        return `<div class="fc-hnode fc-hnode--${statusCls}" title="${escapeHtml(node.detail || "")}">
          <span class="fc-text">${escapeHtml(node.label)}</span>
          ${detail ? `<span class="fc-sub">${escapeHtml(detail)}</span>` : ""}
        </div>${arrow}`;
      })
      .join("")}
  </div>`;
}

function renderThreadImportFlowchart() {
  return `<div class="fc-chart-wrap">
    <div class="fc-legend" aria-hidden="true">
      <span class="fc-legend-item"><i class="fc-legend-shape fc-legend-process"></i>处理步骤</span>
      <span class="fc-legend-item"><i class="fc-legend-shape fc-legend-decision"></i>条件判断</span>
      <span class="fc-legend-item"><i class="fc-legend-shape fc-legend-terminal"></i>流程结果</span>
    </div>
    <p class="fc-chart-hint">对应拓扑 ③扫列表 → ④抓帖 → ⑤入库；磁力板正文无链接时解析 .torrent 附件</p>
    <div class="fc-chart-scroll" aria-label="帖子处理流程，可左右滑动查看">
      <div class="fc-chart">
        ${fcSpine(`
          ${fcProcess("③ 扫列表", "先扫第1页 · 按帖数入队")}
          ${fcArrowDown()}
          ${fcProcess("读取帖子链接", "跳过置顶公告 · 电驴板优先ed2k标题")}
          ${fcArrowDown()}
          ${fcDecision("列表正常？")}
          ${fcArrowDown()}
          ${fcJunction([
            fcBranch("需登录", fcTerminal("标记板块需登录", "永久跳过", "warn")),
            fcBranch("为空", fcTerminal("列表已扫完", "切换下一板块", "muted")),
            fcBranch(
              "正常",
              fcSpine(`
              ${fcProcess("发现新帖写入待处理")}
              ${fcArrowDown()}
              ${fcProcess("④ 抓帖", "访问帖子 · 预览图最多5张")}
              ${fcArrowDown()}
              ${fcDecision("单帖需登录？")}
              ${fcArrowDown()}
              ${fcJunction([
                fcBranch("是", fcTerminal("失败记录", "不入库", "warn")),
                fcBranch(
                  "否",
                  fcSpine(`
                  ${fcDecision("板块类型？")}
                  ${fcArrowDown()}
                  ${fcJunction([
                    fcBranch(
                      "磁力",
                      fcSpine(`
                      ${fcProcess("提取正文 magnet")}
                      ${fcArrowDown()}
                      ${fcDecision("有磁力链接？")}
                      ${fcArrowDown()}
                      ${fcJunction([
                        fcBranch(
                          "是",
                          fcSpine(`${fcProcess("⑤ 入库")}${fcArrowDown()}${fcImportOutcome()}`),
                        ),
                        fcBranch(
                          "否",
                          fcSpine(`
                          ${fcProcess("筛选 torrent 附件", "最多 3 个 · Playwright")}
                          ${fcArrowDown()}
                          ${fcDecision("可下载并解析？")}
                          ${fcArrowDown()}
                          ${fcJunction([
                            fcBranch("否", fcTerminal("失败记录", "无链接 · 不入库", "warn")),
                            fcBranch(
                              "是",
                              fcSpine(`
                              ${fcProcess("种子 → magnet", "解析 infohash 入库")}
                              ${fcArrowDown()}
                              ${fcProcess("⑤ 入库")}
                              ${fcArrowDown()}
                              ${fcImportOutcome()}
                            `),
                              { main: true },
                            ),
                          ], { pair: true })}
                        `),
                          { main: true },
                        ),
                      ], { pair: true })}
                    `),
                    ),
                    fcBranch(
                      "电驴",
                      fcSpine(`
                      ${fcDecision("正文有电驴链接？")}
                      ${fcArrowDown()}
                      ${fcJunction([
                        fcBranch(
                          "是",
                          fcSpine(`${fcProcess("仅用正文")}${fcArrowDown()}${fcProcess("⑤ 入库")}${fcArrowDown()}${fcImportOutcome()}`),
                        ),
                        fcBranch(
                          "否",
                          fcSpine(`
                          ${fcDecision("需回复可见？")}
                          ${fcArrowDown()}
                          ${fcJunction([
                            fcBranch("是", fcTerminal("需回复贴", "占位入库", "warn")),
                            fcBranch(
                              "否",
                              fcSpine(`
                              ${fcProcess("筛选尾部附件", "文本/压缩包 · 最多3个")}
                              ${fcArrowDown()}
                              ${fcDecision("浏览器可下载？")}
                              ${fcArrowDown()}
                              ${fcJunction([
                                fcBranch("否", fcTerminal("无下载权限", "占位入库", "warn")),
                                fcBranch(
                                  "是",
                                  fcSpine(`${fcProcess("⑤ 入库")}${fcArrowDown()}${fcImportOutcome()}`),
                                  { main: true },
                                ),
                              ], { pair: true })}
                            `),
                              { main: true },
                            ),
                          ], { pair: true })}
                        `),
                          { main: true },
                        ),
                      ], { pair: true })}
                    `),
                      { main: true },
                    ),
                  ], { pair: true })}
                `),
                  { main: true },
                ),
              ], { pair: true })}
            `),
              { main: true },
            ),
          ], 3)}
        `)}
      </div>
    </div>
  </div>`;
}

function fcImportOutcome() {
  return fcJunction([
    fcBranch("成功", fcTerminal("资源入库", "1条主资源+全部同类型链接", "ok"), { main: true }),
    fcBranch("失败/异常", fcTerminal("保留待处理", "下轮重试", "warn")),
  ], { pair: true });
}

function topoBoardQueueStats(data) {
  const boards = data.boards || [];
  const active = boards.filter((b) => b.phase === "active").length;
  const done = boards.filter((b) => b.phase === "done").length;
  const pending = boards.reduce((sum, b) => sum + (b.pending_count || 0), 0);
  return { total: boards.length, active, done, pending };
}

function renderTopoBoardQueueModalBody(data) {
  const boards = data.boards || [];
  const stats = topoBoardQueueStats(data);
  if (!boards.length) return '<p class="hint">暂无板块数据</p>';

  const rows = boards
    .map((board, idx) => {
      const phase = TOPO_BOARD_PHASE[board.phase] || TOPO_BOARD_PHASE.waiting;
      const rowCls = board.phase === "active" ? " is-active" : "";
      return `<tr class="topo-board-row${rowCls}">
        <td>${idx + 1}</td>
        <td><strong>${escapeHtml(board.name)}</strong></td>
        <td><code>${escapeHtml(board.fid)}</code></td>
        <td>${linkTypeTag(board.primary_link || "failed")}</td>
        <td><span class="tag ${phase.cls}">${phase.label}</span></td>
        <td>P${board.last_list_page || 0}${board.list_exhausted ? " · 已到底" : ""}</td>
        <td>${formatCount(board.pending_count || 0)}</td>
        <td>${formatCount(board.crawled_thread_count || 0)}</td>
        <td>${board.last_crawled_at ? formatTime(board.last_crawled_at) : "-"}</td>
      </tr>`;
    })
    .join("");

  return `<div class="topo-board-queue-summary">
    <span>共 ${stats.total} 个板块</span>
    <span>执行中 ${stats.active}</span>
    <span>已完成 ${stats.done}</span>
    <span>待处理帖 ${formatCount(stats.pending)}</span>
    ${data.active_board_name ? `<span class="topo-board-queue-current">当前 · ${escapeHtml(data.active_board_name)}</span>` : ""}
  </div>
  <p class="hint topo-board-queue-hint">顺序与「板块列表」拖拽一致；list_exhausted 且无 pending 后进入下一板块；同批内先 pending → 扫列表 → 新帖。</p>
  <div class="table-wrap">
    <table class="data-table settings-table compact topo-board-queue-table">
      <thead>
        <tr>
          <th>#</th>
          <th>板块</th>
          <th>FID</th>
          <th>类型</th>
          <th>状态</th>
          <th>列表进度</th>
          <th>待处理</th>
          <th>已爬</th>
          <th>最近爬取</th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>
  </div>`;
}

function openBoardQueueModal() {
  const body = document.getElementById("forumBoardQueueBody");
  if (!body || !cachedForumTopology) return;
  body.innerHTML = renderTopoBoardQueueModalBody(cachedForumTopology);
  openModal("forumBoardQueueModal");
}

function refreshBoardQueueModal() {
  const modal = document.getElementById("forumBoardQueueModal");
  if (!modal || modal.hidden || !cachedForumTopology) return;
  const body = document.getElementById("forumBoardQueueBody");
  if (body) body.innerHTML = renderTopoBoardQueueModalBody(cachedForumTopology);
}

function renderForumTopologyContent(data) {
  const activeName = data.active_board_name;
  const queueStats = topoBoardQueueStats(data);
  return `<div class="forum-tab-content crawl-topology">
    <div class="crawl-topo-head">
      <div class="crawl-topo-head-main">
        ${topoRuntimeBadge(data)}
        <span class="crawl-topo-summary">${escapeHtml(topoSummaryLine(data))}</span>
        ${activeName ? `<span class="crawl-topo-current">当前 · ${escapeHtml(activeName)}</span>` : ""}
      </div>
      <div class="crawl-topo-head-actions">
        <button type="button" class="btn ghost sm" data-open-board-queue>板块队列 · ${queueStats.total}</button>
        <button type="button" class="btn ghost sm" data-forum-topology-refresh>刷新</button>
      </div>
    </div>
    <div class="crawl-topo-section">
      <div class="crawl-topo-section-title">总览 Pipeline</div>
      <p class="hint crawl-topo-pipeline-hint">与爬虫配置五步对应：开关 → 调度 → 选板 → 扫列表 → 抓帖 → 入库</p>
      ${renderTopoPipeline(data)}
    </div>
    <div class="crawl-topo-section crawl-topo-section--flowchart">
      <div class="crawl-topo-section-title">帖子处理流程</div>
      ${renderThreadImportFlowchart()}
    </div>
  </div>`;
}

function renderForumTopologyError(message) {
  return `<div class="forum-tab-content crawl-topology">
    <div class="crawl-topo-error">
      <p>加载失败</p>
      <p class="hint">${escapeHtml(message || "请重启收集器后重试")}</p>
      <button type="button" class="btn secondary sm" data-forum-topology-refresh>重试</button>
    </div>
  </div>`;
}

function renderForumTopologyTab(forum) {
  if (forum.status !== "active") {
    return '<div class="settings-empty"><p>论坛尚未接入</p></div>';
  }
  if (!forum.crawler_registered) {
    return '<div class="settings-empty"><p>暂无爬虫程序</p></div>';
  }
  if (cachedForumTopology && cachedForumTopology.forum_id === forum.id) {
    return renderForumTopologyContent(cachedForumTopology);
  }
  return `<div class="forum-tab-content crawl-topology crawl-topology-loading"><p class="hint">加载中…</p></div>`;
}

function captureTopologyScroll(panel) {
  if (!panel) return null;
  const chartScroll = panel.querySelector(".fc-chart-scroll");
  return {
    panelTop: panel.scrollTop,
    panelLeft: panel.scrollLeft,
    chartTop: chartScroll?.scrollTop ?? 0,
    chartLeft: chartScroll?.scrollLeft ?? 0,
  };
}

function restoreTopologyScroll(panel, state) {
  if (!panel || !state) return;
  const apply = () => {
    panel.scrollTop = state.panelTop;
    panel.scrollLeft = state.panelLeft;
    const chartScroll = panel.querySelector(".fc-chart-scroll");
    if (chartScroll) {
      chartScroll.scrollTop = state.chartTop;
      chartScroll.scrollLeft = state.chartLeft;
    }
  };
  apply();
  requestAnimationFrame(apply);
}

function renderForumTopologyPanel(panel, data) {
  const scroll = captureTopologyScroll(panel);
  panel.innerHTML = renderForumTopologyContent(data);
  restoreTopologyScroll(panel, scroll);
}

async function loadForumTopology(forumId, silent = false) {
  try {
    const data = await api(`/api/forum/${encodeURIComponent(forumId)}/crawl-topology`);
    cachedForumTopology = data;
    if (activeForumId !== forumId || activeForumTab !== "topology") return data;
    const panel = document.querySelector('.forum-tab-panel[data-forum-tab="topology"]');
    if (panel) renderForumTopologyPanel(panel, data);
    refreshBoardQueueModal();
    if (!silent) applyPermissions();
    return data;
  } catch (err) {
    if (activeForumId === forumId && activeForumTab === "topology") {
      const panel = document.querySelector('.forum-tab-panel[data-forum-tab="topology"]');
      if (panel) {
        const scroll = captureTopologyScroll(panel);
        panel.innerHTML = renderForumTopologyError(err.message);
        restoreTopologyScroll(panel, scroll);
      }
    }
    if (!silent) throw err;
    return null;
  }
}

function startForumTopologyPoll() {
  stopForumTopologyPoll();
  forumTopologyTimer = setInterval(() => {
    if (activeForumTab !== "topology" || !activeForumId) return;
    loadForumTopology(activeForumId, true).catch(() => {});
  }, 4000);
}

function stopForumTopologyPoll() {
  if (forumTopologyTimer) {
    clearInterval(forumTopologyTimer);
    forumTopologyTimer = null;
  }
}

function renderForumConfigSummary(forum) {
  const cfg = forum.crawler_config || cachedForumConfigs[forum.id] || {};
  const enabled = cfg.web_crawler_enabled ?? true;
  const listPages = cfg.web_crawler_list_pages_per_board ?? 15;
  const entry = cfg.web_crawl_urls || forum.base_url || "-";
  return `<div class="forum-config-summary">
    <div class="forum-config-summary-item"><span class="lbl">爬虫状态</span><span class="val">${enabled ? '<span class="tag tag-active">已启用</span>' : '<span class="tag tag-disabled">已关闭</span>'}</span></div>
    <div class="forum-config-summary-item"><span class="lbl">调度模式</span><span class="val">连续执行 · 按列表页数控制范围</span></div>
    <div class="forum-config-summary-item"><span class="lbl">扫列表</span><span class="val">发帖时间序 · 每批向前 ${listPages} 页</span></div>
    <div class="forum-config-summary-item"><span class="lbl">入库</span><span class="val">每帖 1 主资源 · 全链接合并 · 不拦结构化简介</span></div>
    <div class="forum-config-summary-item full"><span class="lbl">入口 URL</span><span class="val mono">${escapeHtml(entry)}</span></div>
  </div>`;
}

function renderForumOverviewTab(forum) {
  const boards = forum.boards || [];
  const magnetCount = boards.filter((b) => b.primary_link === "magnet").length;
  const ed2kCount = boards.filter((b) => b.primary_link === "ed2k").length;

  return `
    <div class="forum-modal-stats">
      <div class="forum-stat-pill"><span class="forum-stat-val">${boards.length}</span><span class="forum-stat-lbl">白名单板块</span></div>
      <div class="forum-stat-pill"><span class="forum-stat-val">${magnetCount}</span><span class="forum-stat-lbl">BT 板块</span></div>
      <div class="forum-stat-pill"><span class="forum-stat-val">${ed2kCount}</span><span class="forum-stat-lbl">ED2K 板块</span></div>
      <div class="forum-stat-pill"><span class="forum-stat-val">${(forum.skip_categories || []).length}</span><span class="forum-stat-lbl">跳过分区</span></div>
    </div>
    <div class="forum-tab-content">
      <section class="forum-modal-block">
        <div class="forum-block-head-inline">
          <h4>当前配置</h4>
          <button type="button" class="btn ghost sm" data-forum-goto-tab="config">编辑爬虫配置</button>
        </div>
        ${renderForumConfigSummary(forum)}
      </section>
      <section class="forum-modal-block">
        <div class="forum-block-head-inline">
          <h4>执行流程</h4>
          <button type="button" class="btn ghost sm" data-forum-goto-tab="topology">查看拓扑</button>
        </div>
        <p class="hint">开关 → 连续调度 → 选板 → 扫列表 → 抓帖 → 入库。配置页按 ①调度 · ②列表 · ③抓帖 · ④入库 分组，与拓扑 Pipeline 一致。</p>
      </section>
      <section class="forum-modal-block">
        <h4>专用爬虫</h4>
        <p class="hint">${forum.crawler_registered
          ? `已接入独立爬虫模块 <code>${escapeHtml(forum.crawler_module || `workers.crawlers.${forum.id}`)}</code>，启用本论坛后将运行此程序（不可与其他论坛复用）。`
          : "该论坛尚无专用爬虫程序，启用后爬取任务会被跳过。"}</p>
      </section>
      <section class="forum-modal-block">
        <h4>爬取策略</h4>
        ${renderForumPolicyList(forum)}
      </section>
      ${(forum.category_summary || []).length
        ? `<section class="forum-modal-block">
        <h4>大分区概览</h4>
        <div class="category-summary-grid">
          ${forum.category_summary
            .map(
              (cat) => `<div class="category-summary-card">
            <strong>${escapeHtml(cat.name)}</strong>
            <span>${cat.board_count} 个板块 · 热门 ${cat.hot_boards}</span>
            <span>${cat.primary_link === "magnet" ? "磁力为主" : cat.primary_link === "ed2k" ? "ED2K 为主" : escapeHtml(cat.primary_link)}</span>
          </div>`
            )
            .join("")}
        </div>
      </section>`
        : ""}
      ${(forum.technical_notes || []).length
        ? `<section class="forum-modal-block">
        <h4>技术备忘</h4>
        <ul class="forum-policy-list">${forum.technical_notes.map((n) => `<li>${escapeHtml(n)}</li>`).join("")}</ul>
      </section>`
        : ""}
    </div>`;
}

function renderResourceFormatSpec(fields) {
  return `<ol class="resource-format-spec">
    ${(fields || [])
      .map(
        (field) => `<li class="resource-format-item">
        <span class="resource-format-no">${field.no}</span>
        <div class="resource-format-body">
          <strong>${escapeHtml(field.name)}</strong>${field.note ? `<span class="resource-format-note"> · ${escapeHtml(field.note)}</span>` : ""}
        </div>
      </li>`
      )
      .join("")}
  </ol>`;
}

function renderForumFormatTab(forum) {
  const fields = forum.resource_format || DEFAULT_RESOURCE_FORMAT;
  return `<div class="forum-tab-content forum-tab-content-compact">
    <section class="forum-format-block">
      <h4>资源格式说明</h4>
      <p class="hint">入库目标共 8 项；文件大小从正文优先解析，不硬性要求结构化简介标签。</p>
      <div class="resource-format-panel">${renderResourceFormatSpec(fields)}</div>
    </section>
    ${(forum.format_guides || []).length
      ? `<section class="forum-format-block">
      <h4>板块解析差异</h4>
      <p class="hint">不同大分区帖子的描述字段与链接提取方式不同，爬虫需按板块类型分别解析。</p>
      <div class="format-guide-grid format-guide-grid-compact">${renderFormatGuideCards(forum.format_guides)}</div>
    </section>`
      : ""}
  </div>`;
}

const DEFAULT_RESOURCE_FORMAT = [
  { no: 1, name: "标题", note: "" },
  { no: 2, name: "文件大小", note: "帖子内容 → 标题 → 资源链接，命中即停" },
  { no: 3, name: "预览图", note: "最多 5 张" },
  { no: 4, name: "来源论坛名", note: "" },
  { no: 5, name: "来源板块名", note: "" },
  { no: 6, name: "magnet 或 ED2K 链接", note: "" },
  { no: 7, name: "帖子原链接", note: "" },
  { no: 8, name: "资源解压密码", note: "如有则解析入库，无则留空" },
];

function renderForumConfigTab(forum) {
  const field = (label, inputHtml, hint = "", extraClass = "") =>
    `<label class="forum-field-block${extraClass ? ` ${extraClass}` : ""}">
      <span class="forum-field-label">${label}</span>
      ${inputHtml}
      ${hint ? `<small class="field-hint">${hint}</small>` : `<small class="field-hint" aria-hidden="true">&nbsp;</small>`}
    </label>`;

  const switchField = (label, key, hint = "", opts = {}) => {
    const attrs = [
      'type="checkbox"',
      `data-forum-key="${key}"`,
      'class="forum-field"',
      opts.checked ? "checked" : "",
      opts.disabled ? "disabled" : "",
      opts.keepDisabled ? "data-keep-disabled" : "",
      opts.title ? `title="${escapeHtml(opts.title)}"` : "",
    ]
      .filter(Boolean)
      .join(" ");
    return `<label class="forum-field-block forum-field-block--switch">
      <span class="forum-field-label">${label}</span>
      <div class="forum-field-control"><input ${attrs} /></div>
      ${hint ? `<small class="field-hint">${hint}</small>` : `<small class="field-hint" aria-hidden="true">&nbsp;</small>`}
    </label>`;
  };

  return `<div class="forum-tab-content">
    <form class="forum-config-form form-grid" data-forum-form="${escapeHtml(forum.id)}">
      <section class="forum-modal-block forum-config-step">
        <div class="forum-config-step-head">
          <span class="forum-config-step-badge">①</span>
          <div>
            <h4>调度与限速</h4>
            <p class="field-hint">连续执行；本批处理帖数/入库数在活动栏实时显示。列表扫描范围见下方②。</p>
          </div>
        </div>
        <div class="settings-grid-3 forum-config-grid">
          ${field("目标入库数", '<input type="number" min="0" max="10000" data-forum-key="web_crawler_target_imports" class="forum-field" />', "0 = 不限，达上限停止本批")}
          ${field("请求延迟（秒）", '<input type="number" min="0.5" max="60" step="0.5" data-forum-key="web_crawler_request_delay" class="forum-field" />', "帖间基准延迟，默认 2s")}
          ${field("连续失败阈值", '<input type="number" min="2" max="20" data-forum-key="web_crawler_fetch_failure_threshold" class="forum-field" />', "连续浏览器失败达此次数后进入冷却（刷新会话+暂停），默认 5")}
          ${field("失败冷却（秒）", '<input type="number" min="15" max="600" data-forum-key="web_crawler_fetch_cooldown_seconds" class="forum-field" />', "触发冷却后暂停时长，默认 45s")}
          ${field("每轮最大冷却", '<input type="number" min="1" max="10" data-forum-key="web_crawler_fetch_max_cooldowns" class="forum-field" />', "一轮内冷却仍无成功才熔断，默认 3")}
          ${field("AutoThrottle 上限（秒）", '<input type="number" min="5" max="300" step="1" data-forum-key="web_crawler_autothrottle_max_delay" class="forum-field" />', "失败率升高时动态延迟上限，默认 60s")}
          ${field("AutoThrottle 采样窗口", '<input type="number" min="5" max="100" data-forum-key="web_crawler_autothrottle_window" class="forum-field" />', "统计近 N 次请求成功率，默认 20")}
        </div>
      </section>
      <section class="forum-modal-block forum-config-step">
        <div class="forum-config-step-head">
          <span class="forum-config-step-badge">②</span>
          <div>
            <h4>扫列表</h4>
            <p class="field-hint">「立即爬取」与连续调度相同：只深扫。手动「扫新帖」从第 1 页扫到上限；连续 N 页全已知则提前结束。</p>
          </div>
        </div>
        <div class="settings-grid-2 forum-config-grid">
          ${field("列表页数 / 批", '<input type="number" min="1" max="100" data-forum-key="web_crawler_list_pages_per_board" class="forum-field" />', "深扫每轮翻 N 页，下轮从游标续扫直到板底；默认 15")}
          ${field("扫新帖上限（全局）", '<input type="number" min="1" max="200" data-forum-key="web_crawler_manual_head_pages" class="forum-field" />', "手动扫新帖最多翻 N 页；默认 20")}
          ${field("扫新帖早停页数", '<input type="number" min="1" max="10" data-forum-key="web_crawler_list_known_stop_pages" class="forum-field" />', "连续 N 页所见均已入库则结束扫新帖，默认 2")}
          ${field("首页捕新上限（已废弃）", '<input type="number" min="1" max="100" data-forum-key="web_crawler_list_head_pages" class="forum-field" />', "原每日自动捕新；现请用「扫新帖上限」")}
          ${field("全局列表页上限", '<input type="number" min="0" max="50000" data-forum-key="web_crawler_max_list_pages" class="forum-field" />', "页码硬顶：0=不限制；>0 时本轮配额也不超过该值")}
        </div>
        <p class="field-hint forum-config-note">每板覆盖写入 board_manual_head_pages（如板 95→30）。网友原创区（141）仅入队发帖已满 3 天的帖，未满龄跳过。</p>
      </section>
      <section class="forum-modal-block forum-config-step">
        <div class="forum-config-step-head">
          <span class="forum-config-step-badge">③</span>
          <div>
            <h4>抓帖与连接</h4>
            <p class="field-hint">magnet 板优先正文 magnet；无链接时 Playwright 下载 .torrent 解析为 magnet。ed2k 板正文无 ed2k 时下载 txt/zip/rar（最多 3 个）。仅登录/回复/无权下载/需购买贴占位入库；其余异常保留 pending 重试。</p>
          </div>
        </div>
        <div class="settings-grid-2 forum-config-grid">
          ${field("入口 URL", '<input type="text" data-forum-key="web_crawl_urls" class="forum-field" placeholder="https://www.sehuatang.net/forum.php" />')}
          ${field("请求超时（秒）", '<input type="number" min="5" max="300" data-forum-key="web_crawler_timeout" class="forum-field" />', "单次浏览器/HTTP 请求上限")}
          ${field("Playwright 重试", '<input type="number" min="1" max="10" data-forum-key="web_crawler_fetch_retries" class="forum-field" />', "单次请求失败时的重试次数")}
          ${field("单帖超时（秒）", '<input type="number" min="0" max="900" data-forum-key="web_crawler_thread_timeout" class="forum-field" />', "0 = 不限；超时后跳过该帖，留待下轮重试，默认 120")}
          ${field("User-Agent", '<input type="text" data-forum-key="web_crawler_ua" class="forum-field" />', "", "forum-field-block--full")}
          ${field(
            "论坛 Cookie",
            '<textarea rows="4" data-forum-key="web_crawler_cookie" class="forum-field forum-cookie-field" spellcheck="false" placeholder="safe=1; bbs_sid=...; 粘贴浏览器完整 Cookie"></textarea>',
            "浏览器登录后 F12 → Application → Cookies 复制全部，或 Network 请求头里的 Cookie。用于 18+ 验证与破解软文拦截；修改后请重启爬虫",
            "forum-field-block--full"
          )}
        </div>
        <p class="field-hint forum-config-note">HTTP 代理在侧边栏「通用配置」中设置。</p>
      </section>
      <section class="forum-modal-block forum-config-step">
        <div class="forum-config-step-head">
          <span class="forum-config-step-badge">④</span>
          <div>
            <h4>入库</h4>
            <p class="field-hint">每帖 1 条主资源，同帖全部同类型链接写入 ed2k_links；文件大小从正文 → 标题 → 链接解析；解析失败保留 pending。</p>
          </div>
        </div>
        <div class="forum-config-grid forum-config-grid--single">
          ${switchField("每帖只入一条主资源", "web_crawler_one_link_per_thread", "同帖全部链接写入 ed2k_links 字段", { checked: true, disabled: true, keepDisabled: true, title: "已定稿规则，暂不可关闭" })}
        </div>
      </section>
      <details class="forum-config-advanced">
        <summary>高级选项</summary>
        <div class="forum-config-advanced-body">
          <div class="settings-grid-3 forum-config-grid">
            ${switchField("自动发现板块", "web_crawler_auto_discover", "建议关闭，仅用白名单板块")}
            ${field("板块刷新（小时）", '<input type="number" min="1" max="168" data-forum-key="web_crawler_board_refresh_hours" class="forum-field" />', "auto_discover 开启时重新发现")}
            ${field("间隔（分钟）", '<input type="number" min="1" max="1440" data-forum-key="web_crawler_interval_minutes" class="forum-field" />', "每轮有抓取工作后，等待多久再开始下一轮")}
          </div>
          <input type="hidden" data-forum-key="web_crawler_require_structured_desc" value="false" />
          <p class="field-hint forum-config-note">结构化简介不再硬性拦截入库。</p>
        </div>
      </details>
      <div class="forum-modal-foot">
        <button type="submit" class="btn primary forum-save-btn">保存论坛配置</button>
      </div>
    </form>
  </div>`;
}

function renderForumModalContent(forum) {
  if (forum.status !== "active") {
    return `<div class="settings-empty">
      <p>${escapeHtml((forum.policies || [])[0] || "该论坛尚未接入")}</p>
    </div>`;
  }

  const tabs = [
    { id: "overview", label: "概览" },
    { id: "format", label: "资源格式" },
    { id: "boards", label: "板块列表" },
    { id: "topology", label: "执行拓扑" },
    { id: "config", label: "爬虫配置" },
  ];

  return `
    <nav class="forum-tab-nav" role="tablist">
      ${tabs
        .map(
          (tab) => `<button type="button" class="forum-tab ${tab.id === activeForumTab ? "active" : ""}" role="tab" data-forum-tab="${tab.id}" aria-selected="${tab.id === activeForumTab}">
        ${escapeHtml(tab.label)}
      </button>`
        )
        .join("")}
    </nav>
    <div class="forum-tab-panels">
      <div class="forum-tab-panel ${activeForumTab === "overview" ? "active" : ""}" data-forum-tab="overview" role="tabpanel">${renderForumOverviewTab(forum)}</div>
      <div class="forum-tab-panel ${activeForumTab === "format" ? "active" : ""}" data-forum-tab="format" role="tabpanel">${renderForumFormatTab(forum)}</div>
      <div class="forum-tab-panel ${activeForumTab === "boards" ? "active" : ""}" data-forum-tab="boards" role="tabpanel">${renderForumBoardsTab(forum)}</div>
      <div class="forum-tab-panel ${activeForumTab === "topology" ? "active" : ""}" data-forum-tab="topology" role="tabpanel">${renderForumTopologyTab(forum)}</div>
      <div class="forum-tab-panel ${activeForumTab === "config" ? "active" : ""}" data-forum-tab="config" role="tabpanel">${renderForumConfigTab(forum)}</div>
    </div>`;
}

function renderForumModalHead(forum) {
  const isEnabled = (cachedSettings.active_forum_id || "sehuatang") === forum.id;
  return `<div class="forum-modal-title">
    <span class="forum-card-icon" aria-hidden="true">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="9"/><path d="M2 12h20M12 3a15 15 0 0 1 0 18M12 3a15 15 0 0 0 0 18"/></svg>
    </span>
    <div>
      <h3>${escapeHtml(forum.name)}</h3>
      <p class="forum-card-url">${escapeHtml(forum.base_url || "")}</p>
    </div>
    ${isEnabled ? '<span class="tag tag-active">当前启用</span>' : forumStatusTag(forum.status)}
  </div>`;
}

async function openForumModal(forumId, refreshOnly = false) {
  const forum = cachedForums.find((f) => f.id === forumId);
  if (!forum) return;

  activeForumId = forumId;
  if (!refreshOnly) cachedForumTopology = null;
  try {
    cachedBoardCrawl = await api("/api/boards");
  } catch {
    cachedBoardCrawl = cachedBoardCrawl || { boards: [] };
  }

  const headEl = document.getElementById("forumModalHead");
  const bodyEl = document.getElementById("forumModalBody");
  if (!headEl || !bodyEl) return;

  headEl.innerHTML = renderForumModalHead(forum);
  bodyEl.innerHTML = renderForumModalContent(forum);

  const form = bodyEl.querySelector(".forum-config-form");
  if (form) {
    const cfg = forum.crawler_config || cachedForumConfigs[forum.id] || {};
    fillForumConfigForm(form, cfg);
  }
  applyPermissions();

  if (!refreshOnly) {
    activeForumTab = "overview";
    openModal("forumConfigModal");
  } else {
    showForumModalTab(activeForumTab);
  }
  if (activeForumTab === "topology") {
    loadForumTopology(forumId, true).catch(() => {});
    startForumTopologyPoll();
  }
}

function truncateText(text, max = 48) {
  const s = (text || "").trim();
  if (!s) return "-";
  return s.length > max ? `${s.slice(0, max)}…` : s;
}

function processingOutcome(item) {
  if (!item) return "-";
  if (item.outcome) return item.outcome;
  if (item.link_kind === "stub") {
    const desc = (item.description || "").trim();
    const match = desc.match(/^【([^】]+)】/);
    return match ? match[1] : "占位入库";
  }
  if (item.link_kind === "magnet" || item.link_kind === "ed2k") {
    const n = item.ed2k_count || detailResourceLinks(item).length || 1;
    return `成功入库 ${n} 条资源`;
  }
  if (item.link_kind === "skipped") return "已跳过";
  if (item.link_kind === "failed") return item.last_error || "处理失败";
  return "-";
}

function processingStatusLabel(item) {
  if (!item) return "-";
  if (item.link_kind === "stub") return "占位";
  if (item.link_kind === "skipped") return "跳过";
  if (item.link_kind === "failed") return "失败";
  if (item.link_kind === "magnet" || item.link_kind === "ed2k") return "成功";
  if (item.source_type === "upload") return "人工导入";
  if (item.source_type === "telegram") return "TG 入库";
  return item.link_kind || "-";
}

function renderVerdictBanner(item) {
  const status = processingStatusLabel(item);
  const statusClass = {
    成功: "verdict-ok",
    占位: "verdict-stub",
    跳过: "verdict-skipped",
    失败: "verdict-failed",
  }[status] || "verdict-neutral";
  return `<div class="verdict-banner ${statusClass}">
    <span class="verdict-banner-status">${escapeHtml(status)}</span>
    ${linkTypeTag(item.link_kind || item.source_type)}
  </div>`;
}

function renderProcessingMetaRows(item) {
  const rows = [];
  const outcome = processingOutcome(item);
  rows.push(
    `<div class="detail-field full"><span class="lbl">判定原因</span><span class="val verdict-reason">${escapeHtml(outcome)}</span></div>`
  );
  if (item.status && item.source_type === "web") {
    rows.push(
      `<div class="detail-field"><span class="lbl">爬取状态</span><span class="val">${escapeHtml(item.status)}</span></div>`
    );
  }
  if (item.ed2k_count != null && item.source_type === "web") {
    rows.push(
      `<div class="detail-field"><span class="lbl">链接数</span><span class="val">${Number(item.ed2k_count) || 0}</span></div>`
    );
  }
  if (item.last_error) {
    rows.push(
      `<div class="detail-field full"><span class="lbl">技术错误</span><span class="val mono verdict-error">${escapeHtml(item.last_error)}</span></div>`
    );
  }
  const pageTitle = (item.title || item.filename || "").trim();
  const listTitle = (item.list_title || "").trim();
  if (listTitle && listTitle !== pageTitle) {
    rows.push(
      `<div class="detail-field full"><span class="lbl">列表页标题</span><span class="val">${escapeHtml(listTitle)}</span></div>`
    );
  }
  if (pageTitle) {
    rows.push(
      `<div class="detail-field full"><span class="lbl">页面标题</span><span class="val">${escapeHtml(pageTitle)}</span></div>`
    );
  }
  return rows.join("");
}

function resourceId(item) {
  return item?.hash || item?.id || "";
}

function isThreadRecord(item) {
  return item?.record_type === "thread";
}

function isStubResource(item) {
  return item?.link_kind === "stub" || String(item?.ed2k_link || "").startsWith("unavailable://");
}

function isSkippedRecord(item) {
  return item?.link_kind === "skipped";
}

function isFailedResource(item) {
  return item?.link_kind === "failed";
}

function resourceTypeLabel(item) {
  if (isThreadRecord(item) || item?.source_type === "web") {
    return linkTypeTag(item.link_kind || "failed");
  }
  return escapeHtml(sourceTypeLabel(item.source_type));
}

function forumDisplayName(forumId) {
  const names = { sehuatang: "色花堂", other: "其他论坛" };
  return names[forumId] || forumId || "-";
}

function parseDescriptionField(description, label) {
  if (!description) return "";
  const re = new RegExp(`【${label}】[：:]?\\s*(.+?)(?=\\n|$)`, "m");
  const match = description.match(re);
  return match ? match[1].trim() : "";
}

function boardNameFromFid(fid, forumId = "sehuatang") {
  if (!fid) return "";
  const forum = cachedForums.find((f) => f.id === forumId);
  const board = forum?.boards?.find((b) => String(b.fid) === String(fid));
  return board?.name || "";
}

function resolveForumName(item) {
  if (!item) return "-";
  if (item.source_type === "telegram") return "Telegram";
  if (item.source_type === "upload") return "人工导入";
  const fromDesc = parseDescriptionField(item.description, "来源论坛名");
  if (fromDesc) return fromDesc;
  if (item.forum_id) {
    const cached = cachedForums.find((f) => f.id === item.forum_id);
    if (cached?.name) return cached.name;
    return forumDisplayName(item.forum_id);
  }
  const url = item.source_url || "";
  if (/sehuatang/i.test(url)) return "色花堂";
  if (item.source_name && item.source_type === "web") return item.source_name;
  return "-";
}

function resolveBoardName(item) {
  if (!item) return "-";
  const fromDesc = parseDescriptionField(item.description, "来源板块名");
  if (fromDesc) return fromDesc;
  if (item.board_name) return item.board_name;
  if (item.board_fid) {
    const name = boardNameFromFid(item.board_fid, item.forum_id || "sehuatang");
    if (name) return name;
    return `板块 fid=${item.board_fid}`;
  }
  const fidMatch = (item.source_url || "").match(/forum-(\d+)-/);
  if (fidMatch) {
    const name = boardNameFromFid(fidMatch[1], item.forum_id || "sehuatang");
    if (name) return name;
  }
  if (item.source_type !== "web" && item.source_name) return item.source_name;
  return "-";
}

function detailDisplayTitle(item) {
  return item?.title || item?.filename || "-";
}

function detailResourceLinks(item) {
  const main = item?.ed2k_link || item?.magnet_url || "";
  const all = Array.isArray(item?.ed2k_links) ? item.ed2k_links.filter(Boolean) : [];
  if (!all.length && main) all.push(main);
  const seen = new Set();
  return all.filter((link) => {
    if (!link || seen.has(link)) return false;
    seen.add(link);
    return true;
  });
}

function renderDetailPreviewImages(images) {
  if (!images?.length) return "";
  return `<div class="detail-field full">
    <span class="lbl">预览图</span>
    <div class="detail-preview-grid">
      ${images
        .map(
          (url) =>
            `<a href="${escapeHtml(url)}" target="_blank" rel="noopener" class="detail-preview-item"><img src="${escapeHtml(url)}" alt="预览图" loading="lazy" /></a>`
        )
        .join("")}
    </div>
  </div>`;
}

function formatCount(n) {
  const num = Number(n) || 0;
  return num.toLocaleString("zh-CN");
}

const FILTER_SVG = {
  chevron: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M6 9l6 6 6-6"/></svg>',
  check: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><path d="M5 12l4 4L19 6"/></svg>',
  source: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 7h16M4 12h10M4 17h16"/></svg>',
  category: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20.59 13.41l-7.17 7.17a2 2 0 0 1-2.83 0L2 12V2h10l8.59 8.59a2 2 0 0 1 0 2.82z"/><circle cx="7" cy="7" r="1.5" fill="currentColor" stroke="none"/></svg>',
  forum: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="9"/><path d="M2 12h20M12 3a15 15 0 0 1 0 18M12 3a15 15 0 0 0 0 18"/></svg>',
  telegram: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 3L11 14M22 3l-7 18-4-8-8-3 18-7z"/></svg>',
  upload: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 16V4m0 0l-4 4m4-4l4 4M4 20h16"/></svg>',
  magnet: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M6 4v6a6 6 0 0 0 12 0V4M6 4H3M18 4h3M6 10H3M18 10h3"/></svg>',
  ed2k: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></svg>',
  failed: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="9"/><path d="M15 9l-6 6M9 9l6 6"/></svg>',
};

const FILTER_ICON_CLASS = {
  forum: "dim-icon-forum",
  telegram: "dim-icon-telegram",
  upload: "dim-icon-upload",
  magnet: "dim-icon-magnet",
  ed2k: "dim-icon-ed2k",
  failed: "dim-icon-failed",
};

function filterIcon(name) {
  const svg = FILTER_SVG[name] || FILTER_SVG.source;
  const cls = FILTER_ICON_CLASS[name] || "dim-icon-default";
  return `<span class="dim-icon ${cls}" aria-hidden="true">${svg}</span>`;
}

function isFilterChecked(id) {
  if (isSourceFilterId(id)) return sourceFilterAll || selectedSourceKeys.has(id);
  if (isCategoryFilterId(id)) return categoryFilterAll || selectedLinkKinds.has(id);
  return false;
}

function isFilterActive(id) {
  if (isSourceFilterId(id)) return !sourceFilterAll && selectedSourceKeys.has(id);
  if (isCategoryFilterId(id)) return !categoryFilterAll && selectedLinkKinds.has(id);
  return false;
}

function updateFilterRowsInPlace() {
  document.querySelectorAll("#resourceFilterPanel .dim-row").forEach((row) => {
    const id = row.dataset.filterId;
    if (!id) return;
    row.classList.toggle("is-on", isFilterChecked(id));
    row.classList.toggle("is-checked", isFilterActive(id));
  });
}

function refreshFilterPanelUI() {
  const panel = document.getElementById("resourceFilterPanel");
  if (panel?.querySelector(".dim-row")) {
    updateFilterRowsInPlace();
    return;
  }
  if (cachedFilterDimensions) {
    renderResourceFilters(cachedFilterDimensions);
  }
}

function renderFilterRow({ id, label, count, child = false, status, hint, icon }) {
  const checked = isFilterChecked(id);
  const active = isFilterActive(id);
  const dim = child ? "child" : "";
  const tag = status === "planned" ? '<span class="dim-tag">待定</span>' : "";
  const hintHtml = hint ? `<div class="dim-hint">${escapeHtml(hint)}</div>` : "";
  const iconHtml = icon ? filterIcon(icon) : "";
  return `<div class="dim-row ${dim}${checked ? " is-on" : ""}${active ? " is-checked" : ""}" data-filter-id="${escapeHtml(id)}" role="button" tabindex="0">
    <span class="dim-check" aria-hidden="true">${FILTER_SVG.check}</span>
    ${iconHtml}
    <span class="dim-label">${escapeHtml(label)}${tag}</span>
    <span class="dim-count">${formatCount(count)}</span>
  </div>${hintHtml}`;
}

function renderSourceDimension(sources) {
  return (sources || [])
    .map((group) => {
      const children = (group.children || [])
        .map((child) =>
          renderFilterRow({
            id: child.id,
            label: child.label,
            count: child.count,
            child: true,
            status: child.status,
            hint: child.hint,
          })
        )
        .join("");
      const groupRow =
        group.children?.length
          ? `<div class="dim-group-label">
              <span class="dim-group-left">${filterIcon(group.id)}<span>${escapeHtml(group.label)}</span></span>
              <span class="dim-count">${formatCount(group.count)}</span>
            </div>${children}`
          : renderFilterRow({
              id: group.id,
              label: group.label,
              count: group.count,
              icon: group.id,
            });
      return groupRow;
    })
    .join("");
}

function renderCategoryDimension(categories) {
  return (categories || [])
    .map((item) =>
      renderFilterRow({
        id: item.id,
        label: item.label,
        count: item.count,
        icon: item.id,
      })
    )
    .join("");
}

function renderResourceFilters(data) {
  const panel = document.getElementById("resourceFilterPanel");
  if (!panel || !data) return;
  cachedFilterDimensions = data;
  panel.innerHTML = `
    <section class="dim-card" data-dim="source">
      <button type="button" class="dim-head" data-dim-toggle="source">
        <span class="dim-title">
          <span class="dim-head-icon">${FILTER_SVG.source}</span>
          <span>资源来源</span>
        </span>
        <span class="dim-chevron">${FILTER_SVG.chevron}</span>
      </button>
      <div class="dim-body">${renderSourceDimension(data.sources)}</div>
    </section>
    <section class="dim-card" data-dim="category">
      <button type="button" class="dim-head" data-dim-toggle="category">
        <span class="dim-title">
          <span class="dim-head-icon category">${FILTER_SVG.category}</span>
          <span>处理类别</span>
        </span>
        <span class="dim-chevron">${FILTER_SVG.chevron}</span>
      </button>
      <div class="dim-body">${renderCategoryDimension(data.categories)}</div>
    </section>`;
}

function isSourceFilterId(id) {
  return id === "upload" || id === "telegram" || id === "forum" || id.startsWith("forum:") || id.startsWith("telegram:");
}

function isCategoryFilterId(id) {
  return id === "magnet" || id === "ed2k" || id === "stub" || id === "skipped" || id === "failed";
}

async function onFilterSelect(id) {
  const isSource = isSourceFilterId(id);
  const isCategory = isCategoryFilterId(id);
  if (!isSource && !isCategory) return;

  if (isSource) {
    const onlyThis =
      !sourceFilterAll && selectedSourceKeys.size === 1 && selectedSourceKeys.has(id);
    if (onlyThis) {
      sourceFilterAll = true;
      selectedSourceKeys.clear();
    } else {
      sourceFilterAll = false;
      selectedSourceKeys.clear();
      selectedSourceKeys.add(id);
    }
  } else {
    const onlyThis =
      !categoryFilterAll && selectedLinkKinds.size === 1 && selectedLinkKinds.has(id);
    if (onlyThis) {
      categoryFilterAll = true;
      selectedLinkKinds.clear();
    } else {
      categoryFilterAll = false;
      selectedLinkKinds.clear();
      selectedLinkKinds.add(id);
    }
  }

  refreshFilterPanelUI();
  await loadResources();
}

function applyResourceFilters() {
  const q = (document.getElementById("resourceSearch").value || "").trim().toLowerCase();
  filteredResources = allResources.filter((item) => {
    if (!q) return true;
    const name = (item.title || item.filename || "").toLowerCase();
    const board = (item.board_name || item.source_name || "").toLowerCase();
    const outcome = processingOutcome(item).toLowerCase();
    return name.includes(q) || board.includes(q) || outcome.includes(q);
  });
  renderResourceTable();
}

function renderResourceTable() {
  const tbody = document.getElementById("resourceTableBody");
  const label = document.getElementById("resourceCountLabel");
  label.textContent = `${filteredResources.length} 条`;

  if (!filteredResources.length) {
    tbody.innerHTML = `<tr><td colspan="6" class="empty">暂无记录</td></tr>`;
    selectedResourceId = null;
    renderDetail(null);
    return;
  }

  if (!filteredResources.some((r) => resourceId(r) === selectedResourceId)) {
    selectedResourceId = resourceId(filteredResources[0]);
  }

  tbody.innerHTML = filteredResources
    .map((item) => {
      const id = resourceId(item);
      const selected = id === selectedResourceId ? "selected" : "";
      const name = item.title || item.filename || threadTitle(item.source_url || id);
      const board = resolveBoardName(item);
      const outcome = processingOutcome(item);
      const resultCol = resourceTypeLabel(item);
      return `<tr class="resource-row ${selected}" data-id="${escapeHtml(id)}">
        <td class="col-icon">${sourceIcon(item.source_type)}</td>
        <td class="col-name" title="${escapeHtml(name)}">${escapeHtml(truncateText(name, 56))}</td>
        <td class="col-board" title="${escapeHtml(board)}">${escapeHtml(truncateText(board, 16))}</td>
        <td class="col-outcome" title="${escapeHtml(outcome)}">${escapeHtml(truncateText(outcome, 40))}</td>
        <td class="col-result">${resultCol}</td>
        <td class="col-time">${formatTime(item.created_at)}</td>
      </tr>`;
    })
    .join("");

  const selected = filteredResources.find((r) => resourceId(r) === selectedResourceId);
  renderDetail(selected || null);
}

function renderDetail(item) {
  const el = document.getElementById("detailContent");
  if (!item) {
    el.innerHTML = '<p class="hint">选择一条记录，核对处理判定是否合理</p>';
    return;
  }

  const isStub = isStubResource(item);
  const isFailed = isFailedResource(item);
  const isSkipped = isSkippedRecord(item);
  const hasDownload = !isThreadRecord(item) && !isStub && !isFailed && !isSkipped;

  if (currentDetailTab === "verdict") {
    const openLink = item.source_url
      ? `<div class="detail-actions"><a class="btn secondary sm" href="${escapeHtml(item.source_url)}" target="_blank" rel="noopener">打开原帖核对</a></div>`
      : "";
    el.innerHTML = `
      ${renderVerdictBanner(item)}
      <div class="detail-grid verdict-grid">
        <div class="detail-field"><span class="lbl">处理时间</span><span class="val">${formatTime(item.created_at)}</span></div>
        <div class="detail-field"><span class="lbl">板块</span><span class="val">${escapeHtml(resolveBoardName(item))}</span></div>
        ${renderProcessingMetaRows(item)}
      </div>
      ${openLink}`;
    return;
  }

  if (currentDetailTab === "source") {
    el.innerHTML = `
      <div class="detail-grid">
        <div class="detail-field"><span class="lbl">论坛名</span><span class="val">${escapeHtml(resolveForumName(item))}</span></div>
        <div class="detail-field"><span class="lbl">板块名</span><span class="val">${escapeHtml(resolveBoardName(item))}</span></div>
        <div class="detail-field full"><span class="lbl">帖子原链接</span><span class="val">${item.source_url ? `<a href="${escapeHtml(item.source_url)}" target="_blank" rel="noopener">${escapeHtml(item.source_url)}</a>` : "-"}</span></div>
      </div>`;
    return;
  }

  if (currentDetailTab === "content") {
    const desc = (item.description || "").trim() || "（无简介）";
    const links = detailResourceLinks(item);
    const linkBlock =
      hasDownload && links.length
        ? `<div class="detail-field full">
            <span class="lbl">入库链接</span>
            <pre class="desc-pre link-only">${links.map((link) => escapeHtml(link)).join("\n\n")}</pre>
          </div>`
        : "";
    const verdictNote =
      isStub || isSkipped || isFailed
        ? `<p class="hint verdict-note">${escapeHtml(processingOutcome(item))}</p>`
        : "";
    el.innerHTML = `
      ${verdictNote}
      ${renderDetailPreviewImages(item.preview_images)}
      <div class="detail-field full">
        <span class="lbl">结构化简介</span>
        <pre class="desc-pre">${escapeHtml(desc)}</pre>
      </div>
      ${linkBlock}`;
  }
}

async function loadResources() {
  const params = new URLSearchParams({ limit: "100" });
  if (!sourceFilterAll && selectedSourceKeys.size) {
    params.set("source_keys", [...selectedSourceKeys].join(","));
  }
  if (!categoryFilterAll && selectedLinkKinds.size) {
    params.set("link_kinds", [...selectedLinkKinds].join(","));
  }
  const data = await api(`/api/resources/recent?${params}`);
  allResources = data.items || [];
  applyResourceFilters();
}

function filtersFromSidebar(sidebar) {
  if (!sidebar) return null;
  return {
    all: sidebar.all ?? 0,
    sources: [
      {
        id: "forum",
        label: "论坛",
        count: sidebar.web ?? 0,
        children: [
          { id: "forum:sehuatang", label: "色花堂", count: sidebar.web ?? 0, status: "active" },
          { id: "forum:other", label: "其他论坛", count: 0, status: "planned" },
        ],
      },
      { id: "telegram", label: "TG 群组", count: sidebar.telegram ?? 0, children: [] },
      { id: "upload", label: "人工导入", count: sidebar.upload ?? 0 },
    ],
    categories: [
      { id: "magnet", label: "magnet", count: sidebar.web_magnet ?? 0 },
      { id: "ed2k", label: "ed2k", count: sidebar.web_ed2k ?? 0 },
      { id: "stub", label: "占位", count: sidebar.web_stub ?? 0 },
      { id: "failed", label: "failed", count: sidebar.web_failed ?? 0 },
    ],
  };
}

function showFilterPanelError(message) {
  const panel = document.getElementById("resourceFilterPanel");
  if (!panel) return;
  panel.innerHTML = `
    <section class="dim-card">
      <div class="dim-body">
        <p class="hint" style="padding:10px 12px;color:var(--danger)">${escapeHtml(message)}</p>
      </div>
    </section>`;
}

function showFilterPanelLoading() {
  const panel = document.getElementById("resourceFilterPanel");
  if (!panel || panel.querySelector(".dim-card")) return;
  panel.innerHTML = `
    <section class="dim-card">
      <div class="dim-body"><p class="hint" style="padding:10px 12px">加载筛选...</p></div>
    </section>`;
}

function filtersFromLegacyStats(stats) {
  const byType = Object.fromEntries((stats.sources || []).map((s) => [s.source_type, s.link_count || 0]));
  return filtersFromSidebar({
    all: stats.total_resources ?? 0,
    web: byType.web ?? 0,
    telegram: byType.telegram ?? 0,
    upload: byType.upload ?? 0,
    web_magnet: 0,
    web_ed2k: byType.web ?? 0,
    web_failed: 0,
  });
}

async function loadResourceFilters() {
  showFilterPanelLoading();
  try {
    const data = await api("/api/resources/filters");
    renderResourceFilters(data);
    return;
  } catch (primaryErr) {
    try {
      const stats = await api("/api/stats");
      const fallback = stats.filters || filtersFromSidebar(stats.sidebar) || filtersFromLegacyStats(stats);
      if (fallback) {
        renderResourceFilters(fallback);
        return;
      }
    } catch {
      /* ignore secondary failure */
    }
    showFilterPanelError(`筛选加载失败：${primaryErr.message}（请重启收集器后 Ctrl+F5 刷新）`);
  }
}

async function loadBoardConfig(refreshStats = false) {
  const suffix = refreshStats ? "?refresh_stats=true" : "";
  cachedBoardCrawl = await api(`/api/boards${suffix}`);
  if (cachedBoardCrawl?.board_order && activeForumId) {
    cachedForumConfigs[activeForumId] = {
      ...(cachedForumConfigs[activeForumId] || {}),
      board_order: cachedBoardCrawl.board_order,
    };
  }
  if (activeForumId && !document.getElementById("forumConfigModal")?.hidden) {
    await openForumModal(activeForumId, true);
  }
}

function setBoardRefreshBtnState(btn, state) {
  if (!btn) return;
  btn.classList.remove("is-loading", "is-success");
  btn.disabled = state === "loading";
  const label = btn.querySelector(".btn-label");
  if (!label) return;
  if (state === "loading") {
    btn.classList.add("is-loading");
    label.textContent = "刷新中...";
  } else if (state === "success") {
    btn.classList.add("is-success");
    label.textContent = "已更新";
  } else {
    label.textContent = "刷新已爬取数";
  }
}

function snapshotBoardCounts() {
  const counts = {};
  for (const board of cachedBoardCrawl?.boards || []) {
    counts[String(board.fid)] = board.crawled_thread_count ?? 0;
  }
  return counts;
}

function highlightBoardCountUpdates(prevCounts) {
  document.querySelectorAll(".forum-board-row").forEach((row) => {
    const fid = row.dataset.boardFid;
    const countCell = row.querySelector(".board-col-count");
    if (!countCell || fid == null) return;
    const newCount = Number.parseInt(countCell.textContent, 10) || 0;
    const oldCount = prevCounts[fid] ?? 0;
    if (newCount === oldCount) return;
    countCell.classList.add("count-updated");
    window.setTimeout(() => countCell.classList.remove("count-updated"), 1600);
  });
}

async function refreshBoardStats(forumId, btn) {
  if (boardStatsRefreshing) return;
  boardStatsRefreshing = true;

  const prevCounts = snapshotBoardCounts();
  const tableWrap = document.querySelector(".forum-boards-table-wrap");

  setBoardRefreshBtnState(btn, "loading");
  tableWrap?.classList.add("is-refreshing");

  try {
    cachedBoardCrawl = await api("/api/boards?refresh_stats=true");
    if (cachedBoardCrawl?.board_order) {
      cachedForumConfigs[forumId] = {
        ...(cachedForumConfigs[forumId] || {}),
        board_order: cachedBoardCrawl.board_order,
      };
    }

    if (activeForumId === forumId && !document.getElementById("forumConfigModal")?.hidden) {
      await openForumModal(forumId, true);
    }

    const newTableWrap = document.querySelector(".forum-boards-table-wrap");
    const newBtn = document.querySelector(`[data-forum-refresh-boards="${forumId}"]`);

    newTableWrap?.classList.add("refresh-done");
    highlightBoardCountUpdates(prevCounts);
    setBoardRefreshBtnState(newBtn, "success");
    notify("已爬取数已刷新", { type: "success" });

    window.setTimeout(() => {
      newTableWrap?.classList.remove("refresh-done");
      setBoardRefreshBtnState(newBtn, "idle");
    }, 1400);
  } catch (err) {
    toast(err.message, true);
    setBoardRefreshBtnState(document.querySelector(`[data-forum-refresh-boards="${forumId}"]`), "idle");
  } finally {
    boardStatsRefreshing = false;
    document.querySelector(".forum-boards-table-wrap")?.classList.remove("is-refreshing");
  }
}

async function ensureForumCache() {
  if (cachedForums.length) return;
  try {
    const data = await api("/api/forum/rules");
    cachedForums = data.forums || [];
    syncForumConfigsFromRules(data);
    if (data.active_forum_id) cachedSettings.active_forum_id = data.active_forum_id;
  } catch {
    /* 板块名回退到 board_name / fid */
  }
}

async function loadForumRules() {
  const container = document.getElementById("forumCardsContainer");
  if (!container) return;

  try {
    const data = await api("/api/forum/rules");
    cachedForums = data.forums || [];
    syncForumConfigsFromRules(data);
    if (data.active_forum_id) cachedSettings.active_forum_id = data.active_forum_id;
    container.innerHTML = `
      <div class="settings-card">
        <div class="settings-card-head">
          <h4>论坛列表</h4>
          <span class="hint inline">选择启用论坛，点击图标查看详情</span>
        </div>
        <div class="settings-card-body">
          <div id="forumIconGrid" class="forum-icon-grid">${cachedForums.map((forum) => renderForumIconTile(forum)).join("")}</div>
        </div>
      </div>`;
    if (cachedSettings && Object.keys(cachedSettings).length) {
      setSettingsForm(cachedSettings, { syncForumConfig: false });
    }
    applyPermissions();
    const summary = document.getElementById("forumActiveSummary");
    if (summary) summary.innerHTML = renderForumActiveSummary();
    autoProbeForumLinkStatuses().catch(() => {});
  } catch (err) {
    container.innerHTML = `<div class="settings-card settings-card-error"><p class="hint" style="color:var(--danger)">论坛配置加载失败：${escapeHtml(err.message)}</p></div>`;
  }
}

async function loadImportSpec() {
  const spec = await api("/api/import/spec");
  const briefEl = document.getElementById("importSpecBrief");
  if (briefEl) {
    briefEl.innerHTML = `
    <p><strong>标准格式</strong></p>
    <code>${escapeHtml(spec.ed2k_format)}</code>
    <p class="hint">${escapeHtml(spec.filename_rules?.[0] || "")}</p>`;
  }
}

async function loadCrawlerStatus(fullReload = false) {
  if (fullReload) lastActivityId = 0;
  const logEl = document.getElementById("activityLog");
  try {
    const data = await api(`/api/crawl/status?since_id=${lastActivityId}`);
    const runtime = data.runtime || {};
    crawlerPollRunning = !!runtime.running;
    updateCrawlerRunUI(runtime);

    const activities = data.activities || [];
    if (logEl) {
      if (!activities.length && lastActivityId === 0) {
        const starting = runtime.enabled && !runtime.running;
        logEl.innerHTML = starting
          ? '<div class="activity-empty">正在启动爬虫，稍候…</div>'
          : '<div class="activity-empty">暂无爬取记录，点击「立即爬取」开始</div>';
      } else if (activities.length) {
        const html = activities.map(renderActivityRow).join("");
        if (lastActivityId === 0) {
          logEl.innerHTML = html;
        } else {
          logEl.querySelector(".activity-empty")?.remove();
          logEl.insertAdjacentHTML("beforeend", html);
        }
        logEl.scrollTop = logEl.scrollHeight;
      }
    }
    if (data.latest_activity_id) lastActivityId = data.latest_activity_id;
  } catch (e) {
    if (logEl && lastActivityId === 0) {
      logEl.innerHTML = `<div class="activity-empty activity-error">加载失败：${escapeHtml(e.message)}</div>`;
    }
  }
}

function activityLevelClass(level, message = "") {
  if (String(message).includes("风控熔断")) return "activity-risk";
  return (
    {
      info: "activity-info",
      warn: "activity-warn",
      error: "activity-error",
      success: "activity-success",
    }[level] || "activity-info"
  );
}

function formatActivityTime(iso) {
  if (!iso) return "--:--:--";
  try {
    const d = new Date(iso);
    return d.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  } catch {
    return iso;
  }
}

function renderActivityRow(item) {
  const msg = item.message || "";
  const boardName = (item.board_name || "").trim();
  const title = (item.thread_title || "").trim();
  const board = boardName && !msg.includes(boardName)
    ? `<span class="activity-board">${escapeHtml(boardName)}</span>`
    : "";
  const link = item.thread_url && title && !msg.includes(title)
    ? `<a class="activity-link" href="${escapeHtml(item.thread_url)}" target="_blank" rel="noopener">${escapeHtml(title || threadTitle(item.thread_url))}</a>`
    : "";
  return `<div class="activity-row ${activityLevelClass(item.level, item.message)}" data-id="${item.id}">
    <span class="activity-time">${formatActivityTime(item.created_at)}</span>
    <span class="activity-msg">${escapeHtml(item.message)}</span>
    ${board}${link}
  </div>`;
}

function getCrawlerPollInterval() {
  if (crawlerPollRunning) return 1000;
  if (cachedSettings.web_crawler_enabled) return 1200;
  return 2500;
}

function stopCrawlerBurstPolling() {
  if (crawlerBurstTimer) {
    clearTimeout(crawlerBurstTimer);
    crawlerBurstTimer = null;
  }
}

function startCrawlerBurstPolling(durationMs = 45000) {
  stopCrawlerBurstPolling();
  const endAt = Date.now() + durationMs;
  const burstTick = () => {
    const page = document.getElementById("page-crawler");
    if (!page?.classList.contains("active") || !isForumCrawlerTabActive()) {
      stopCrawlerBurstPolling();
      return;
    }
    loadCrawlerStatus(false)
      .catch(() => {})
      .finally(() => {
        if (Date.now() >= endAt || !cachedSettings.web_crawler_enabled) {
          stopCrawlerBurstPolling();
          return;
        }
        crawlerBurstTimer = setTimeout(burstTick, crawlerPollRunning ? 800 : 600);
      });
  };
  burstTick();
}

function startCrawlerPolling() {
  stopCrawlerPolling();
  const tick = () => {
    const page = document.getElementById("page-crawler");
    if (page?.classList.contains("active") && isForumCrawlerTabActive()) {
      loadCrawlerStatus(false).catch(() => {});
    }
    crawlerPollTimer = setTimeout(tick, getCrawlerPollInterval());
  };
  tick();
}

function stopCrawlerPolling() {
  stopCrawlerBurstPolling();
  if (crawlerPollTimer) {
    clearTimeout(crawlerPollTimer);
    crawlerPollTimer = null;
  }
}

async function loadHeader() {
  const [health, stats, system] = await Promise.all([
    api("/health"),
    api("/api/stats"),
    api("/api/system/info").catch(() => ({})),
  ]);
  const db = health.database || {};
  cachedSystemInfo = {
    version: system.version || "1.0.0",
    database: system.database || db,
    health: health.status,
    dbLabel: health.status === "ok" ? "已连接" : "未连接",
  };
  const badge = document.getElementById("healthBadge");
  const healthText = badge?.querySelector(".health-text");
  if (healthText) healthText.textContent = health.status === "ok" ? "数据库正常" : "异常";
  badge.className = `health-pill badge ${health.status === "ok" ? "badge-ok" : "badge-warn"}`;
  document.getElementById("sidebarVersion").textContent = `v${system.version || "1.0.0"}`;
  renderCapabilities(system.capabilities || {});
  setSettingsForm(stats.settings || {});
}

async function refreshCrawler() {
  await loadCrawlerStatus(true);
}

function updateCrawlerRunUI(runtime = {}) {
  const enabledFlag = !!runtime.enabled;
  const isRunning = !!runtime.running;
  const runLabel = document.getElementById("crawlerRunState");
  const interval = runtime.interval_minutes ?? cachedSettings.web_crawler_interval_minutes ?? 30;
  const activeForumId = runtime.active_forum_id || cachedSettings.active_forum_id || "sehuatang";
  const forum = cachedForums.find((f) => f.id === activeForumId);
  const forumName = forum?.name || activeForumId;
  const hasCrawler = runtime.crawler_registered ?? forum?.crawler_registered ?? activeForumId === "sehuatang";

  if (runLabel) {
    if (isRunning && !enabledFlag) runLabel.textContent = `正在停止 · ${forumName}`;
    else if (isRunning) runLabel.textContent = `正在执行 · ${forumName}`;
    else if (!hasCrawler) runLabel.textContent = `${forumName} · 无专用爬虫`;
    else if (enabledFlag) runLabel.textContent = `${forumName} · 已开启 · 连续执行`;
    else runLabel.textContent = `${forumName} · 已关闭`;
  }

  const crawlerSwitch = document.getElementById("crawlerSwitch");
  if (crawlerSwitch) {
    if (!crawlerSwitchBusy) {
      crawlerSwitch.checked = enabledFlag;
    }
    crawlerSwitch.disabled = !hasPerm("crawl.run");
    crawlerSwitch.title = isRunning && !enabledFlag
      ? "正在停止，待处理将并入上轮遗留队列"
      : isRunning
        ? "爬虫执行中，关闭后将立即停止"
        : enabledFlag
          ? "点击关闭论坛爬虫"
          : "点击开启论坛爬虫";
  }

  const settingsCheckbox = document.getElementById("web_crawler_enabled");
  if (settingsCheckbox) settingsCheckbox.checked = enabledFlag;
  cachedSettings.web_crawler_enabled = enabledFlag;

  const crawlBtn = document.getElementById("runCrawlBtn");
  if (crawlBtn) {
    crawlBtn.disabled = isRunning || !enabledFlag;
    crawlBtn.title = isRunning
      ? "爬虫正在执行中，请等待结束后再手动触发"
      : !enabledFlag
        ? "请先开启论坛爬虫"
        : "立即执行一轮爬取";
  }

  const carryoverEl = document.getElementById("metricPendingCarryover");
  const abnormalEl = document.getElementById("metricPendingAbnormal");
  const softAdEl = document.getElementById("metricPendingSoftAd");
  const discoveredEl = document.getElementById("metricPendingDiscovered");
  const carryover = runtime.pending_carryover ?? 0;
  const abnormal = runtime.pending_abnormal_discovered ?? 0;
  const softAd = runtime.pending_soft_ad ?? 0;
  const queue = runtime.pending_queue ?? runtime.pending_discovered ?? 0;
  if (carryoverEl) carryoverEl.textContent = formatCount(carryover);
  if (abnormalEl) abnormalEl.textContent = formatCount(abnormal);
  if (softAdEl) softAdEl.textContent = formatCount(softAd);
  if (discoveredEl) discoveredEl.textContent = formatCount(queue);

  const runCrawledEl = document.getElementById("metricRunCrawled");
  const runLinksEl = document.getElementById("metricRunLinks");
  const crawled = runtime.run_crawled_threads ?? 0;
  const links = runtime.run_links_imported ?? 0;
  if (runCrawledEl) runCrawledEl.textContent = formatCount(crawled);
  if (runLinksEl) runLinksEl.textContent = formatCount(links);

  const riskWrap = document.getElementById("metricRiskControlWrap");
  const riskEl = document.getElementById("metricRiskControl");
  const tripped = !!runtime.risk_control_tripped;
  if (riskWrap) riskWrap.hidden = !tripped;
  if (riskEl) {
    riskEl.textContent = tripped ? "熔断" : "正常";
    riskEl.title = runtime.risk_control_message || "";
  }
  if (tripped && runLabel) {
    runLabel.textContent = `${forumName} · 风控熔断`;
  }

  const delayWrap = document.getElementById("metricFetchDelayWrap");
  const delayEl = document.getElementById("metricFetchDelay");
  const currentDelay = runtime.fetch_delay_current;
  if (delayWrap && delayEl && currentDelay != null) {
    delayWrap.hidden = false;
    const base = runtime.fetch_delay_base;
    delayEl.textContent = base != null && currentDelay > base
      ? `${currentDelay}s ↑`
      : `${currentDelay}s`;
    const rate = runtime.fetch_success_rate;
    delayEl.title = rate != null
      ? `基准 ${base}s · 上限 ${runtime.fetch_delay_max ?? base}s · 近 ${runtime.fetch_sample_size || 0} 次成功率 ${Math.round(rate * 100)}% · 熔断阈值 ${runtime.fetch_failure_threshold ?? 5}`
      : "";
  }
}

async function setCrawlerEnabled(enabled) {
  const data = await api("/api/crawl/enable", {
    method: "POST",
    body: JSON.stringify({ enabled }),
  });
  const forumId = data.active_forum_id || getActiveForumId();
  if (data.settings) {
    setSettingsForm(data.settings);
  } else {
    cachedForumConfigs[forumId] = {
      ...(cachedForumConfigs[forumId] || {}),
      web_crawler_enabled: enabled,
    };
    updateCrawlerRunUI({ enabled });
  }
  toast(enabled ? "论坛爬虫已开启" : "论坛爬虫已关闭，待处理已并入上轮遗留队列");
  cachedSettings.web_crawler_enabled = enabled;
  await loadCrawlerStatus(true);
  if (enabled) {
    startCrawlerPolling();
    startCrawlerBurstPolling();
  } else {
    stopCrawlerBurstPolling();
  }
}

async function refreshAll() {
  await loadHeader();
  await Promise.all([
    ensureForumCache(),
    loadResources(),
    loadResourceFilters(),
    loadImportSpec().catch(() => {}),
  ]);
  const crawlerPage = document.getElementById("page-crawler");
  if (crawlerPage?.classList.contains("active")) {
    await loadCrawlerStatus(false);
  }
}

mainNav.forEach((btn) => {
  btn.addEventListener("click", () => {
    const page = btn.dataset.page;
    if (page) showPage(page);
  });
});

document.getElementById("closeSettings").addEventListener("click", () => showPage("resources"));

document.getElementById("resourceFilterPanel")?.addEventListener("click", async (e) => {
  const toggle = e.target.closest("[data-dim-toggle]");
  if (toggle) {
    const card = toggle.closest(".dim-card");
    card?.classList.toggle("collapsed");
    return;
  }

  const row = e.target.closest(".dim-row");
  if (!row) return;
  const id = row.dataset.filterId;
  if (!id) return;
  e.preventDefault();
  e.stopPropagation();
  try {
    await onFilterSelect(id);
  } catch (err) {
    toast(err.message, true);
  }
});

document.getElementById("resourceFilterPanel")?.addEventListener("keydown", async (e) => {
  if (e.key !== "Enter" && e.key !== " ") return;
  const row = e.target.closest(".dim-row");
  if (!row) return;
  e.preventDefault();
  const id = row.dataset.filterId;
  if (!id) return;
  try {
    await onFilterSelect(id);
  } catch (err) {
    toast(err.message, true);
  }
});

detailTabs.forEach((btn) => {
  btn.addEventListener("click", () => {
    detailTabs.forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    currentDetailTab = btn.dataset.detail;
    const selected = filteredResources.find((r) => resourceId(r) === selectedResourceId);
    renderDetail(selected || null);
  });
});

document.getElementById("resourceTableBody").addEventListener("click", (e) => {
  const row = e.target.closest(".resource-row");
  if (!row) return;
  selectedResourceId = row.dataset.id;
  document.querySelectorAll(".resource-row").forEach((r) => r.classList.toggle("selected", r.dataset.id === selectedResourceId));
  const selected = filteredResources.find((r) => resourceId(r) === selectedResourceId);
  renderDetail(selected || null);
});

document.getElementById("resourceSearch").addEventListener("input", applyResourceFilters);
document.getElementById("refreshResources").addEventListener("click", () => refreshAll().catch((e) => toast(e.message, true)));
document.getElementById("refreshCrawler").addEventListener("click", () => refreshCrawler().catch((e) => toast(e.message, true)));

let crawlerSwitchBusy = false;

document.getElementById("crawlerSwitch").addEventListener("change", async (e) => {
  if (crawlerSwitchBusy) return;
  const enabled = e.target.checked;
  const prev = !enabled;
  crawlerSwitchBusy = true;
  try {
    await setCrawlerEnabled(enabled);
  } catch (err) {
    e.target.checked = prev;
    toast(err.message, true);
  } finally {
    crawlerSwitchBusy = false;
  }
});

document.getElementById("importQuickBtn").addEventListener("click", () => openModal("importModal"));
document.getElementById("accountBtn").addEventListener("click", () => {
  renderAccountInfo();
  openModal("accountModal");
});

document.getElementById("logoutBtn").addEventListener("click", async () => {
  try {
    await fetch("/api/auth/logout", { method: "POST", credentials: "include" });
    location.href = "/login";
  } catch (e) {
    location.href = "/login";
  }
});

document.getElementById("refreshUsersBtn")?.addEventListener("click", () => loadUsers().catch((e) => toast(e.message, true)));

document.getElementById("openCreateUserBtn")?.addEventListener("click", () => openModal("createUserModal"));

document.getElementById("createUserForm")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  try {
    const role = document.getElementById("newRoles").value;
    await api("/api/auth/users", {
      method: "POST",
      body: JSON.stringify({
        username: document.getElementById("newUsername").value.trim(),
        password: document.getElementById("newPassword").value,
        display_name: document.getElementById("newDisplayName").value.trim() || undefined,
        roles: role ? [role] : ["viewer"],
      }),
    });
    toast("账号已创建");
    e.target.reset();
    closeModal("createUserModal");
    await loadUsers();
  } catch (err) {
    toast(err.message, true);
  }
});

document.getElementById("editUserForm")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const userId = Number(document.getElementById("editUserId").value);
  if (!userId) return;
  const password = document.getElementById("editPassword").value;
  const payload = {
    display_name: document.getElementById("editDisplayName").value.trim() || undefined,
    roles: [document.getElementById("editRoles").value || "viewer"],
    is_active: document.getElementById("editIsActive").checked,
  };
  if (password) payload.password = password;
  try {
    await api(`/api/auth/users/${userId}`, {
      method: "PUT",
      body: JSON.stringify(payload),
    });
    toast("账号已更新");
    closeModal("editUserModal");
    await loadUsers();
  } catch (err) {
    toast(err.message, true);
  }
});

document.getElementById("usersTableBody")?.addEventListener("click", async (e) => {
  const openEditBtn = e.target.closest("[data-user-open-edit]");
  const toggleBtn = e.target.closest("[data-user-toggle]");
  const deleteBtn = e.target.closest("[data-user-delete]");
  if (openEditBtn) {
    openEditUserModal(Number(openEditBtn.dataset.userOpenEdit));
    return;
  }
  if (toggleBtn) {
    const userId = Number(toggleBtn.dataset.userToggle);
    const isActive = toggleBtn.dataset.userActive === "true";
    try {
      await api(`/api/auth/users/${userId}`, {
        method: "PUT",
        body: JSON.stringify({ is_active: !isActive }),
      });
      toast(isActive ? "已禁用" : "已启用");
      await loadUsers();
    } catch (err) {
      toast(err.message, true);
    }
    return;
  }
  if (deleteBtn) {
    if (deleteBtn.disabled) return;
    const userId = Number(deleteBtn.dataset.userDelete);
    if (!confirm("确定删除该账号？")) return;
    try {
      await api(`/api/auth/users/${userId}`, { method: "DELETE" });
      toast("已删除");
      await loadUsers();
    } catch (err) {
      toast(err.message, true);
    }
  }
});

document.querySelectorAll("[data-close]").forEach((el) => {
  el.addEventListener("click", () => closeModal(el.dataset.close));
});

configTabs.forEach((btn) => {
  btn.addEventListener("click", () => {
    configTabs.forEach((b) => b.classList.remove("active"));
    configPanels.forEach((p) => p.classList.remove("active"));
    btn.classList.add("active");
    const panel = document.getElementById(`config-${btn.dataset.config}`);
    if (panel) panel.classList.add("active");
  });
});

function retestForumLinkStatus(forumId) {
  if (!forumId || !hasPerm("settings.read")) return;
  setForumLinkTesting(forumId);
  probeForumLinkStatus(forumId).catch((err) => {
    forumLinkStatus[forumId] = { state: "fail", detail: err.message };
    updateForumLinkStatusBadge(forumId);
    toast(err.message, true);
  });
}

document.getElementById("forumCardsContainer")?.addEventListener("click", (e) => {
  const statusBadge = e.target.closest("[data-forum-link-status]");
  if (statusBadge) {
    e.preventDefault();
    e.stopPropagation();
    retestForumLinkStatus(statusBadge.dataset.forumLinkStatus);
    return;
  }
  const btn = e.target.closest("[data-forum-open]");
  if (!btn || btn.disabled) return;
  openForumModal(btn.dataset.forumOpen).catch((err) => toast(err.message, true));
});

document.getElementById("forumCardsContainer")?.addEventListener("keydown", (e) => {
  if (e.key !== "Enter" && e.key !== " ") return;
  const statusBadge = e.target.closest("[data-forum-link-status]");
  if (!statusBadge) return;
  e.preventDefault();
  retestForumLinkStatus(statusBadge.dataset.forumLinkStatus);
});

document.getElementById("forumCardsContainer")?.addEventListener("change", async (e) => {
  const radio = e.target.closest('input[name="active_forum_id"]');
  if (!radio || !radio.checked || radio.disabled) return;
  const prev = cachedSettings.active_forum_id || "sehuatang";
  try {
    cachedSettings.active_forum_id = radio.value;
    const data = await api("/api/settings", {
      method: "PUT",
      body: JSON.stringify({
        ...collectGlobalSettings(),
        active_forum_id: radio.value,
        ...forumCrawlerPayload(radio.value),
      }),
    });
    setSettingsForm(data.settings);
    toast(`已启用论坛：${cachedForums.find((f) => f.id === radio.value)?.name || radio.value}`);
  } catch (err) {
    cachedSettings.active_forum_id = prev;
    rerenderForumIcons();
    toast(err.message, true);
  }
});

document.getElementById("forumModalBody")?.addEventListener("click", (e) => {
  if (Date.now() < boardSortSuppressClickUntil && !e.target.closest(".forum-tab")) {
    e.preventDefault();
    e.stopPropagation();
    return;
  }
  const tabBtn = e.target.closest(".forum-tab");
  if (tabBtn?.dataset.forumTab) {
    showForumModalTab(tabBtn.dataset.forumTab);
    return;
  }
  const gotoTab = e.target.closest("[data-forum-goto-tab]");
  if (gotoTab?.dataset.forumGotoTab) {
    showForumModalTab(gotoTab.dataset.forumGotoTab);
    return;
  }
  const refreshBtn = e.target.closest("[data-forum-refresh-boards]");
  if (refreshBtn) {
    refreshBoardStats(refreshBtn.dataset.forumRefreshBoards, refreshBtn).catch((err) => toast(err.message, true));
    return;
  }
  const topoRefresh = e.target.closest("[data-forum-topology-refresh]");
  if (topoRefresh && activeForumId) {
    loadForumTopology(activeForumId).catch((err) => toast(err.message, true));
    return;
  }
  const openQueue = e.target.closest("[data-open-board-queue]");
  if (openQueue) {
    openBoardQueueModal();
  }
});

document.getElementById("forumModalBody")?.addEventListener("submit", async (e) => {
  const form = e.target.closest(".forum-config-form");
  if (!form) return;
  e.preventDefault();
  const forumId = form.dataset.forumForm;
  if (!forumId) return;
  try {
    const payload = collectForumConfigForm(form);
    const data = await api(`/api/forum/${forumId}/config`, {
      method: "PUT",
      body: JSON.stringify(payload),
    });
    if (forumId === getActiveForumId() && data.settings) setSettingsForm(data.settings);
    refreshForumModalAfterSave(forumId, data.crawler_config);
    notify("论坛配置已保存", {
      type: "success",
      detail: payload.web_crawler_cookie ? "若修改了 Cookie，请重启爬虫使新 Cookie 生效" : "",
    });
    probeForumLinkStatus(forumId).catch(() => {});
  } catch (err) {
    toast(err.message, true);
  }
});

crawlerTabs.forEach((btn) => {
  btn.addEventListener("click", () => showCrawlerTab(btn.dataset.crawler));
});

document.getElementById("parseTestForm")?.addEventListener("submit", runParseTest);

document.getElementById("importBtn").addEventListener("click", async () => {
  try {
    const content = document.getElementById("importText").value.trim();
    if (!content) return toast("请输入 ED2K 链接", true);
    const data = await api("/api/import", { method: "POST", body: JSON.stringify({ content }) });
    document.getElementById("importResult").textContent = `成功导入 ${data.count} 条`;
    notify(`成功导入 ${data.count} 条`, { type: "success", detail: data.message || "" });
    await refreshAll();
  } catch (e) {
    toast(e.message, true);
  }
});

document.getElementById("importFileBtn").addEventListener("click", async () => {
  try {
    const fileInput = document.getElementById("importFile");
    if (!fileInput.files?.[0]) return toast("请选择文件", true);
    const form = new FormData();
    form.append("file", fileInput.files[0]);
    const res = await fetch("/api/import/file", { method: "POST", credentials: "include", body: form });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "上传失败");
    notify(`成功导入 ${data.count} 条`, { type: "success" });
    await refreshAll();
  } catch (e) {
    toast(e.message, true);
  }
});

async function saveSettings(message) {
  const data = await api("/api/settings", { method: "PUT", body: JSON.stringify(collectSettings()) });
  setSettingsForm(data.settings);
  notify(message || "已保存", { type: "success", detail: data.note || "" });
  autoProbeForumLinkStatuses().catch(() => {});
}

document.getElementById("telegramForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  try {
    await saveSettings("TG 配置已保存，重启后生效");
  } catch (err) {
    toast(err.message, true);
  }
});

document.getElementById("settingsForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  try {
    await saveSettings("通用设置已保存");
  } catch (err) {
    toast(err.message, true);
  }
});

document.getElementById("testProxyBtn")?.addEventListener("click", async () => {
  const btn = document.getElementById("testProxyBtn");
  if (!btn) return;
  const proxy = settingText("web_crawler_proxy");
  const testUrl = (cachedSettings.web_crawl_urls || "https://www.sehuatang.net/forum.php").split(",")[0].trim();
  const prevText = btn.textContent;
  btn.disabled = true;
  btn.textContent = "测试中...";
  try {
    const data = await api("/api/system/proxy-test", {
      method: "POST",
      body: JSON.stringify({ proxy, test_url: testUrl }),
    });
    const mode = data.proxy_used ? "代理" : "直连";
    const detail = data.elapsed_ms != null
      ? `${mode} · ${data.elapsed_ms}ms · HTTP ${data.status_code ?? "-"}`
      : data.test_url || "";
    notify(data.message || (data.ok ? "代理联通正常" : "代理测试失败"), {
      type: data.ok ? "success" : "error",
      detail,
    });
  } catch (err) {
    toast(err.message, true);
  } finally {
    btn.disabled = false;
    btn.textContent = prevText;
  }
});

document.getElementById("runCrawlBtn").addEventListener("click", async () => {
  const resultEl = document.getElementById("crawlerResult");
  const btn = document.getElementById("runCrawlBtn");
  if (btn.disabled) {
    toast(btn.title || "爬虫正在进行中", true);
    return;
  }
  resultEl.textContent = "爬取中，请稍候...";
  btn.disabled = true;
  try {
    await loadCrawlerStatus(true);
    const data = await api("/api/crawl/run", { method: "POST" });
    const r = data.result || {};
    resultEl.textContent = `完成：新帖 ${r.discovered_threads ?? 0} · 处理 ${r.crawled_threads ?? 0} · 入库 ${r.links ?? 0}`;
    notify("爬取完成", {
      type: "success",
      detail: `新帖 ${r.discovered_threads ?? 0} · 处理 ${r.crawled_threads ?? 0} · 入库 ${r.links ?? 0}`,
    });
    lastActivityId = 0;
    await loadCrawlerStatus(true);
  } catch (e) {
    resultEl.textContent = e.message;
    toast(e.message, true);
  } finally {
    await loadCrawlerStatus(true);
  }
});

document.getElementById("systemInfoBtn")?.addEventListener("click", () => openSystemInfoModal());

document.getElementById("refreshDataOverview")?.addEventListener("click", () => {
  loadDataOverview().catch((e) => toast(e.message, true));
});

document.getElementById("dataResetForm")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const confirmInput = document.getElementById("dataResetConfirm");
  const btn = document.getElementById("dataResetBtn");
  const confirmText = (confirmInput?.value || "").trim();
  if (confirmText !== "清空") {
    toast('请在确认框输入「清空」', true);
    return;
  }
  if (!confirm("确定清空所有爬取数据与资源？此操作不可恢复。")) return;

  const prevText = btn?.textContent || "";
  if (btn) {
    btn.disabled = true;
    btn.textContent = "清空中...";
  }
  try {
    const data = await resetAllData(confirmText);
    if (confirmInput) confirmInput.value = "";
    renderDataOverview({ overview: {}, crawler_running: false, crawler_enabled: false });
    await loadDataOverview();
    await refreshAll();
    notify("数据已清空", {
      type: "success",
      detail: `已删除资源 ${data.deleted?.resources ?? 0} 条、爬取记录 ${data.deleted?.crawl_pages ?? 0} 条`,
    });
  } catch (err) {
    toast(err.message, true);
    await loadDataOverview().catch(() => {});
  } finally {
    if (btn) {
      btn.disabled = !hasPerm("settings.write");
      btn.textContent = prevText;
    }
  }
});

document.getElementById("clearSystemMessages")?.addEventListener("click", () => {
  systemMessages = [];
  renderSystemMessageList();
  updateSystemMsgBadge();
});

initAuth().then((ok) => {
  if (ok) {
    initBoardSortInteractions();
    refreshAll()
      .then(() => {
        if (!sessionStorage.getItem("collector_boot_notified")) {
          notify("系统已就绪", { type: "info", detail: "保存等操作会在此反馈，可点击右上角「系统」查看记录" });
          sessionStorage.setItem("collector_boot_notified", "1");
        }
      })
      .catch((e) => toast(e.message, true));
  }
});
