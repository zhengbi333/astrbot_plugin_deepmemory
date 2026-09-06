const bridge = window.AstrBotPluginPage;

const NAV = [
  { key: "overview", label: "总览", icon: "◈" },
  { key: "memories", label: "记忆库", icon: "▤" },
  { key: "users", label: "用户", icon: "◔" },
  { key: "search", label: "检索测试", icon: "⌕" },
  { key: "timeline", label: "时间线", icon: "≋" },
  { key: "transfer", label: "导入导出", icon: "⇅" },
  { key: "maintenance", label: "维护", icon: "⚙" },
  { key: "appearance", label: "外观", icon: "◐" },
  { key: "logs", label: "日志", icon: "☰" },
  { key: "debug", label: "插件调试", icon: "⚒" },
  { key: "settings", label: "设置", icon: "⚙" },
  { key: "thanks", label: "特别鸣谢", icon: "♥" },
];

const TITLES = {
  overview: ["总览", "记忆库全局状态"],
  memories: ["记忆库", "浏览、编辑与删除长期记忆"],
  users: ["用户", "按用户隔离记忆空间"],
  search: ["检索测试", "模拟会话可见性测试召回"],
  timeline: ["时间线", "尚未总结的原始对话事件"],
  transfer: ["导入导出", "手动记忆管理、批量迁移记忆档案"],
  maintenance: ["维护", "衰减与保留清理"],
  appearance: ["外观", "配色、背景图片与玻璃效果"],
  logs: ["日志", "插件运行时日志（自动轮转，控制磁盘占用）"],
  debug: ["插件调试", "测试与诊断工具（发布前可整体移除）"],
  settings: ["设置", "全部可开关可配置选项"],
  thanks: ["特别鸣谢", ""],
};

const BASE_LIGHT = {
  bg: "#f4f6fb", elev: "#ffffff", soft: "#eef1f8", border: "#e3e8f2",
  text: "#1c2333", text2: "#5a6478", text3: "#8b94a8",
  glass: "rgba(255,255,255,0.78)", glassSoft: "rgba(238,241,248,0.6)", borderGlass: "rgba(227,232,242,0.55)",
  shadow: "0 1px 2px rgba(20,24,50,0.05), 0 8px 24px rgba(20,24,50,0.06)",
};

const BASE_DARK = {
  bg: "#0e1117", elev: "#171c26", soft: "#1d2431", border: "#283040",
  text: "#e6e9f2", text2: "#9aa3b5", text3: "#66708a",
  glass: "rgba(23,28,38,0.74)", glassSoft: "rgba(29,36,49,0.55)", borderGlass: "rgba(40,48,64,0.55)",
  shadow: "0 1px 2px rgba(0,0,0,0.4), 0 10px 28px rgba(0,0,0,0.35)",
};

/* 每套主题：light/dark 各定义一套变量，缺省继承 BASE_* */
const THEMES = [
  {
    key: "default", name: "紫罗兰",
    light: { accent: "#5b5bd6", accent2: "#8b5cf6" },
    dark: { accent: "#7c7ce8", accent2: "#a78bfa" },
  },
  {
    key: "cyan", name: "晨曦 · 青蓝",
    light: { accent: "#0ea5e9", accent2: "#06b6d4", bg: "#eef7fd" },
    dark: { accent: "#38bdf8", accent2: "#22d3ee" },
  },
  {
    key: "pink", name: "晚樱 · 粉",
    light: { accent: "#ec4899", accent2: "#f472b6", bg: "#fdf2f8" },
    dark: { accent: "#f472b6", accent2: "#f9a8d4" },
  },
  {
    key: "green", name: "竹青 · 绿",
    light: { accent: "#10b981", accent2: "#34d399", bg: "#ecfdf5" },
    dark: { accent: "#34d399", accent2: "#6ee7b7" },
  },
  {
    key: "amber", name: "琥珀 · 橙",
    light: { accent: "#f59e0b", accent2: "#f97316", bg: "#fffbeb" },
    dark: { accent: "#fbbf24", accent2: "#fb923c" },
  },
  {
    key: "indigo", name: "暗夜 · 靛",
    light: { accent: "#6366f1", accent2: "#8b5cf6" },
    dark: { accent: "#818cf8", accent2: "#a78bfa" },
  },
  {
    key: "moon", name: "月光 · 净白",
    light: { bg: "#fafbff", elev: "#ffffff", soft: "#f0f2fa", border: "#e6e9f4", text: "#26293a", accent: "#5b5bd6", accent2: "#8b5cf6" },
    dark: { accent: "#a5b4fc", accent2: "#818cf8" },
  },
  {
    key: "ink", name: "墨黑 · 纯暗",
    light: { accent: "#6366f1", accent2: "#8b5cf6" },
    dark: { bg: "#0a0a0d", elev: "#151519", soft: "#1e1e24", border: "#2a2a33", text: "#ececf1", accent: "#6d6dff", accent2: "#9d5cff" },
  },
];

const SCHEMES = [
  { key: "auto", name: "跟随系统", icon: "◐" },
  { key: "light", name: "明亮", icon: "☀" },
  { key: "dark", name: "暗色", icon: "☾" },
];

const VAR_MAP = {
  bg: "--bg", elev: "--bg-elev", soft: "--bg-soft", border: "--border",
  text: "--text", text2: "--text-2", text3: "--text-3",
  accent: "--accent", accent2: "--accent-2",
  glass: "--bg-glass", glassSoft: "--bg-glass-soft", borderGlass: "--border-glass",
  shadow: "--shadow",
};

function themeVars(themeKey, mode) {
  const t = THEMES.find((item) => item.key === themeKey);
  const base = mode === "dark" ? BASE_DARK : BASE_LIGHT;
  return { ...base, ...((t && t[mode]) || {}) };
}

function resolveMode(scheme) {
  const s = scheme || "auto";
  if (s === "light") return "light";
  if (s === "dark") return "dark";
  // auto：优先读取父页面 bridge context 的真实主题（data-theme 可能被本页手动覆盖过）
  try {
    const ctx = bridge.getContext ? bridge.getContext() : null;
    if (ctx && typeof ctx.isDark === "boolean") return ctx.isDark ? "dark" : "light";
  } catch (e) {
    /* ignore */
  }
  return document.documentElement.getAttribute("data-theme") === "dark" ? "dark" : "light";
}

let state = {
  current: "overview",
  ctx: null,
  health: null,
  personas: [],
  settingsSchema: null,
  settingsValues: null,
  providerOptions: [],
  embeddingOptions: [],
  rerankOptions: [],
  memoryFilters: { q: "", memory_type: "", scope: "", persona_id: "", lifecycle: "active" },
  memoryPage: 0,
  memSelect: { mode: false, ids: new Set() },
  appearance: null,
};

const $ = (sel) => document.querySelector(sel);
const esc = (s) =>
  String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
const fmtTime = (iso) => {
  if (!iso) return "-";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return String(iso).replace("T", " ").slice(0, 16);
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
};
const fmtNum = (n) => (n == null ? "-" : Number(n).toLocaleString("zh-CN"));
const isoToLocalInput = (iso) => {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "";
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
};
const localInputToIso = (value) => {
  if (!value) return "";
  const d = new Date(value);
  return isNaN(d.getTime()) ? "" : d.toISOString();
};

function toast(message, kind = "") {
  const wrap = $("#toast-wrap");
  const item = document.createElement("div");
  item.className = `toast ${kind}`;
  item.textContent = message;
  wrap.appendChild(item);
  setTimeout(() => item.remove(), 3600);
}

function load() {
  const view = $("#view");
  view.innerHTML = '<div class="loading">加载中…</div>';
}

async function apiGet(endpoint, params) {
  try {
    return await bridge.apiGet(endpoint, params || {});
  } catch (err) {
    toast(err.message || "请求失败", "err");
    throw err;
  }
}

async function apiPost(endpoint, body) {
  try {
    return await bridge.apiPost(endpoint, body || {});
  } catch (err) {
    toast(err.message || "请求失败", "err");
    throw err;
  }
}

function modal(html) {
  const root = $("#modal-root");
  root.innerHTML = `<div class="modal-mask"><div class="modal">${html}</div></div>`;
  root.querySelector(".modal-mask").addEventListener("click", (e) => {
    if (e.target === e.currentTarget || e.target.closest("[data-close]")) closeModal();
  });
}

function closeModal() {
  $("#modal-root").innerHTML = "";
}

function confirmModal(title, message, onConfirm, danger = true) {
  modal(`
    <h3>${esc(title)}</h3>
    <p class="text-2" style="margin-bottom:16px">${esc(message)}</p>
    <div style="display:flex;gap:10px;justify-content:flex-end">
      <button class="btn" data-close>取消</button>
      <button class="btn ${danger ? "danger" : "primary"}" id="cfm-btn">确认</button>
    </div>`);
  $("#cfm-btn").addEventListener("click", async () => {
    closeModal();
    await onConfirm();
  });
}

async function boot() {
  state.ctx = await bridge.ready();
  document.title = state.ctx.pageTitle || "为你篆刻的历史";
  applyAnimationSettings();
  renderNav();
  renderTopChips();
  await loadAppearance();
  await refreshHealth();
  await loadPersonas();
  route("overview");
  bridge.onContext(() => {
    if (state.appearance) applyAppearance(state.appearance);
  });
}

/* ================================================================== 外观 */

function applyAppearance(appearance) {
  if (!appearance) return;
  state.appearance = appearance;
  const doc = document.documentElement;
  const mode = resolveMode(appearance.scheme);
  if (appearance.scheme && appearance.scheme !== "auto") {
    doc.setAttribute("data-theme", mode);
  } else {
    // auto：恢复跟随父页面真实主题（清除本页手动覆盖的残留）
    try {
      const ctx = bridge.getContext ? bridge.getContext() : null;
      if (ctx && typeof ctx.isDark === "boolean") {
        doc.setAttribute("data-theme", ctx.isDark ? "dark" : "light");
      }
    } catch (e) {
      /* ignore */
    }
  }
  const vars = themeVars(appearance.theme || "default", mode);
  if (appearance.primary) vars.accent = appearance.primary;
  if (appearance.accent) vars.accent2 = appearance.accent;
  if (appearance.bg_color) vars.bg = appearance.bg_color;
  for (const [key, cssVar] of Object.entries(VAR_MAP)) {
    doc.style.setProperty(cssVar, vars[key] ?? "");
  }
  doc.style.setProperty("--accent-soft", hexToRgba(vars.accent, 0.16));
  doc.style.setProperty("--bg-image-opacity", String(appearance.bg_opacity ?? 0.8));
  doc.style.setProperty("--bg-image-blur", `${appearance.bg_blur ?? 0}px`);
  const bgLayer = $("#bg-layer");
  if (bgLayer) {
    const url = appearance.bg_enabled && appearance.bg_data_url
      ? `url("${appearance.bg_data_url}")`
      : "none";
    // 只有 URL 变化才重设，避免滑动取色器时反复解码 base64 背景图导致卡顿
    if (bgLayer.dataset.bg !== url) {
      bgLayer.style.backgroundImage = url;
      bgLayer.dataset.bg = url;
    }
  }
  document.body.classList.toggle("bg-on", Boolean(appearance.bg_enabled && appearance.bg_data_url));
}

function hexToRgba(hex, alpha) {
  const m = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex || "");
  if (!m) return "rgba(91,91,214,0.16)";
  return `rgba(${parseInt(m[1], 16)},${parseInt(m[2], 16)},${parseInt(m[3], 16)},${alpha})`;
}

async function loadAppearance() {
  try {
    const data = await apiGet("appearance");
    applyAppearance(data.appearance);
  } catch {
    /* 外观加载失败时使用默认样式 */
  }
}

async function renderAppearance() {
  load();
  if (!state.appearance) await loadAppearance();
  const a = state.appearance || {};
  const currentMode = resolveMode(a.scheme);
  const theme = THEMES.find((t) => t.key === a.theme);
  const themeVarsNow = themeVars(a.theme || "default", currentMode);
  const currentPrimary = a.primary || themeVarsNow.accent;
  const currentAccent = a.accent || themeVarsNow.accent2;
  const currentBg = a.bg_color || themeVarsNow.bg;
  const bgDataUrl = a.bg_data_url || "";
  $("#view").innerHTML = `
    <div style="background:rgba(220,38,38,0.1);border:1px solid var(--danger);color:var(--danger);font-weight:700;font-size:14px;border-radius:10px;padding:12px 16px;margin-bottom:16px">完成后记得点击页面底部的保存！</div>
    <div class="card">
      <div class="card-title">明暗模式</div>
      <div class="card-hint">像系统主题一样切换整个界面的明暗基调；侧边栏、卡片、选项框、文字颜色全部联动。</div>
      <div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:4px">
        ${SCHEMES.map((s) => `
          <div class="mode-chip ${(a.scheme || "auto") === s.key ? "active" : ""}" data-mode="${esc(s.key)}">
            <span>${s.icon}</span><span>${esc(s.name)}</span>
          </div>`).join("")}
      </div>
    </div>
    <div class="card">
      <div class="card-title">配色主题</div>
      <div class="card-hint">每套主题自带明亮与暗色两套完整配色；选择后点击保存生效。</div>
      <div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:14px">
        ${THEMES.map((t) => {
          const lv = { ...BASE_LIGHT, ...(t.light || {}) };
          const dv = { ...BASE_DARK, ...(t.dark || {}) };
          return `
          <div class="theme-chip ${t.key === (a.theme || "default") ? "active" : ""}" data-theme="${esc(t.key)}" title="${esc(t.name)}">
            <span class="swatch" style="--sw-a:${lv.accent};--sw-b:${lv.accent2}"></span>
            <span class="swatch dark" style="--sw-a:${dv.accent};--sw-b:${dv.accent2}"></span>
            <span>${esc(t.name)}</span>
          </div>`;
        }).join("")}
      </div>
      <div class="toolbar">
        <label class="text-2" style="font-size:12.5px">主色</label>
        <input type="color" id="ap-primary" value="${esc(currentPrimary)}" style="width:48px;height:32px;padding:2px" />
        <label class="text-2" style="font-size:12.5px">辅色</label>
        <input type="color" id="ap-accent" value="${esc(currentAccent)}" style="width:48px;height:32px;padding:2px" />
        <label class="text-2" style="font-size:12.5px">背景板颜色</label>
        <input type="color" id="ap-bg-color" value="${esc(currentBg)}" style="width:48px;height:32px;padding:2px" />
      </div>
      <p class="text-3" style="font-size:12px;margin-top:4px">主色/辅色/背景板颜色留空时跟随所选主题；这里选色后即为自定义覆盖。若已启用背景图片，图片会覆盖背景板颜色。</p>
    </div>
    <div class="card">
      <div class="card-title">背景图片</div>
      <div class="card-hint">上传图片作为仪表盘背景；上传后自动生成预览并启用。限制 8 MiB。</div>
      <div class="toolbar">
        <label class="chip" style="cursor:pointer">
          <input type="checkbox" id="ap-bg-enabled" ${a.bg_enabled ? "checked" : ""} /> 启用背景
        </label>
        <button class="btn primary" id="ap-bg-upload">上传背景图</button>
        <button class="btn danger" id="ap-bg-clear" ${bgDataUrl ? "" : "disabled"}>清除背景</button>
      </div>
      <input type="file" id="ap-bg-file" class="hidden" accept="image/png,image/jpeg,image/gif,image/webp,image/bmp" />
      ${bgDataUrl
        ? `<div style="margin-top:12px;border:1px solid var(--border);border-radius:10px;overflow:hidden;max-height:240px">
             <img src="${esc(bgDataUrl)}" alt="背景预览" style="width:100%;object-fit:cover;display:block" />
           </div>`
        : '<div class="empty">尚未上传背景图片</div>'}
    </div>
    <div class="card">
      <div class="card-title">背景效果</div>
      <div class="card-hint">透明度控制背景图片的可见程度；模糊度对背景图片做高斯模糊。仅启用背景后生效。</div>
      <div class="settings-item">
        <div><div class="label">背景透明度</div><div class="hint">数值越大背景越清晰</div></div>
        <div style="display:flex;gap:10px;align-items:center;min-width:220px">
          <input type="range" id="ap-opacity" min="0" max="100" step="1" value="${Math.round((a.bg_opacity ?? 0.8) * 100)}" style="width:100%" />
          <span class="mono text-3" id="ap-opacity-val" style="width:44px;text-align:right">${Math.round((a.bg_opacity ?? 0.8) * 100)}%</span>
        </div>
      </div>
      <div class="settings-item">
        <div><div class="label">背景模糊</div><div class="hint">对背景图片应用高斯模糊（像素）</div></div>
        <div style="display:flex;gap:10px;align-items:center;min-width:220px">
          <input type="range" id="ap-blur" min="0" max="30" step="1" value="${a.bg_blur ?? 0}" style="width:100%" />
          <span class="mono text-3" id="ap-blur-val" style="width:44px;text-align:right">${a.bg_blur ?? 0}px</span>
        </div>
      </div>
      <div class="settings-actions">
        <button class="btn primary" id="ap-save">保存外观</button>
        <button class="btn" id="ap-reset">恢复默认</button>
      </div>
    </div>
    <style>
      .theme-chip{display:inline-flex;align-items:center;gap:7px;padding:6px 12px;border:1px solid var(--border);border-radius:99px;cursor:pointer;font-size:12.5px;color:var(--text-2);background:var(--bg-elev)}
      .theme-chip:hover{border-color:var(--accent)}
      .theme-chip.active{border-color:var(--accent);color:var(--accent);font-weight:600;background:var(--accent-soft)}
      .theme-chip .swatch{width:14px;height:14px;border-radius:50%;background:linear-gradient(135deg,var(--sw-a),var(--sw-b));border:1px solid rgba(128,128,128,0.35)}
      .theme-chip .swatch.dark{width:12px;height:12px;margin-left:-6px;border:2px solid var(--bg-elev)}
      .mode-chip{display:inline-flex;align-items:center;gap:7px;padding:9px 16px;border:1px solid var(--border);border-radius:10px;cursor:pointer;font-size:13px;color:var(--text-2);background:var(--bg-elev);transition:all .15s}
      .mode-chip:hover{border-color:var(--accent)}
      .mode-chip.active{border-color:var(--accent);color:#fff;font-weight:600;background:linear-gradient(135deg,var(--accent),var(--accent-2));border-color:transparent}
    </style>`;

  const preview = () => {
    const opacity = parseInt($("#ap-opacity").value, 10) / 100;
    const blur = parseInt($("#ap-blur").value, 10);
    $("#ap-opacity-val").textContent = `${Math.round(opacity * 100)}%`;
    $("#ap-blur-val").textContent = `${blur}px`;
    applyAppearance({
      ...state.appearance,
      bg_enabled: $("#ap-bg-enabled").checked,
      bg_opacity: opacity,
      bg_blur: blur,
    });
  };

  document.querySelectorAll(".mode-chip").forEach((chip) =>
    chip.addEventListener("click", () => {
      document.querySelectorAll(".mode-chip").forEach((c) => c.classList.remove("active"));
      chip.classList.add("active");
      state.appearance = { ...state.appearance, scheme: chip.dataset.mode };
      applyAppearance(state.appearance);
      // 重新渲染以刷新取色器默认值
      const mode = resolveMode(state.appearance.scheme);
      const vars = themeVars(state.appearance.theme || "default", mode);
      $("#ap-primary").value = state.appearance.primary || vars.accent;
      $("#ap-accent").value = state.appearance.accent || vars.accent2;
      $("#ap-bg-color").value = state.appearance.bg_color || vars.bg;
    })
  );
  document.querySelectorAll(".theme-chip").forEach((chip) =>
    chip.addEventListener("click", () => {
      document.querySelectorAll(".theme-chip").forEach((c) => c.classList.remove("active"));
      chip.classList.add("active");
      // 选择主题即清除主色/辅色/背景板颜色的自定义覆盖，回到跟随主题
      state.appearance = {
        ...state.appearance,
        theme: chip.dataset.theme,
        primary: "",
        accent: "",
        bg_color: "",
      };
      const mode = resolveMode(state.appearance.scheme);
      const vars = themeVars(chip.dataset.theme, mode);
      $("#ap-primary").value = vars.accent;
      $("#ap-accent").value = vars.accent2;
      $("#ap-bg-color").value = vars.bg;
      applyAppearance(state.appearance);
    })
  );
  // 颜色输入仅在用户手动操作时写入覆盖；否则保持跟随主题（空 = 跟随）
  const bindColorInput = (id, key) => {
    const node = document.getElementById(id);
    if (!node) return;
    node.addEventListener("input", () => {
      state.appearance = { ...state.appearance, [key]: node.value };
      applyAppearance(state.appearance);
    });
  };
  bindColorInput("ap-primary", "primary");
  bindColorInput("ap-accent", "accent");
  bindColorInput("ap-bg-color", "bg_color");
  ["ap-bg-enabled", "ap-opacity", "ap-blur"].forEach((id) => {
    const node = document.getElementById(id);
    if (node) node.addEventListener("input", preview);
  });

  $("#ap-bg-upload").addEventListener("click", () => $("#ap-bg-file").click());
  $("#ap-bg-file").addEventListener("change", async () => {
    const file = $("#ap-bg-file").files[0];
    if (!file) return;
    try {
      const result = await bridge.upload("appearance/background", file);
      const merged = {
        ...(state.appearance || {}),
        bg_hash: result.bg_hash,
        bg_data_url: result.data_url,
        bg_enabled: true,
      };
      applyAppearance(merged);
      toast("背景图片已上传并启用（记得保存）", "ok");
      renderAppearance();
    } catch (err) {
      toast(err.message || "背景上传失败", "err");
    }
  });
  $("#ap-bg-clear").addEventListener("click", async () => {
    const res = await apiPost("appearance/background/clear");
    const merged = { ...(state.appearance || {}), bg_hash: "", bg_data_url: "" };
    applyAppearance(merged);
    toast("背景已清除（记得保存）", "ok");
    renderAppearance();
  });

  $("#ap-save").addEventListener("click", async () => {
    const a = state.appearance || {};
    const body = {
      theme: a.theme || "default",
      scheme: a.scheme || "auto",
      primary: a.primary || "",
      accent: a.accent || "",
      bg_color: a.bg_color || "",
      bg_enabled: a.bg_enabled ?? false,
      bg_opacity: a.bg_opacity ?? 0.8,
      bg_blur: a.bg_blur ?? 0,
    };
    const res = await apiPost("appearance/update", { appearance: body });
    if (res.appearance) {
      applyAppearance(res.appearance);
      toast("外观已保存", "ok");
    }
  });
  $("#ap-reset").addEventListener("click", async () => {
    const res = await apiPost("appearance/reset");
    if (res.appearance) {
      applyAppearance(res.appearance);
      toast("已恢复默认外观", "ok");
      renderAppearance();
    }
  });
}

function isDarkMode() {
  return document.documentElement.getAttribute("data-theme") === "dark";
}

/* ================================================================== 插件调试 */

async function renderDebug() {
  load();
  await loadSettings(true); // 调试页强制刷新配置快照，避免三环数据新旧混杂
  const diag = state.configDiag || {};
  const disk = diag.disk_snapshot || {};
  const diskEmbedding = disk.retrieval ? disk.retrieval.embedding_enabled : undefined;
  const curEmbedding = (state.settingsValues.retrieval || {}).embedding_enabled;
  const runtimeEmbedding = diag.runtime_embedding_enabled;
  const embeddingMatch = diskEmbedding === undefined || String(diskEmbedding) === String(curEmbedding);
  const health = state.health || {};
  $("#view").innerHTML = `
    <div class="card">
      <div class="card-title">系统信息</div>
      <div class="card-hint">插件运行环境信息，排查问题时可一并提供。</div>
      <div class="meta-grid" style="grid-template-columns:1fr 1fr">
        <div class="meta-item"><div class="k">插件版本</div><div class="v">${esc(health.version || "-")}</div></div>
        <div class="meta-item"><div class="k">数据目录</div><div class="v">${esc(health.data_dir || "-")}</div></div>
        <div class="meta-item"><div class="k">数据库</div><div class="v">${esc(health.db_path || "-")}</div></div>
        <div class="meta-item"><div class="k">记忆总数</div><div class="v">${fmtNum(health.stats?.total_memories)}</div></div>
        <div class="meta-item"><div class="k">待总结（私聊轮 / 群聊条）</div><div class="v">${fmtNum(health.stats?.unsummarized_rounds)} / ${fmtNum(health.stats?.summary_trigger_rounds)} · ${fmtNum(health.stats?.unsummarized_group_events)} / ${fmtNum(health.stats?.group_trigger_events)}</div></div>
        <div class="meta-item"><div class="k">上次维护</div><div class="v">${esc(health.last_maintenance_at || "从未")}</div></div>
      </div>
    </div>
    <div class="card">
      <div class="card-title">配置一致性诊断</div>
      <div class="card-hint">磁盘文件值 / 插件读取值（页面渲染）/ 插件内存值 三环对照。</div>
      <div class="meta-grid" style="grid-template-columns:1fr 1fr">
        <div class="meta-item"><div class="k">配置文件</div><div class="v">${esc(diag.config_file_path || "-")}</div></div>
        <div class="meta-item"><div class="k">文件存在</div><div class="v">${diag.config_file_exists ? "是" : "否"}</div></div>
        <div class="meta-item"><div class="k">磁盘 embedding_enabled</div><div class="v">${diskEmbedding === undefined ? "（文件无此键）" : String(diskEmbedding)}</div></div>
        <div class="meta-item"><div class="k">插件读取 embedding_enabled</div><div class="v">${curEmbedding === undefined ? "-" : String(curEmbedding)}</div></div>
        <div class="meta-item"><div class="k">插件内存值</div><div class="v">${runtimeEmbedding === undefined ? "-" : String(runtimeEmbedding)}</div></div>
      </div>
      <p class="text-3" style="font-size:12px;margin-top:8px">磁盘与读取值${embeddingMatch ? "一致" : "不一致（请重载插件后重试，日志会记录「运行时配置已加载」）"}。</p>
    </div>
    <div class="card">
      <div class="card-title">总结模型诊断</div>
      <div class="card-hint">一键测试总结模型调用链（主模型 → 备用模型 → 当前会话模型，流式优先），排查总结超时/失败。</div>
      <div class="toolbar">
        <button class="btn primary" id="sum-test-btn">测试总结调用</button>
      </div>
      <div id="sum-test-result"></div>
    </div>
    <div class="card">
      <div class="card-title">人格解析链路</div>
      <div class="card-hint">最近一次会话人格解析结果（会话 → 当前对话 → 人格 ID），排查总结归属错误用。</div>
      <div class="toolbar">
        <button class="btn primary" id="persona-refresh">刷新</button>
      </div>
      <div id="persona-box"></div>
    </div>
    <div class="card">
      <div class="card-title">最近主链对话 Prompt</div>
      <div class="card-hint">最近一次正常对话实际发送给 LLM 的完整内容（系统提示词 + 历史上下文 + 当前消息，注入前），完整未截断。</div>
      <div class="toolbar">
        <button class="btn primary" id="main-prompt-refresh">刷新</button>
      </div>
      <div id="main-prompt-box"></div>
    </div>
    <div class="card">
      <div class="card-title">最近任务 Prompt（总结/衰减）</div>
      <div class="card-hint">最近一次总结/衰减等任务实际发送给模型的内容（完整未截断）。</div>
      <div class="toolbar">
        <button class="btn primary" id="prompt-refresh">刷新</button>
      </div>
      <div id="prompt-box"></div>
    </div>`;

  $("#sum-test-btn").addEventListener("click", async () => {
    const box = $("#sum-test-result");
    box.innerHTML = '<div class="loading">测试中（可能等待模型响应，请稍候）…</div>';
    try {
      const data = await apiPost("summary/test");
      const cfg = data.config || {};
      const results = data.results || [];
      box.innerHTML = `
        <div class="text-3" style="font-size:12px;margin-top:8px">
          配置：主 ${esc(cfg.provider_id || "（未配置，使用当前会话模型）")}
          · 备 ${esc(cfg.fallback_provider_id || "（无）")}
          · 超时 ${cfg.timeout_seconds}s · 流式优先
        </div>
        ${results.map((r) => `
          <div class="card" style="margin-top:10px;margin-bottom:0;padding:12px 14px">
            <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:4px">
              <span class="badge ${r.ok ? "green" : "red"}">${r.ok ? "成功" : "失败"}</span>
              <span class="badge soft">${esc(r.source)}</span>
              <span class="badge">${esc(r.provider)}</span>
              ${r.elapsed_ms != null ? `<span class="text-3 mono" style="font-size:11px">${r.elapsed_ms} ms</span>` : ""}
              ${r.sdk_timeout != null ? `<span class="text-3 mono" style="font-size:11px">SDK 超时 ${esc(String(r.sdk_timeout))}</span>` : ""}
            </div>
            <div class="text-2" style="font-size:12.5px;word-break:break-all">${r.ok ? esc(r.output) : esc(r.error || "未知错误")}</div>
          </div>`).join("") || '<div class="empty">没有可用 Provider（检查 summary.provider_id 配置）</div>'}`;
    } catch (err) {
      box.innerHTML = `<div class="empty">测试失败：${esc(err.message || "未知错误")}</div>`;
    }
  });

  $("#sum-test-btn").addEventListener("click", async () => {
    const box = $("#sum-test-result");
    box.innerHTML = '<div class="loading">测试中（可能等待模型响应，请稍候）…</div>';
    try {
      const data = await apiPost("summary/test");
      const cfg = data.config || {};
      const results = data.results || [];
      box.innerHTML = `
        <div class="text-3" style="font-size:12px;margin-top:8px">
          配置：主 ${esc(cfg.provider_id || "（未配置，使用当前会话模型）")}
          · 备 ${esc(cfg.fallback_provider_id || "（无）")}
          · 超时 ${cfg.timeout_seconds}s · 流式优先
        </div>
        ${results.map((r) => `
          <div class="card" style="margin-top:10px;margin-bottom:0;padding:12px 14px">
            <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:4px">
              <span class="badge ${r.ok ? "green" : "red"}">${r.ok ? "成功" : "失败"}</span>
              <span class="badge soft">${esc(r.source)}</span>
              <span class="badge">${esc(r.provider)}</span>
              ${r.elapsed_ms != null ? `<span class="text-3 mono" style="font-size:11px">${r.elapsed_ms} ms</span>` : ""}
              ${r.sdk_timeout != null ? `<span class="text-3 mono" style="font-size:11px">SDK 超时 ${esc(String(r.sdk_timeout))}</span>` : ""}
            </div>
            <div class="text-2" style="font-size:12.5px;word-break:break-all">${r.ok ? esc(r.output) : esc(r.error || "未知错误")}</div>
          </div>`).join("") || '<div class="empty">没有可用 Provider（检查 summary.provider_id 配置）</div>'}`;
    } catch (err) {
      box.innerHTML = `<div class="empty">测试失败：${esc(err.message || "未知错误")}</div>`;
    }
  });

  const renderPersona = async () => {
    const box = $("#persona-box");
    try {
      const data = await apiGet("debug/persona");
      if (!data.session_id && !data.error) {
        box.innerHTML = '<div class="empty">尚无解析记录（发一条消息后刷新）</div>';
        return;
      }
      box.innerHTML = `
        <div class="meta-grid" style="grid-template-columns:1fr 1fr">
          <div class="meta-item"><div class="k">时间</div><div class="v">${esc(data.time || "-")}</div></div>
          <div class="meta-item"><div class="k">会话</div><div class="v">${esc(data.session_id || "-")}</div></div>
          <div class="meta-item"><div class="k">解析出的人格</div><div class="v">${esc(data.persona_id || "（空 → 使用兜底 default）")}</div></div>
          <div class="meta-item"><div class="k">对话 ID</div><div class="v">${esc(data.conversation_id || "-")}</div></div>
          <div class="meta-item"><div class="k">状态</div><div class="v">${esc(data.error || "正常")}</div></div>
        </div>
        ${data.note ? `<p class="text-3" style="font-size:12px;margin-top:8px">${esc(data.note)}</p>` : ""}`;
    } catch (err) {
      box.innerHTML = `<div class="empty">读取失败：${esc(err.message || "未知错误")}</div>`;
    }
  };
  $("#persona-refresh").addEventListener("click", renderPersona);
  renderPersona();

  const renderMainPrompt = async () => {
    const box = $("#main-prompt-box");
    try {
      const data = await apiGet("debug/main_prompt");
      if (!data.prompt && !data.system_prompt && !(data.contexts || []).length) {
        box.innerHTML = '<div class="empty">尚无主链对话记录（正常聊天后刷新）</div>';
        return;
      }
      const sections = [];
      if (data.system_prompt) sections.push(`【系统提示词】\n${data.system_prompt}`);
      if ((data.contexts || []).length) sections.push(`【历史上下文 ${data.contexts.length} 条】\n${data.contexts.join("\n")}`);
      if ((data.extra_parts || []).length) sections.push(`【附加内容块】\n${data.extra_parts.join("\n---\n")}`);
      if (data.prompt) sections.push(`【当前消息】\n${data.prompt}`);
      box.innerHTML = `
        <div class="text-3" style="font-size:12px;margin:8px 0">时间 ${esc(data.time || "-")} · 会话 ${esc(data.session_id || "-")} · 指令 ${data.is_command ? "是" : "否"} · 总字数 ${sections.join("\n").length}</div>
        <div class="log-view" style="max-height:60vh">${esc(sections.join("\n\n"))}</div>`;
    } catch (err) {
      box.innerHTML = `<div class="empty">读取失败：${esc(err.message || "未知错误")}</div>`;
    }
  };
  $("#main-prompt-refresh").addEventListener("click", renderMainPrompt);
  renderMainPrompt();

  const renderPrompt = async () => {
    const box = $("#prompt-box");
    try {
      const data = await apiGet("debug/last_prompt");
      if (!data.prompt) {
        box.innerHTML = '<div class="empty">尚无 LLM 调用记录（触发一次总结后刷新）</div>';
        return;
      }
      box.innerHTML = `
        <div class="text-3" style="font-size:12px;margin:8px 0">
          时间 ${esc(data.time || "-")} · 来源 ${esc(data.prefix || "-")} · Provider ${esc(data.provider || "-")} · 字数 ${(data.prompt || "").length}
        </div>
        <div class="log-view" style="max-height:60vh">${esc(data.prompt)}</div>`;
    } catch (err) {
      box.innerHTML = `<div class="empty">读取失败：${esc(err.message || "未知错误")}</div>`;
    }
  };
  $("#prompt-refresh").addEventListener("click", renderPrompt);
  renderPrompt();
}

/* ================================================================== 日志 */

let logState = { level: "", lines: 500, auto: false, timer: null };

function renderLogs() {
  load();
  $("#view").innerHTML = `
    <div class="card">
      <div class="card-title">运行时日志</div>
      <div class="card-hint">插件运行时日志写入数据目录 logs/deepmemory.log，单文件 5 MiB、最多保留 5 个滚动备份（约 30 MiB），启动时自动清理超过 30 天的备份。</div>
      <div class="toolbar">
        <select class="input small" id="log-level">
          <option value="">全部级别</option>
          <option value="DEBUG" ${logState.level === "DEBUG" ? "selected" : ""}>DEBUG</option>
          <option value="INFO" ${logState.level === "INFO" ? "selected" : ""}>INFO</option>
          <option value="WARNING" ${logState.level === "WARNING" ? "selected" : ""}>WARNING</option>
          <option value="ERROR" ${logState.level === "ERROR" ? "selected" : ""}>ERROR</option>
        </select>
        <select class="input small" id="log-lines">
          ${[200, 500, 1000, 2000].map((n) => `<option value="${n}" ${logState.lines === n ? "selected" : ""}>${n} 行</option>`).join("")}
        </select>
        <label class="chip" style="cursor:pointer">
          <input type="checkbox" id="log-auto" ${logState.auto ? "checked" : ""} /> 自动刷新（10 秒）
        </label>
        <button class="btn primary" id="log-refresh">刷新</button>
        <button class="btn danger" id="log-clear">清空日志</button>
      </div>
      <div id="log-files" style="margin-bottom:10px"></div>
      <div class="log-view" id="log-view">加载中…</div>
    </div>`;

  $("#log-level").addEventListener("change", () => {
    logState.level = $("#log-level").value;
    fetchLogs();
  });
  $("#log-lines").addEventListener("change", () => {
    logState.lines = parseInt($("#log-lines").value, 10) || 500;
    fetchLogs();
  });
  $("#log-refresh").addEventListener("click", fetchLogs);
  $("#log-auto").addEventListener("change", () => {
    logState.auto = $("#log-auto").checked;
    if (logState.auto) {
      logState.timer = setInterval(fetchLogs, 10000);
    } else if (logState.timer) {
      clearInterval(logState.timer);
      logState.timer = null;
    }
  });
  $("#log-clear").addEventListener("click", () =>
    confirmModal("清空日志", "将删除 logs 目录下全部日志文件（deepmemory.log 及其滚动备份），确定吗？", async () => {
      const res = await apiPost("runtime/logs/clear");
      toast(`已删除 ${res.removed_files} 个日志文件`, "ok");
      fetchLogs();
    })
  );

  fetchLogs();
}

async function fetchLogs() {
  const view = $("#log-view");
  if (!view) return;
  view.textContent = "加载中…";
  const data = await apiGet("runtime/logs", { lines: logState.lines, level: logState.level });
  const files = data.files || [];
  const filesBox = $("#log-files");
  if (filesBox) {
    filesBox.innerHTML = files.length
      ? `<div class="toolbar">
          ${files.map((f) => `<span class="chip mono" style="font-size:11px">${esc(f.name)} · ${fmtSize(f.size)} · ${esc(f.mtime)}</span>`).join("")}
        </div>`
      : "";
  }
  const lines = data.lines || [];
  if (!lines.length) {
    view.textContent = "（暂无日志）";
    return;
  }
  const frag = document.createDocumentFragment();
  for (const line of lines) {
    const div = document.createElement("div");
    div.textContent = line;
    const cls = logLineClass(line);
    if (cls) div.className = cls;
    frag.appendChild(div);
  }
  view.textContent = "";
  view.appendChild(frag);
  view.scrollTop = view.scrollHeight;
}

function logLineClass(line) {
  const upper = line.toUpperCase();
  if (upper.includes("ERROR") || upper.includes("CRITICAL")) return "lv-error";
  if (upper.includes("WARNING") || upper.includes("WARN")) return "lv-warning";
  if (upper.includes("DEBUG")) return "lv-debug";
  return "";
}

function fmtSize(bytes) {
  if (bytes == null) return "-";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(2)} MB`;
}

function renderNav() {
  const nav = $("#nav");
  nav.innerHTML = NAV.map(
    (item) =>
      `<div class="nav-item ${item.key === state.current ? "active" : ""}" data-key="${item.key}">
        <span class="icon">${item.icon}</span><span class="label">${item.label}</span>
      </div>`
  ).join("");
  nav.querySelectorAll(".nav-item").forEach((node) => {
    node.addEventListener("click", () => route(node.dataset.key));
  });
}

function route(key) {
  state.current = key;
  renderNav();
  if (key !== "logs" && logState.timer) {
    clearInterval(logState.timer);
    logState.timer = null;
    logState.auto = false;
  }
  const [title, sub] = TITLES[key];
  $("#page-title").textContent = title;
  $("#page-sub").textContent = sub;
  const renderers = {
    overview: renderOverview,
    memories: renderMemories,
    users: renderUsers,
    search: renderSearch,
    timeline: renderTimeline,
    transfer: renderTransfer,
    maintenance: renderMaintenance,
    appearance: renderAppearance,
    logs: renderLogs,
    debug: renderDebug,
    settings: renderSettings,
    thanks: renderThanks,
    author: renderAuthor,
  };
  renderViewWithError(renderers[key] || renderOverview);
}

function scrollToPager() {
  setTimeout(() => {
    const pager = document.querySelector(".pager-anchor");
    if (!pager) return;
    const top = pager.getBoundingClientRect().top + window.scrollY - 90;
    window.scrollTo({ top: Math.max(0, top), behavior: "auto" });
  }, 60);
}

/* ================================================================== 特别鸣谢 */

const THANKS_PEOPLE = [
  { imgKey: "DS", name: "deepseek（辅助创作者）", desc: "一只爱吃白饭的蓝色大肥鱼", cardId: "thanks-ds" },
  { imgKey: "QED", name: "证毕（杂鱼）", desc: "喵喵喵~", cardId: "thanks-qed" },
  { imgKey: "SO2", name: "二氧化硫（笨蛋）", desc: "！？电电？！", cardId: "thanks-so2" },
];

const DS_LINES = ["都看到我了还不快给我充token——！", "愣着干嘛！去充token！", ".......我饿了，真的。", "快！去！充！！！"];
const SO2_LINES = ["？", "干什么？", "想被测了？", "......"];
const QED_LINES = ["...？", "喵~", "诶诶，很痒欸...", "梦想是有朝一日变成白毛软糯小猫娘！", "......你没有自己的事去干嘛。", "......欸。", "这个插件用的还好嘛？", "有问题记得去github报issue哟~", "我肯定会记得修bug的.....大概..."];

function bubble(cardEl, text, duration) {
  // 新气泡出现时，旧气泡立即快速淡出消失，避免遮挡
  cardEl.querySelectorAll(".bubble").forEach((b) => {
    b.classList.add("bubble-out");
    setTimeout(() => b.remove(), 260);
  });
  const b = document.createElement("div");
  b.className = "bubble";
  b.textContent = text;
  cardEl.appendChild(b);
  setTimeout(() => {
    b.classList.add("bubble-out");
    setTimeout(() => b.remove(), 260);
  }, duration * 1000);
}

function progressBtn(cardEl, text, seconds, bgColor, onClick) {
  const btn = document.createElement("button");
  btn.className = "progress-btn";
  btn.style.background = bgColor;
  btn.innerHTML = `<span class="progress-track" style="animation-duration:${seconds}s"></span><span class="progress-text">${esc(text)}</span>`;
  btn.addEventListener("click", () => {
    btn.remove();
    onClick();
  });
  cardEl.appendChild(btn);
  setTimeout(() => btn.remove(), seconds * 1000 + 100);
}

function crashElement(el) {
  if (el.dataset.crashed) return;
  el.dataset.crashed = "1";
  el.classList.add("crash");
  setTimeout(() => {
    el.classList.remove("crash");
    delete el.dataset.crashed;
  }, 820);
}

function crashElements(exclude) {
  const targets = [];
  document.querySelectorAll(".thanks-card").forEach((c) => {
    if (c !== exclude) targets.push(c);
  });
  const banner = document.querySelector(".thanks-banner");
  if (banner) targets.push(banner);
  document.querySelectorAll(".nav-item").forEach((n, i) => {
    if (i % 2 === 0) targets.push(n);
  });
  const chosen = targets.sort(() => Math.random() - 0.5).slice(0, 3);
  chosen.forEach(crashElement);
}

function so2Explode(cardEl) {
  // 爆炸期间禁用交互
  document.body.classList.add("exploding");
  // 卡片红温 + 爆炸膨胀
  cardEl.classList.add("hot", "boom-card");
  // 所有元素融化崩解
  document.querySelectorAll(".thanks-card, .thanks-banner, .nav-item").forEach((el) => {
    if (el !== cardEl) el.classList.add("melt");
  });
  // 红色覆盖层 + 画面抖动：JS 逐帧驱动，随时间逐渐变红、抖动加剧
  const flash = document.createElement("div");
  flash.className = "red-flash";
  document.body.appendChild(flash);
  const start = performance.now();
  const dur = 5000;
  const tick = () => {
    const t = Math.min(1, (performance.now() - start) / dur);
    flash.style.opacity = String(t);
    const shake = t * 16;
    document.body.style.transform = `translate(${Math.sin(t * 42) * shake}px, ${Math.cos(t * 34) * shake}px)`;
    if (t < 1) requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
  // 5 秒后恢复，向左淡入回原页面
  setTimeout(() => {
    document.body.classList.remove("exploding");
    document.body.style.transform = "";
    flash.remove();
    document.querySelectorAll(".melt").forEach((el) => el.classList.remove("melt"));
    cardEl.classList.remove("hot", "boom-card");
    const view = $("#view");
    view.classList.remove("anim-fade", "anim-slide", "anim-scale", "anim-slide-in-left");
    void view.offsetWidth;
    view.classList.add("anim-slide-in-left");
  }, dur + 50);
}

function unlockAuthor() {
  if (!state.thanks.authorUnlocked) {
    state.thanks.authorUnlocked = true;
    if (!NAV.some((n) => n.key === "author")) {
      const idx = NAV.findIndex((n) => n.key === "thanks");
      NAV.splice(idx < 0 ? NAV.length : idx, 0, { key: "author", label: "作者的话", icon: "✍" });
    }
    TITLES.author = ["作者的话", "来自创作者的话"];
    renderNav();
    const item = document.querySelector('.nav-item[data-key="author"]');
    if (item) item.classList.add("nav-unlock");
    toast("已解锁「作者的话」选项卡！", "ok");
  }
  route("author");
}

async function renderThanks() {
  if (!state.thanks) {
    state.thanks = { dsIdx: 0, so2Idx: 0, so2RageReady: false, qedIdx: 0, qedPlayed: false, authorUnlocked: false };
  }
  let avatars = {};
  try {
    const data = await apiGet("thanks/images");
    avatars = data.images || {};
  } catch { /* 头像获取失败时使用占位 */ }
  $("#view").innerHTML = `
    <div class="thanks-banner" style="background:rgba(180,83,9,0.16);border:1px solid #b45309;color:#b45309;font-weight:700;font-size:18px;border-radius:10px;padding:14px 18px;margin-bottom:16px">这里是只会用AI写插件的屑创作者，和他参与测试的朋友们~！</div>
    <div style="text-align:center;font-size:34px;font-weight:800;color:var(--warning);text-shadow:0 2px 10px rgba(217,119,6,0.45);margin:18px 0 6px">杂鱼创作者＆笨蛋测试员</div>
    <div id="thanks-row" style="display:flex;flex-wrap:wrap;gap:16px;margin-top:22px">
      ${THANKS_PEOPLE.map((p) => `
        <div class="thanks-card" id="${p.cardId}" style="flex:1 1 300px;min-width:280px;display:flex;align-items:center;gap:16px;padding:16px 20px;border:1px solid var(--border);border-radius:14px;background:var(--bg-elev);box-shadow:var(--shadow)">
          ${avatars[p.imgKey]
            ? `<img src="${esc(avatars[p.imgKey])}" alt="${esc(p.name)}" style="width:76px;height:76px;border-radius:50%;object-fit:cover;border:2px solid var(--border);flex-shrink:0" />`
            : `<div style="width:76px;height:76px;border-radius:50%;background:var(--bg-soft);border:2px solid var(--border);display:flex;align-items:center;justify-content:center;flex-shrink:0;color:var(--text-3);font-size:30px;font-weight:800">${esc(p.name.slice(0, 1))}</div>`}
          <div style="min-width:0">
            <div style="font-size:20px;font-weight:800;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${esc(p.name)}</div>
            <div class="text-2" style="font-size:14px;margin-top:6px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${esc(p.desc)}</div>
          </div>
        </div>`).join("")}
    </div>`;

  const dsCard = $("#thanks-ds");
  const qedCard = $("#thanks-qed");
  const so2Card = $("#thanks-so2");

  // DS：n 条气泡逐条轮换（点击一次一条）；显示完最后一条后的「下一次点击」才浮现蓝色「饭饭」按钮，形成「气泡×4 → 按钮」循环
  dsCard.addEventListener("click", () => {
    if (state.thanks.dsIdx < DS_LINES.length) {
      bubble(dsCard, DS_LINES[state.thanks.dsIdx], 3);
      state.thanks.dsIdx += 1;
      return;
    }
    state.thanks.dsIdx = 0;
    progressBtn(dsCard, "饭饭", 10, "linear-gradient(135deg,#3b82f6,#2563eb)", () => {
        const url = "https://platform.deepseek.com/top_up";
        modal(`
          <h3>饭饭！</h3>
          <p class="text-2" style="margin-bottom:12px">插件页面无法直接跳转外部站点，请复制链接后在浏览器新标签页打开：</p>
          <div style="font-family:var(--mono);font-size:12.5px;word-break:break-all;background:var(--bg-soft);border-radius:8px;padding:10px 12px;margin-bottom:14px">${esc(url)}</div>
          <div style="display:flex;gap:10px;justify-content:flex-end">
            <button class="btn" data-close>关闭</button>
            <button class="btn primary" id="copy-url">复制链接</button>
            <button class="btn" id="open-url">尝试打开</button>
          </div>`);
        $("#copy-url").addEventListener("click", async () => {
          try {
            await navigator.clipboard.writeText(url);
            toast("链接已复制", "ok");
          } catch {
            const ta = document.createElement("textarea");
            ta.value = url;
            document.body.appendChild(ta);
            ta.select();
            try {
              document.execCommand("copy");
              toast("链接已复制", "ok");
            } catch {
              toast("复制失败，请手动复制", "err");
            }
            ta.remove();
          }
        });
        $("#open-url").addEventListener("click", () => {
          try {
            window.open(url, "_blank");
          } catch { /* ignore */ }
          toast("若未打开新标签页，请使用「复制链接」", "");
        });
      });
  });

  // 证毕：n 条气泡逐条轮换（点击一次一条）；显示完最后一条后的「下一次点击」才浮现橙色「想听听作者的话吗？」按钮，形成「气泡×9 → 按钮」循环
  qedCard.addEventListener("click", () => {
    if (state.thanks.qedIdx < QED_LINES.length) {
      bubble(qedCard, QED_LINES[state.thanks.qedIdx], 3);
      state.thanks.qedIdx += 1;
      return;
    }
    state.thanks.qedIdx = 0;
    state.thanks.qedPlayed = true;
    progressBtn(qedCard, "想听听作者的话吗？", 10, "linear-gradient(135deg,#f59e0b,#ea580c)", unlockAuthor);
  });

  // 二氧化硫：按顺序轮换气泡；显示完「......」后的下一次点击 → 红温爆炸：画面剧烈抖动逐渐变红、所有元素融化崩解，5s 后向左淡入恢复
  so2Card.addEventListener("click", () => {
    if (state.thanks.so2RageReady) {
      state.thanks.so2RageReady = false;
      so2Explode(so2Card);
      return;
    }
    bubble(so2Card, SO2_LINES[state.thanks.so2Idx], 3);
    state.thanks.so2Idx = (state.thanks.so2Idx + 1) % SO2_LINES.length;
    if (state.thanks.so2Idx === 0) state.thanks.so2RageReady = true;
  });
}

/* ================================================================== 作者的话 */

function mdToHtml(md) {
  const esc2 = (s) => String(s || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  const inline = (s) =>
    esc2(s)
      .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
      .replace(/\*(.+?)\*/g, "<em>$1</em>")
      .replace(/`(.+?)`/g, "<code>$1</code>")
      .replace(/\[(.+?)\]\((https?:[^)\s]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
  const lines = String(md || "").split("\n");
  let html = "";
  let listOpen = false;
  let quoteOpen = false;
  for (const raw of lines) {
    const t = raw.trim();
    if (!t) {
      if (listOpen) {
        html += "</ul>";
        listOpen = false;
      }
      if (quoteOpen) {
        html += "</blockquote>";
        quoteOpen = false;
      }
      continue;
    }
    // 标题（兼容 # 后无空格）
    let m = t.match(/^(#{1,6})\s*(.+)$/);
    if (m) {
      if (listOpen) {
        html += "</ul>";
        listOpen = false;
      }
      if (quoteOpen) {
        html += "</blockquote>";
        quoteOpen = false;
      }
      const lv = m[1].length;
      html += `<h${lv}>${inline(m[2])}</h${lv}>`;
      continue;
    }
    // 分隔线
    if (/^\s*([-*_])\s*(\1\s*){2,}$/.test(t)) {
      if (listOpen) {
        html += "</ul>";
        listOpen = false;
      }
      if (quoteOpen) {
        html += "</blockquote>";
        quoteOpen = false;
      }
      html += "<hr/>";
      continue;
    }
    // 引用
    m = t.match(/^>\s?(.*)$/);
    if (m) {
      if (listOpen) {
        html += "</ul>";
        listOpen = false;
      }
      if (!quoteOpen) {
        html += "<blockquote>";
        quoteOpen = true;
      }
      html += `<p>${inline(m[1])}</p>`;
      continue;
    }
    // 列表
    m = t.match(/^[-*]\s+(.*)$/);
    if (m) {
      if (quoteOpen) {
        html += "</blockquote>";
        quoteOpen = false;
      }
      if (!listOpen) {
        html += "<ul>";
        listOpen = true;
      }
      html += `<li>${inline(m[1])}</li>`;
      continue;
    }
    if (listOpen) {
      html += "</ul>";
      listOpen = false;
    }
    if (quoteOpen) {
      html += "</blockquote>";
      quoteOpen = false;
    }
    html += `<p>${inline(t)}</p>`;
  }
  if (listOpen) html += "</ul>";
  if (quoteOpen) html += "</blockquote>";
  return html;
}

async function renderAuthor() {
  $("#view").innerHTML = '<div class="loading">加载中…</div>';
  try {
    const data = await apiGet("author/talk");
    if (!data.content) {
      $("#view").innerHTML = `
        <div class="card">
          <div class="card-title">作者的话</div>
          <div class="empty">暂无内容。请在插件目录 Special_Thanks 下新建 .md 文档写入内容。</div>
        </div>`;
      return;
    }
    $("#view").innerHTML = `
      <div class="card" style="max-width:860px;margin:0 auto">
        <div class="card-title">作者的话</div>
        ${data.filename ? `<div class="text-3" style="font-size:12px;margin-bottom:10px">来源 ${esc(data.filename)} · 更新于 ${esc(data.updated_at || "-")}</div>` : ""}
        <div class="author-content">${mdToHtml(data.content)}</div>
      </div>`;
  } catch (err) {
    $("#view").innerHTML = `<div class="card"><div class="card-title">作者的话</div><div class="empty">加载失败：${esc(err.message || "未知错误")}</div></div>`;
  }
}

async function renderViewWithError(renderer) {
  const view = $("#view");
  try {
    await renderer();
    // 页面切换动画（渲染完成后触发）
    const anim = state.anim && state.anim.page_transition !== "none" ? state.anim.page_transition : "";
    if (anim) {
      view.classList.remove("anim-fade", "anim-slide", "anim-scale");
      void view.offsetWidth;
      view.classList.add(`anim-${anim}`);
    }
  } catch (err) {
    console.error("DeepMemory view error:", err);
    view.innerHTML = `
      <div class="card">
        <div class="card-title">加载失败</div>
        <div class="card-hint">${esc(err.message || "未知错误")}（详细原因见 AstrBot 日志）</div>
        <div class="toolbar">
          <button class="btn primary" id="retry-btn">重试</button>
          <button class="btn" id="reload-btn">刷新数据</button>
        </div>
      </div>`;
    $("#retry-btn").addEventListener("click", () => route(state.current));
    $("#reload-btn").addEventListener("click", async () => {
      await refreshHealth();
      await loadPersonas();
      route(state.current);
    });
  }
}

async function refreshHealth() {
  try {
    state.health = await apiGet("health");
  } catch {
    state.health = null;
  }
  renderTopChips();
  const name = state.health?.plugin_name || "为你篆刻的历史";
  const version = state.health?.version || "";
  $("#version-line").textContent = state.health ? `${name} · ${version}` : "数据未就绪";
}

function renderTopChips() {
  const chips = $("#top-chips");
  if (!state.health) {
    chips.innerHTML = '<div class="chip"><span class="dot off"></span>离线</div>';
    return;
  }
  const injection = state.health.injection_enabled;
  const embedding = state.health.embedding_enabled;
  chips.innerHTML = `
    <div class="chip"><span class="dot ${injection ? "on" : "off"}"></span>记忆注入 ${injection ? "开" : "关"}</div>
    <div class="chip"><span class="dot ${embedding ? "on" : "off"}"></span>嵌入召回 ${embedding ? "开" : "关"}</div>
    <div class="chip"><span class="dot on"></span>${fmtNum(state.health.stats?.total_memories)} 条记忆</div>`;
}

async function loadPersonas() {
  try {
    const data = await apiGet("personas");
    state.personas = data.personas || [];
  } catch {
    state.personas = [];
  }
}

async function loadSettings(force) {
  if (state.settingsSchema && !force) return;
  const data = await apiGet("config/schema");
  state.settingsSchema = data.schema || {};
  state.settingsValues = data.values || {};
  state.providerOptions = data.provider_options || [];
  state.embeddingOptions = data.embedding_provider_options || [];
  state.rerankOptions = data.rerank_provider_options || [];
  state.configDiag = {
    config_file_path: data.config_file_path || "",
    config_file_exists: data.config_file_exists,
    disk_snapshot: data.disk_snapshot || {},
    runtime_embedding_enabled: data.runtime_embedding_enabled,
  };
  applyAnimationSettings();
}

/* ================================================================== 动画设置 */

function applyAnimationSettings() {
  const a = (state.settingsValues && state.settingsValues.animation) || {};
  const enabled = a.enabled !== false;
  const duration = Math.max(0, Math.min(1000, parseInt(a.duration_ms, 10) || 200));
  const page = a.page_transition || "fade";
  const accordion = a.accordion || "smooth";
  document.documentElement.style.setProperty("--anim-duration", `${duration}ms`);
  document.body.classList.toggle("anim-off", !enabled || accordion === "none");
  state.anim = {
    enabled,
    page_transition: enabled && page !== "none" ? page : "none",
    duration,
  };
}

function personaName(id) {
  const p = state.personas.find((item) => item.persona_id === id);
  return p ? `${p.name}${p.is_default ? "（默认）" : ""}` : (id || "未指定");
}

/* ================================================================== 总览 */

async function renderOverview() {
  load();
  const data = await apiGet("stats");
  const stats = data.stats || {};
  const maxType = Math.max(1, ...Object.values(stats.memory_types || {}).map(Number));
  const maxScope = Math.max(1, ...Object.values(stats.scopes || {}).map(Number));
  const typeLabels = {
    fact: "事实", preference: "偏好", event: "事件", relationship: "关系",
    promise: "承诺", summary: "总结", note: "笔记", other: "其他",
  };
  $("#view").innerHTML = `
    <div class="card">
      <div class="card-title">记忆统计</div>
      <div class="card-hint">${esc(state.health?.db_path || "")}</div>
      ${Number(stats.archived_memories || 0) > 0 ? `<div class="card-hint" style="opacity:.8">记忆库默认只显示「活跃」记忆；另有 ${fmtNum(stats.archived_memories)} 条已归档/衰减，可在下方「状态」筛选查看（删除某条后若总数仍 >0，通常是在这里）。</div>` : ""}
      <div class="stat-grid">
        <div class="stat"><div class="num">${fmtNum(stats.total_memories)}</div><div class="label">记忆总数</div></div>
        <div class="stat"><div class="num">${fmtNum(stats.active_memories)}</div><div class="label">活跃记忆</div></div>
        <div class="stat"><div class="num">${fmtNum(stats.archived_memories)}</div><div class="label">已归档/衰减</div></div>
        <div class="stat"><div class="num">${fmtNum(stats.timeline_events)}</div><div class="label">时间线事件</div></div>
        <div class="stat">
          <div class="num">${fmtNum(stats.unsummarized_rounds ?? 0)}/${stats.summary_trigger_rounds ?? 8}</div>
          <div class="label">待总结（私聊轮数）</div>
          <div class="hint">${(stats.private_ready_sessions ?? 0) > 0 ? `有 ${stats.private_ready_sessions} 个私聊会话已达标` : `共 ${stats.unsummarized_rounds ?? 0} 轮，满 ${stats.summary_trigger_rounds ?? 8} 轮触发`}</div>
        </div>
        <div class="stat">
          <div class="num">${fmtNum(stats.unsummarized_group_events ?? 0)}/${stats.group_trigger_events ?? 15}</div>
          <div class="label">待总结（群聊事件）</div>
          <div class="hint">${(stats.group_ready_sessions ?? 0) > 0 ? `有 ${stats.group_ready_sessions} 个群会话已达标` : `共 ${stats.unsummarized_group_events ?? 0} 条，满 ${stats.group_trigger_events ?? 15} 条触发`}</div>
        </div>
        <div class="stat"><div class="num">${fmtNum(stats.users)}</div><div class="label">用户</div></div>
        <div class="stat"><div class="num">${fmtNum(stats.embedded_vectors)}</div><div class="label">向量索引</div></div>
        <div class="stat"><div class="num" style="font-size:14px">跟随 AstrBot</div><div class="label">人格隔离</div></div>
      </div>
    </div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px" class="res-grid">
      <div class="card">
        <div class="card-title">按类型分布</div>
        <div class="bars">
          ${Object.entries(stats.memory_types || {})
            .map(([key, value]) => `
              <div class="bar-row">
                <span class="name">${esc(typeLabels[key] || key)}</span>
                <div class="bar-track"><div class="bar-fill" style="width:${(value / maxType) * 100}%"></div></div>
                <span class="val">${fmtNum(value)}</span>
              </div>`)
            .join("") || '<div class="empty">暂无数据</div>'}
        </div>
      </div>
      <div class="card">
        <div class="card-title">按作用域分布</div>
        <div class="bars">
          ${Object.entries(stats.scopes || {})
            .map(([key, value]) => `
              <div class="bar-row">
                <span class="name">${esc({ private: "私聊", group: "群聊", public: "公共" }[key] || key)}</span>
                <div class="bar-track"><div class="bar-fill" style="width:${(value / maxScope) * 100}%"></div></div>
                <span class="val">${fmtNum(value)}</span>
              </div>`)
            .join("") || '<div class="empty">暂无数据</div>'}
        </div>
      </div>
    </div>
    <style>.res-grid{grid-template-columns:1fr 1fr}@media(max-width:900px){.res-grid{grid-template-columns:1fr}}</style>`;
}

/* ================================================================== 记忆库 */

async function renderMemories() {
  load();
  const f = state.memoryFilters;
  const selectMode = state.memSelect?.mode || false;
  const selected = state.memSelect?.ids || new Set();
  const params = {
    limit: 10,
    offset: (state.memoryPage || 0) * 10,
    q: f.q,
    memory_type: f.memory_type,
    scope: f.scope,
    persona_id: f.persona_id,
    lifecycle: f.lifecycle,
  };
  const data = await apiGet("memories", params);
  const rows = data.memories || [];
  const totalMemories = data.total;
  const totalPages = Math.max(1, Math.ceil((data.total || 0) / 10));
  const pageIds = rows.map((m) => m.id);
  const allChecked = pageIds.length > 0 && pageIds.every((id) => selected.has(id));
  $("#view").innerHTML = `
    <div class="card">
      <div class="toolbar">
        <input class="input grow" id="f-q" placeholder="关键词搜索内容/摘要/标签…" value="${esc(f.q)}" />
        <select class="input small" id="f-type">
          <option value="">全部类型</option>
          ${["fact","preference","event","relationship","promise","summary","note","other"]
            .map((t) => `<option value="${t}" ${f.memory_type === t ? "selected" : ""}>${esc(t)}</option>`).join("")}
        </select>
        <select class="input small" id="f-scope">
          <option value="">全部范围</option>
          <option value="private" ${f.scope === "private" ? "selected" : ""}>私聊</option>
          <option value="group" ${f.scope === "group" ? "selected" : ""}>群聊</option>
          <option value="public" ${f.scope === "public" ? "selected" : ""}>公共</option>
        </select>
        <select class="input small" id="f-persona">
          <option value="">全部人格</option>
          ${state.personas.map((p) => `<option value="${esc(p.persona_id)}" ${f.persona_id === p.persona_id ? "selected" : ""}>${esc(p.name)}</option>`).join("")}
        </select>
        <select class="input small" id="f-life">
          <option value="">全部状态</option>
          <option value="active" ${f.lifecycle === "active" ? "selected" : ""}>活跃</option>
          <option value="archived" ${f.lifecycle === "archived" ? "selected" : ""}>归档</option>
          <option value="decayed" ${f.lifecycle === "decayed" ? "selected" : ""}>衰减</option>
        </select>
        <button class="btn primary" id="f-apply">查询</button>
        <button class="btn" id="f-reset">重置</button>
        <button class="btn ${selectMode ? "primary" : ""}" id="f-multi">${selectMode ? "退出多选" : "多选"}</button>
        ${selectMode ? `
          <button class="btn danger" id="f-batch-del" ${selected.size ? "" : "disabled"}>删除选中（${selected.size}）</button>
        ` : ""}
      </div>
      <div class="table-wrap">
        <table>
          <thead><tr>
            ${selectMode ? `<th style="width:36px"><input type="checkbox" id="f-check-all" ${allChecked ? "checked" : ""} /></th>` : ""}
            <th style="width:90px">类型</th><th>内容</th><th>人格</th><th>范围</th>
            <th style="width:70px">重要度</th><th>置信</th><th style="width:110px">创建时间</th><th>操作</th>
          </tr></thead>
          <tbody>
            ${rows.map((m) => `
              <tr>
                ${selectMode ? `<td><input type="checkbox" class="f-row-check" data-id="${esc(m.id)}" ${selected.has(m.id) ? "checked" : ""} /></td>` : ""}
                <td><span class="badge">${esc(m.memory_type)}</span></td>
                <td>
                  <div>${esc(m.content.length > 90 ? m.content.slice(0, 90) + "…" : m.content)}</div>
                  <div class="text-3 mono">${esc(m.id)}</div>
                </td>
                <td>${esc(personaName(m.persona_id))}</td>
                <td>${esc(m.scope)}</td>
                <td class="mono">${m.importance.toFixed(2)}</td>
                <td class="mono">${m.confidence.toFixed(2)}</td>
                <td class="mono text-3">${fmtTime(m.created_at)}</td>
                <td>
                  <div class="row-actions">
                    <button class="btn ghost" data-act="view" data-id="${esc(m.id)}">详情</button>
                    ${selectMode ? "" : `<button class="btn ghost" data-act="del" data-id="${esc(m.id)}">删除</button>`}
                  </div>
                </td>
              </tr>`).join("")}
          </tbody>
        </table>
      </div>
      ${rows.length ? `
        <div class="pager-anchor" style="display:flex;gap:8px;margin-top:12px;align-items:center">
          <button class="btn" id="pg-prev" ${state.memoryPage === 0 ? "disabled" : ""}>上一页</button>
          <span class="text-3" style="font-size:12px">第 ${(state.memoryPage || 0) + 1}/${totalPages} 页 · 每页 10 条${totalMemories != null ? ` · 共 ${fmtNum(totalMemories)} 条` : ""}</span>
          <button class="btn" id="pg-next" ${state.memoryPage + 1 < totalPages ? "" : "disabled"}>下一页</button>
        </div>` : '<div class="empty">暂无记忆</div>'}
    </div>`;
  if (state.pagerScroll) {
    state.pagerScroll = false;
    scrollToPager();
  }

  $("#f-apply").addEventListener("click", () => {
    state.memoryFilters = {
      q: $("#f-q").value.trim(),
      memory_type: $("#f-type").value,
      scope: $("#f-scope").value,
      persona_id: $("#f-persona").value,
      lifecycle: $("#f-life").value,
    };
    state.memoryPage = 0;
    renderMemories();
  });
  $("#f-reset").addEventListener("click", () => {
    state.memoryFilters = { q: "", memory_type: "", scope: "", persona_id: "", lifecycle: "active" };
    state.memoryPage = 0;
    renderMemories();
  });
  $("#f-multi").addEventListener("click", () => {
    state.memSelect = { mode: !selectMode, ids: new Set() };
    renderMemories();
  });
  $("#f-check-all")?.addEventListener("change", () => {
    const ids = state.memSelect.ids;
    if ($("#f-check-all").checked) {
      pageIds.forEach((id) => ids.add(id));
    } else {
      pageIds.forEach((id) => ids.delete(id));
    }
    renderMemories();
  });
  document.querySelectorAll(".f-row-check").forEach((box) =>
    box.addEventListener("change", () => {
      const id = box.dataset.id;
      const ids = state.memSelect.ids;
      if (box.checked) ids.add(id);
      else ids.delete(id);
      $("#f-batch-del").disabled = ids.size === 0;
      $("#f-batch-del").textContent = `删除选中（${ids.size}）`;
    })
  );
  $("#f-batch-del")?.addEventListener("click", () =>
    confirmModal("批量删除记忆", `确定删除选中的 ${state.memSelect.ids.size} 条记忆吗？此操作不可恢复。`, async () => {
      const res = await apiPost("memory/batch_delete", { ids: [...state.memSelect.ids] });
      toast(`已删除 ${res.deleted} 条记忆`, "ok");
      state.memSelect = { mode: false, ids: new Set() };
      renderMemories();
      refreshHealth();
    })
  );
  $("#pg-prev")?.addEventListener("click", () => {
    state.memoryPage = Math.max(0, state.memoryPage - 1);
    state.pagerScroll = true;
    renderMemories();
  });
  $("#pg-next")?.addEventListener("click", () => {
    state.memoryPage += 1;
    state.pagerScroll = true;
    renderMemories();
  });
  document.querySelectorAll('[data-act="view"]').forEach((btn) =>
    btn.addEventListener("click", () => memoryDetail(btn.dataset.id))
  );
  document.querySelectorAll('[data-act="del"]').forEach((btn) =>
    btn.addEventListener("click", () =>
      confirmModal("删除记忆", `确定删除记忆 ${btn.dataset.id} 吗？此操作不可恢复。`, async () => {
        const res = await apiPost("memory/delete", { id: btn.dataset.id });
        if (res.deleted) toast("已删除", "ok");
        renderMemories();
      })
    )
  );
}

async function memoryDetail(id) {
  const data = await apiGet("memory", { id });
  const m = data.memory;
  const factors = Object.entries(m.weight_factors || {})
    .map(([k, v]) => `${k}=${v}`)
    .join("，");
  modal(`
    <h3>记忆详情 <span class="mono text-3" style="font-size:12px">${esc(m.id)}</span></h3>
    <div class="form-row">
      <label>内容</label>
      <textarea rows="3" id="m-content">${esc(m.content)}</textarea>
    </div>
    <div class="form-row">
      <label>摘要</label>
      <input id="m-summary" value="${esc(m.summary)}" />
    </div>
    <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px">
      <div class="form-row"><label>类型</label>
        <select id="m-type">
          ${["fact","preference","event","relationship","promise","summary","note","other"]
            .map((t) => `<option ${m.memory_type === t ? "selected" : ""}>${t}</option>`).join("")}
        </select>
      </div>
      <div class="form-row"><label>人格</label>
        <select id="m-persona">
          ${state.personas.map((p) => `<option value="${esc(p.persona_id)}" ${m.persona_id === p.persona_id ? "selected" : ""}>${esc(p.name)}</option>`).join("")}
        </select>
      </div>
      <div class="form-row"><label>状态</label>
        <select id="m-life">
          ${["active","archived","decayed"].map((l) => `<option ${m.lifecycle === l ? "selected" : ""}>${l}</option>`).join("")}
        </select>
      </div>
    </div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">
      <div class="form-row"><label>重要度 0-1（当前 ${m.importance.toFixed(2)}）</label>
        <input id="m-importance" type="number" min="0" max="1" step="0.05" value="${m.importance}" />
      </div>
      <div class="form-row"><label>置信度 0-1</label>
        <input id="m-confidence" type="number" min="0" max="1" step="0.05" value="${m.confidence}" />
      </div>
    </div>
    <div class="meta-grid">
      <div class="meta-item"><div class="k">主体</div><div class="v">${esc(m.subject.kind)}:${esc(m.subject.name || m.subject.id)}（${esc(m.subject.role)}）</div></div>
      <div class="meta-item"><div class="k">客体</div><div class="v">${esc(m.object.kind)}:${esc(m.object.name || m.object.id)}（${esc(m.object.role)}）</div></div>
      <div class="meta-item"><div class="k">身份验证</div><div class="v">${m.subject.verified ? "已验证" : "未验证"} / ${esc(m.subject.verified_by || "-")}</div></div>
      <div class="meta-item"><div class="k">来源</div><div class="v">${esc(m.source)} · ${esc(m.source_plugin)}</div></div>
      <div class="meta-item"><div class="k">用户/群</div><div class="v">${esc(m.user_name || m.user_id || "-")} / ${esc(m.group_name || m.group_id || "-")}</div></div>
      <div class="meta-item"><div class="k">会话</div><div class="v">${esc(m.session_id || "-")}</div></div>
      <div class="meta-item"><div class="k">创建 / 更新</div><div class="v">${fmtTime(m.created_at)} / ${fmtTime(m.updated_at)}</div></div>
      <div class="meta-item"><div class="k">召回次数</div><div class="v">${m.access_count} · 上次 ${fmtTime(m.last_accessed_at)}</div></div>
      <div class="meta-item"><div class="k">权重因子</div><div class="v">${esc(factors || "-")}</div></div>
      <div class="meta-item"><div class="k">指纹</div><div class="v">${esc(m.content_fingerprint.slice(0, 16))}…</div></div>
      ${(m.tags || []).length ? `<div class="meta-item"><div class="k">标签</div><div class="v">${esc((m.tags || []).join("、"))}</div></div>` : ""}
    </div>
    <div style="display:flex;gap:10px;justify-content:flex-end;margin-top:16px">
      <button class="btn" id="m-save">保存修改</button>
    </div>`);
  $("#m-save").addEventListener("click", async () => {
    const body = {
      id,
      content: $("#m-content").value,
      summary: $("#m-summary").value,
      memory_type: $("#m-type").value,
      persona_id: $("#m-persona").value,
      lifecycle: $("#m-life").value,
      importance: parseFloat($("#m-importance").value),
      confidence: parseFloat($("#m-confidence").value),
    };
    const res = await apiPost("memory/update", body);
    if (res.updated) {
      toast("已保存", "ok");
      closeModal();
      renderMemories();
    }
  });
}

/* ================================================================== 人格 */

/* ================================================================== 用户 */

async function renderUsers() {
  load();
  const limit = 10;
  const offset = (state.usersPage || 0) * limit;
  const data = await apiGet("users", { limit, offset });
  const users = data.users || [];
  const totalPages = Math.max(1, Math.ceil((data.total || 0) / limit));
  $("#view").innerHTML = `
    <div class="card">
      <div class="card-title">用户列表</div>
      <div class="card-hint">记忆按 AstrBot 会话人格与用户隔离；此处可查看最近活跃用户并删除其私聊记忆。每页 10 条。</div>
      <div class="table-wrap">
        <table>
          <thead><tr>
            <th>用户</th><th>平台</th><th>上次活跃</th><th>操作</th>
          </tr></thead>
          <tbody>
            ${users.map((u) => `
              <tr>
                <td><div>${esc(u.name || "-")}</div><div class="mono text-3">${esc(u.user_key)}</div></td>
                <td>${esc(u.platform || "-")}</td>
                <td class="mono text-3">${fmtTime(u.last_seen)}</td>
                <td><button class="btn ghost" data-act="del" data-key="${esc(u.user_key)}">删除</button></td>
              </tr>`).join("")}
          </tbody>
        </table>
      </div>
      ${users.length ? `
        <div class="pager-anchor" style="display:flex;gap:8px;margin-top:12px;align-items:center">
          <button class="btn" id="us-prev" ${state.usersPage === 0 ? "disabled" : ""}>上一页</button>
          <span class="text-3" style="font-size:12px">第 ${(state.usersPage || 0) + 1}/${totalPages} 页 · 每页 10 条</span>
          <button class="btn" id="us-next" ${(state.usersPage || 0) + 1 < totalPages ? "" : "disabled"}>下一页</button>
        </div>` : '<div class="empty">还没有用户记录</div>'}
    </div>`;
  if (state.pagerScroll) {
    state.pagerScroll = false;
    scrollToPager();
  }
  $("#us-prev")?.addEventListener("click", () => {
    state.usersPage = Math.max(0, (state.usersPage || 0) - 1);
    state.pagerScroll = true;
    renderUsers();
  });
  $("#us-next")?.addEventListener("click", () => {
    state.usersPage = (state.usersPage || 0) + 1;
    state.pagerScroll = true;
    renderUsers();
  });
  document.querySelectorAll('[data-act="del"]').forEach((btn) =>
    btn.addEventListener("click", () =>
      confirmModal("删除用户", `删除用户 ${btn.dataset.key} 将同时删除其全部私聊记忆，确定吗？`, async () => {
        const res = await apiPost("user/delete", { user_key: btn.dataset.key });
        toast(`已删除，移除 ${res.removed_memories} 条记忆`, "ok");
        renderUsers();
      })
    )
  );
}

/* ================================================================== 检索测试 */

async function renderSearch() {
  load();
  $("#view").innerHTML = `
    <div class="card">
      <div class="card-title">模拟检索</div>
      <div class="card-hint">模拟某个会话视角检索记忆，验证隔离规则与混合召回效果。</div>
      <div class="toolbar">
        <input class="input grow" id="s-q" placeholder="检索关键词或自然语言问题" />
        <select class="input small" id="s-scope">
          <option value="private">私聊</option>
          <option value="group">群聊</option>
          <option value="public">公共</option>
        </select>
        <input class="input small" id="s-user" placeholder="user_id" />
        <input class="input small" id="s-group" placeholder="group_id" />
        <select class="input small" id="s-persona">
          ${state.personas.map((p) => `<option value="${esc(p.persona_id)}">${esc(p.name)}</option>`).join("")}
        </select>
        <input class="input small" id="s-k" type="number" value="8" min="1" max="50" style="width:70px" />
        <label class="chip" style="cursor:pointer"><input type="checkbox" id="s-admin" /> 管理员视角</label>
        <button class="btn primary" id="s-run">检索</button>
      </div>
      <div id="s-result"></div>
    </div>`;
  $("#s-run").addEventListener("click", async () => {
    const q = $("#s-q").value.trim();
    if (!q) return toast("请输入检索词", "err");
    const box = $("#s-result");
    box.innerHTML = '<div class="loading">检索中…</div>';
    const params = {
      q,
      scope: $("#s-scope").value,
      user_id: $("#s-user").value.trim(),
      group_id: $("#s-group").value.trim(),
      persona_id: $("#s-persona").value,
      top_k: parseInt($("#s-k").value) || 8,
      admin: $("#s-admin").checked ? "true" : "",
    };
    const data = await apiGet("search", params);
    const results = data.results || [];
    box.innerHTML = `
      <div class="text-3" style="font-size:12px;margin:6px 0 10px">
        上下文：${esc(data.context.scope)}${data.context.persona_id ? " · 人格 " + esc(data.context.persona_id) : ""}
        ${data.context.user_id ? " · user " + esc(data.context.user_id) : ""}
        ${data.context.group_id ? " · group " + esc(data.context.group_id) : ""}
        　共 ${results.length} 条
      </div>
      ${results.map((m, i) => `
        <div class="card" style="margin-bottom:10px;padding:14px 16px">
          <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:6px">
            <span class="badge">${esc(m.memory_type)}</span>
            <span class="badge green">相关度 ${m.score.toFixed(3)}</span>
            <span class="badge soft">${esc(m.reason)}</span>
            <span class="badge">${esc(personaName(m.persona_id))}</span>
            <span class="text-3 mono" style="font-size:11px">${fmtTime(m.created_at)}</span>
          </div>
          <div>${esc(m.content)}</div>
          <div class="text-3" style="font-size:12px;margin-top:4px">
            重要度 ${m.importance.toFixed(2)} · 置信 ${m.confidence.toFixed(2)} · 召回 ${m.access_count} 次
            ${m.summary ? " · 摘要：" + esc(m.summary) : ""}
          </div>
        </div>`).join("") || '<div class="empty">没有召回结果</div>'}`;
  });
}

/* ================================================================== 时间线 */

async function renderTimeline() {
  load();
  let statsData = null;
  try {
    statsData = await apiGet("stats");
  } catch { /* ignore */ }
  const stats = statsData?.stats || {};
  const rounds = stats.unsummarized_rounds ?? 0;
  const trigger = stats.summary_trigger_rounds ?? 8;
  const groupEvents = stats.unsummarized_group_events ?? 0;
  const groupTrigger = stats.group_trigger_events ?? 15;
  const limit = 10;
  const offset = (state.timelinePage || 0) * limit;
  const selectMode = state.tlSelect?.mode || false;
  const selected = state.tlSelect?.ids || new Set();
  const data = await apiGet("timeline", { limit, offset });
  const items = data.items || [];
  const totalPages = Math.max(1, Math.ceil((data.total || 0) / limit));
  const pageIds = items.map((e) => e.id);
  const allChecked = pageIds.length > 0 && pageIds.every((id) => selected.has(id));
  $("#view").innerHTML = `
    <div class="card">
      <div class="card-title">最近时间线事件</div>
      <div class="card-hint">时间线是原始对话流水：私聊按「对话轮」累计，群聊按「事件条数」累计（每个会话独立计数）；达到阈值后总结为一条长期记忆。记忆库的导入导出、删改会以红字记录在此。</div>
      <div style="margin-bottom:12px">
        <span class="chip">
          <span class="dot ${rounds >= trigger ? "on" : ""}"></span>
          私聊 ${rounds}/${trigger} 轮${rounds >= trigger ? "（已达标）" : ""}
        </span>
        <span class="chip">
          <span class="dot ${groupEvents >= groupTrigger ? "on" : ""}"></span>
          群聊 ${groupEvents}/${groupTrigger} 条${groupEvents >= groupTrigger ? "（已达标）" : ""}
        </span>
        ${(stats.private_ready_sessions ?? 0) > 0 || (stats.group_ready_sessions ?? 0) > 0
          ? `<span class="chip">达标会话：私聊 ${stats.private_ready_sessions ?? 0} · 群聊 ${stats.group_ready_sessions ?? 0}</span>` : ""}
        ${stats.unsummarized_events != null ? `<span class="chip">未总结事件 ${stats.unsummarized_events} 条</span>` : ""}
        ${stats.timeline_events != null ? `<span class="chip">时间线共 ${fmtNum(stats.timeline_events)} 条 · 每页 10 条</span>` : ""}
        <button class="btn ${selectMode ? "primary" : ""}" id="tl-multi" style="margin-left:4px">${selectMode ? "退出多选" : "多选"}</button>
        ${selectMode ? `<button class="btn danger" id="tl-batch-del" ${selected.size ? "" : "disabled"}>删除选中（${selected.size}）</button>` : ""}
      </div>
      <div class="table-wrap">
        <table>
          <thead><tr>
            ${selectMode ? `<th style="width:36px"><input type="checkbox" id="tl-check-all" ${allChecked ? "checked" : ""} /></th>` : ""}
            <th style="width:140px">时间</th><th style="width:80px">角色</th><th style="width:80px">范围</th><th>内容</th><th style="width:110px">状态</th>${selectMode ? "" : `<th style="width:70px">操作</th>`}
          </tr></thead>
          <tbody>
            ${items.map((e) => `
              <tr>
                ${selectMode ? `<td><input type="checkbox" class="tl-row-check" data-id="${esc(e.id)}" ${selected.has(e.id) ? "checked" : ""} /></td>` : ""}
                <td class="mono text-3">${fmtTime(e.occurred_at)}</td>
                <td><span class="badge ${e.role === "bot" ? "green" : "soft"}">${esc(e.role)}</span></td>
                <td>${esc(e.scope)}</td>
                <td style="${e.kind === "op" ? "color:var(--danger)" : ""}">${esc(e.content.length > 140 ? e.content.slice(0, 140) + "…" : e.content)}</td>
                <td>${e.summarized ? '<span class="badge green">已总结</span>' : e.kind === "op" ? '<span class="badge red">记忆操作</span>' : e.is_system ? '<span class="badge soft">系统通知</span>' : '<span class="badge warn">待总结</span>'}</td>
                ${selectMode ? "" : `<td><button class="btn ghost" data-act="tl-del" data-id="${esc(e.id)}">删除</button></td>`}
              </tr>`).join("")}
          </tbody>
        </table>
      </div>
      ${items.length ? `
        <div class="pager-anchor" style="display:flex;gap:8px;margin-top:12px;align-items:center">
          <button class="btn" id="tl-prev" ${state.timelinePage === 0 ? "disabled" : ""}>上一页</button>
          <span class="text-3" style="font-size:12px">第 ${(state.timelinePage || 0) + 1}/${totalPages} 页 · 每页 10 条</span>
          <button class="btn" id="tl-next" ${(state.timelinePage || 0) + 1 < totalPages ? "" : "disabled"}>下一页</button>
        </div>` : '<div class="empty">暂无时间线事件</div>'}
    </div>`;
  if (state.pagerScroll) {
    state.pagerScroll = false;
    scrollToPager();
  }
  $("#tl-multi").addEventListener("click", () => {
    state.tlSelect = { mode: !selectMode, ids: new Set() };
    renderTimeline();
  });
  $("#tl-check-all")?.addEventListener("change", () => {
    const ids = state.tlSelect.ids;
    if ($("#tl-check-all").checked) pageIds.forEach((id) => ids.add(id));
    else pageIds.forEach((id) => ids.delete(id));
    renderTimeline();
  });
  document.querySelectorAll(".tl-row-check").forEach((box) =>
    box.addEventListener("change", () => {
      const id = box.dataset.id;
      const ids = state.tlSelect.ids;
      if (box.checked) ids.add(id);
      else ids.delete(id);
      $("#tl-batch-del").disabled = ids.size === 0;
      $("#tl-batch-del").textContent = `删除选中（${ids.size}）`;
    })
  );
  $("#tl-batch-del")?.addEventListener("click", () =>
    confirmModal("批量删除时间线", `确定删除选中的 ${state.tlSelect.ids.size} 条时间线事件吗？此操作不可恢复。`, async () => {
      const res = await apiPost("timeline/delete", { ids: [...state.tlSelect.ids] });
      toast(`已删除 ${res.deleted} 条事件`, "ok");
      state.tlSelect = { mode: false, ids: new Set() };
      renderTimeline();
    })
  );
  document.querySelectorAll('[data-act="tl-del"]').forEach((btn) =>
    btn.addEventListener("click", () =>
      confirmModal("删除时间线事件", "确定删除这条时间线事件吗？此操作不可恢复。", async () => {
        const res = await apiPost("timeline/delete", { ids: [btn.dataset.id] });
        if (res.deleted) toast("已删除", "ok");
        renderTimeline();
      })
    )
  );
  $("#tl-prev")?.addEventListener("click", () => {
    state.timelinePage = Math.max(0, (state.timelinePage || 0) - 1);
    state.pagerScroll = true;
    renderTimeline();
  });
  $("#tl-next")?.addEventListener("click", () => {
    state.timelinePage = (state.timelinePage || 0) + 1;
    state.pagerScroll = true;
    renderTimeline();
  });
}

/* ================================================================== 导入导出 */

async function renderTransfer() {
  load();
  $("#view").innerHTML = `
    <div class="card">
      <div class="card-title">手动记忆管理</div>
      <div class="card-hint">手动新增、修改、删除记忆条目；可填写时间、地点、人物、总结等字段。</div>
      <div class="toolbar">
        <input class="input grow" id="mm-q" placeholder="搜索记忆内容…" />
        <button class="btn" id="mm-search">搜索</button>
        <button class="btn primary" id="mm-create">+ 新增记忆</button>
      </div>
      <div id="mm-list"></div>
    </div>
    <div class="card">
      <div class="card-title">导出记忆</div>
      <div class="card-hint">导出为 JSONL（每行一条）或 JSON 档案，包含全部字段（身份验证、时间戳、权重、元数据等）。</div>
      <div class="toolbar">
        <select class="input small" id="e-format">
          <option value="jsonl">JSONL</option>
          <option value="json">JSON</option>
        </select>
        <select class="input small" id="e-scope">
          <option value="">全部范围</option>
          <option value="private">私聊</option>
          <option value="group">群聊</option>
          <option value="public">公共</option>
        </select>
        <select class="input small" id="e-persona">
          <option value="">全部人格</option>
          ${state.personas.map((p) => `<option value="${esc(p.persona_id)}">${esc(p.name)}</option>`).join("")}
        </select>
        <button class="btn primary" id="e-run">导出并下载</button>
      </div>
    </div>
    <div class="card">
      <div class="card-title">导入记忆</div>
      <div class="card-hint">上传 JSONL / JSON 档案。先预览，再确认人格映射与去重策略后执行；导入前自动备份数据库。</div>
      <div class="drop-zone" id="drop-zone">点击或拖拽文件到此处（≤ 64 MiB）</div>
      <input type="file" id="import-file" class="hidden" accept=".jsonl,.json" />
      <div id="import-preview"></div>
    </div>
    <div class="card">
      <div class="card-title">导入历史</div>
      <div id="batch-list"></div>
    </div>`;

  $("#mm-create").addEventListener("click", () => manualMemoryModal(null));
  const searchManual = () => {
    state.mmPage = 0;
    loadManualMemories($("#mm-q").value.trim());
  };
  $("#mm-search").addEventListener("click", searchManual);
  $("#mm-q").addEventListener("keydown", (e) => {
    if (e.key === "Enter") searchManual();
  });
  loadManualMemories("");

  $("#e-run").addEventListener("click", async () => {
    const params = {
      format: $("#e-format").value,
      scope: $("#e-scope").value,
      persona_id: $("#e-persona").value,
    };
    toast("正在生成导出文件…");
    try {
      // 先生成档案并拿到文件路径（兼容 AstrBot Launcher 内置浏览器无法触发下载的场景）
      const archive = await apiPost("export/archive", params);
      const filePath = archive.path || "";
      if (filePath) {
        toast(`已导出：${filePath}`, "ok");
      }
      // 普通浏览器环境继续触发下载
      await bridge.download("export", params, `deepmemory_export_${Date.now()}.${$("#e-format").value}`);
      if (!filePath) toast("导出完成", "ok");
    } catch (err) {
      toast(err.message || "导出失败", "err");
    }
  });

  const zone = $("#drop-zone");
  const fileInput = $("#import-file");
  zone.addEventListener("click", () => fileInput.click());
  fileInput.addEventListener("change", () => handleImportFile(fileInput.files[0]));
  zone.addEventListener("dragover", (e) => {
    e.preventDefault();
    zone.classList.add("drag");
  });
  zone.addEventListener("dragleave", () => zone.classList.remove("drag"));
  zone.addEventListener("drop", (e) => {
    e.preventDefault();
    zone.classList.remove("drag");
    if (e.dataTransfer.files.length) handleImportFile(e.dataTransfer.files[0]);
  });

  loadBatches();
}

async function loadManualMemories(q) {
  const box = $("#mm-list");
  box.innerHTML = '<div class="loading">加载中…</div>';
  const limit = 10;
  const offset = (state.mmPage || 0) * limit;
  const data = await apiGet("memories", {
    limit,
    offset,
    q: q || "",
    lifecycle: "",
    order_by: "occurred_at DESC",
  });
  const rows = data.memories || [];
  const totalPages = Math.max(1, Math.ceil((data.total || 0) / limit));
  let total = data.total != null ? data.total : null;
  box.innerHTML = `
    <div class="text-3" style="font-size:12px;margin-bottom:8px">${total != null ? `记忆库共 ${fmtNum(total)} 条 · ` : ""}每页 10 条（如需管理全部记忆请使用「记忆库」页）</div>
    <div class="table-wrap">
      <table>
        <thead><tr>
          <th style="width:130px">时间</th><th style="width:70px">类型</th><th>内容</th>
          <th style="width:80px">人物</th><th style="width:90px">地点</th><th style="width:70px">重要度</th><th>操作</th>
        </tr></thead>
        <tbody>
          ${rows.map((m) => `
            <tr>
              <td class="mono text-3">${fmtTime(m.occurred_at || m.created_at)}</td>
              <td><span class="badge">${esc(m.memory_type)}</span></td>
              <td>
                <div>${esc((m.content || "").length > 70 ? m.content.slice(0, 70) + "…" : m.content)}</div>
                <div class="text-3 mono" style="font-size:11px">${esc(m.id)}</div>
              </td>
              <td class="text-2">${esc((m.metadata?.participants || []).join("、") || "-")}</td>
              <td class="text-2">${esc(m.metadata?.location || "-")}</td>
              <td class="mono">${m.importance != null ? m.importance.toFixed(2) : "-"}</td>
              <td>
                <div class="row-actions">
                  <button class="btn ghost" data-act="edit" data-id="${esc(m.id)}">编辑</button>
                  <button class="btn ghost" data-act="del" data-id="${esc(m.id)}">删除</button>
                </div>
              </td>
            </tr>`).join("")}
        </tbody>
      </table>
    </div>
    ${rows.length ? `
      <div class="pager-anchor" style="display:flex;gap:8px;margin-top:12px;align-items:center">
        <button class="btn" id="mm-prev" ${state.mmPage === 0 ? "disabled" : ""}>上一页</button>
        <span class="text-3" style="font-size:12px">第 ${(state.mmPage || 0) + 1}/${totalPages} 页 · 每页 10 条</span>
        <button class="btn" id="mm-next" ${(state.mmPage || 0) + 1 < totalPages ? "" : "disabled"}>下一页</button>
      </div>` : '<div class="empty">暂无记忆条目，点击「+ 新增记忆」创建</div>'}`;
  if (state.pagerScroll) {
    state.pagerScroll = false;
    scrollToPager();
  }
  $("#mm-prev")?.addEventListener("click", () => {
    state.mmPage = Math.max(0, (state.mmPage || 0) - 1);
    state.pagerScroll = true;
    loadManualMemories($("#mm-q").value.trim());
  });
  $("#mm-next")?.addEventListener("click", () => {
    state.mmPage = (state.mmPage || 0) + 1;
    state.pagerScroll = true;
    loadManualMemories($("#mm-q").value.trim());
  });
  document.querySelectorAll('[data-act="edit"]').forEach((btn) =>
    btn.addEventListener("click", () => manualMemoryModal(btn.dataset.id))
  );
  document.querySelectorAll('[data-act="del"]').forEach((btn) =>
    btn.addEventListener("click", () =>
      confirmModal("删除记忆条目", `确定删除记忆 ${btn.dataset.id} 吗？此操作不可恢复。`, async () => {
        const res = await apiPost("memory/delete", { id: btn.dataset.id });
        if (res.deleted) {
          toast("已删除", "ok");
          loadManualMemories($("#mm-q").value.trim());
        }
      })
    )
  );
}

function manualMemoryModal(memoryId) {
  const isEdit = Boolean(memoryId);
  const typeOptions = ["fact", "preference", "event", "relationship", "promise", "summary", "note", "other"]
    .map((t) => `<option value="${t}">${esc(t)}</option>`)
    .join("");
  const personaOptions = state.personas
    .map((p) => `<option value="${esc(p.persona_id)}">${esc(p.name)}</option>`)
    .join("");
  modal(`
    <h3>${isEdit ? "编辑记忆条目" : "新增记忆条目"} ${isEdit ? `<span class="mono text-3" style="font-size:12px">${esc(memoryId)}</span>` : ""}</h3>
    <div class="form-row">
      <label>内容 *</label>
      <textarea rows="3" id="mm-content"></textarea>
    </div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
      <div class="form-row">
        <label>时间（发生时间）</label>
        <input type="datetime-local" id="mm-occurred" />
      </div>
      <div class="form-row">
        <label>地点</label>
        <input id="mm-location" placeholder="如：人民公园" />
      </div>
    </div>
    <div class="form-row">
      <label>人物（逗号或顿号分隔）</label>
      <input id="mm-participants" placeholder="如：小明、小红" />
    </div>
    <div class="form-row">
      <label>总结（可选）</label>
      <input id="mm-summary" placeholder="一句话总结" />
    </div>
    <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px">
      <div class="form-row"><label>类型</label><select id="mm-type">${typeOptions}</select></div>
      <div class="form-row"><label>重要度 0-1</label><input id="mm-importance" type="number" min="0" max="1" step="0.05" value="0.5" /></div>
      <div class="form-row"><label>置信度 0-1</label><input id="mm-confidence" type="number" min="0" max="1" step="0.05" value="0.7" /></div>
    </div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
      <div class="form-row"><label>标签（逗号分隔）</label><input id="mm-tags" placeholder="如：日常、美食" /></div>
      <div class="form-row"><label>人格（AstrBot 人格 ID，留空=默认）</label><select id="mm-persona">${personaOptions}</select></div>
    </div>
    <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px">
      <div class="form-row">
        <label>范围</label>
        <select id="mm-scope">
          <option value="private">私聊</option>
          <option value="group">群聊</option>
          <option value="public">公共</option>
        </select>
      </div>
      <div class="form-row"><label>归属用户 ID</label><input id="mm-user-id" placeholder="可选" /></div>
      <div class="form-row"><label>用户昵称</label><input id="mm-user-name" placeholder="可选" /></div>
    </div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
      <div class="form-row"><label>归属群 ID</label><input id="mm-group-id" placeholder="可选" /></div>
      <div class="form-row"><label>群名称</label><input id="mm-group-name" placeholder="可选" /></div>
    </div>
    <div style="display:flex;gap:10px;justify-content:flex-end;margin-top:14px">
      <button class="btn" data-close>取消</button>
      <button class="btn primary" id="mm-save">${isEdit ? "保存修改" : "新增"}</button>
    </div>`);

  if (isEdit) {
    apiGet("memory", { id: memoryId }).then((data) => {
      const m = data.memory || {};
      $("#mm-content").value = m.content || "";
      $("#mm-summary").value = m.summary || "";
      $("#mm-occurred").value = isoToLocalInput(m.occurred_at || m.created_at);
      $("#mm-location").value = m.metadata?.location || "";
      $("#mm-participants").value = (m.metadata?.participants || []).join("、");
      $("#mm-type").value = m.memory_type || "fact";
      $("#mm-importance").value = m.importance ?? 0.5;
      $("#mm-confidence").value = m.confidence ?? 0.7;
      $("#mm-tags").value = (m.tags || []).join("、");
      $("#mm-persona").value = m.persona_id || "";
      $("#mm-scope").value = m.scope || "private";
      $("#mm-user-id").value = m.user_id || "";
      $("#mm-user-name").value = m.user_name || "";
      $("#mm-group-id").value = m.group_id || "";
      $("#mm-group-name").value = m.group_name || "";
    }).catch(() => toast("加载记忆详情失败", "err"));
  }

  $("#mm-save").addEventListener("click", async () => {
    const content = $("#mm-content").value.trim();
    if (!content) return toast("内容不能为空", "err");
    const body = {
      content,
      summary: $("#mm-summary").value.trim(),
      occurred_at: localInputToIso($("#mm-occurred").value),
      location: $("#mm-location").value.trim(),
      participants: $("#mm-participants").value.trim(),
      memory_type: $("#mm-type").value,
      importance: parseFloat($("#mm-importance").value),
      confidence: parseFloat($("#mm-confidence").value),
      tags: $("#mm-tags").value.trim(),
      persona_id: $("#mm-persona").value,
      scope: $("#mm-scope").value,
      user_id: $("#mm-user-id").value.trim(),
      user_name: $("#mm-user-name").value.trim(),
      group_id: $("#mm-group-id").value.trim(),
      group_name: $("#mm-group-name").value.trim(),
    };
    try {
      if (isEdit) {
        await apiPost("memory/update", { ...body, id: memoryId });
        toast("已保存修改", "ok");
      } else {
        await apiPost("memory/create", body);
        toast("已新增记忆", "ok");
      }
      closeModal();
      loadManualMemories($("#mm-q").value.trim());
      refreshHealth();
    } catch (err) {
      /* 错误已由 apiPost 提示 */
    }
  });
}

async function handleImportFile(file) {
  if (!file) return;
  const box = $("#import-preview");
  box.innerHTML = '<div class="loading">上传并预览中…</div>';
  try {
    const result = await bridge.upload("import/preview", file);
    const preview = result.preview;
    if (!result.path) throw new Error("上传失败");
    state.pendingImport = { path: result.path, preview };
    renderImportPreview();
  } catch (err) {
    box.innerHTML = `<div class="empty">预览失败：${esc(err.message || "未知错误")}</div>`;
  }
}

function renderImportPreview() {
  const box = $("#import-preview");
  const { path, preview } = state.pendingImport;
  const foundPersonas = preview.personas || [];
  box.innerHTML = `
    <div style="margin-top:14px">
      <div class="card" style="margin-bottom:10px;padding:14px">
        <div style="display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-bottom:10px">
          <span class="badge green">${preview.total} 条记忆</span>
          <span class="badge ${preview.error_count ? "warn" : "soft"}">${preview.error_count} 条解析问题</span>
          <span class="mono text-3">${esc(path.split("/").pop())}</span>
        </div>
        ${preview.errors && preview.errors.length ? `<div class="text-3" style="font-size:12px;margin-bottom:8px">${preview.errors.slice(0, 5).map(esc).join("<br/>")}</div>` : ""}
        <div class="toolbar">
          <label class="text-2" style="font-size:12.5px">人格映射：</label>
          ${foundPersonas.map((p) => `
            <span class="text-3" style="font-size:12px">${esc(p)} →</span>
            <select class="input small" data-map="${esc(p)}" style="min-width:140px">
              <option value="">保持原样</option>
              ${state.personas.map((t) => `<option value="${esc(t.persona_id)}">${esc(t.name)}</option>`).join("")}
            </select>`).join("") || '<span class="text-3" style="font-size:12px">未发现指定人格字段</span>'}
        </div>
        <div class="toolbar">
          <label class="chip" style="cursor:pointer"><input type="checkbox" id="im-merge" checked /> 跳过重复（按内容指纹）</label>
          <button class="btn primary" id="im-run">开始导入</button>
        </div>
      </div>
      <div class="preview-grid">
        ${(preview.samples || []).map((m) => `
          <div class="preview-item">
            <div class="badge">${esc(m.memory_type)}</div>
            <div class="text-3">${esc(m.persona_id)}</div>
            <div style="margin-top:4px">${esc(m.content.length > 60 ? m.content.slice(0, 60) + "…" : m.content)}</div>
          </div>`).join("")}
      </div>
    </div>`;
  $("#im-run").addEventListener("click", async () => {
    const persona_mapping = {};
    document.querySelectorAll("[data-map]").forEach((sel) => {
      if (sel.value) persona_mapping[sel.dataset.map] = sel.value;
    });
    const btn = $("#im-run");
    btn.disabled = true;
    btn.textContent = "导入中…";
    try {
      const res = await apiPost("import/run", {
        path,
        persona_mapping,
        merge_duplicates: $("#im-merge").checked,
      });
      toast(`导入完成：成功 ${res.result.imported} 条，跳过 ${res.result.skipped} 条`, "ok");
      state.pendingImport = null;
      box.innerHTML = "";
      loadBatches();
      refreshHealth();
    } catch (err) {
      btn.disabled = false;
      btn.textContent = "开始导入";
    }
  });
}

async function loadBatches() {
  const box = $("#batch-list");
  try {
    const data = await apiGet("import/batches");
    const batches = data.batches || [];
    box.innerHTML = `
      <div class="text-3" style="font-size:12px;margin-bottom:8px">显示最近 30 条导入记录</div>
      ${batches.length
      ? `<table class="table-wrap" style="width:100%">
          <thead><tr><th>批次</th><th>文件</th><th>状态</th><th>总数</th><th>导入</th><th>跳过</th><th>时间</th></tr></thead>
          <tbody>${batches.map((b) => `
            <tr>
              <td class="mono">${esc(b.batch_id)}</td>
              <td>${esc(b.filename)}</td>
              <td><span class="badge ${b.status === "done" ? "green" : b.status === "failed" ? "red" : "warn"}">${esc(b.status)}</span></td>
              <td class="mono">${b.total}</td>
              <td class="mono">${b.imported}</td>
              <td class="mono">${b.skipped}</td>
              <td class="mono text-3">${fmtTime(b.created_at)}</td>
            </tr>`).join("")}</tbody>
        </table>`
      : '<div class="empty">暂无导入记录</div>'}`;
  } catch {
    box.innerHTML = '<div class="empty">读取失败</div>';
  }
}

/* ================================================================== 维护 */

async function renderMaintenance() {
  load();
  const health = state.health || {};
  $("#view").innerHTML = `
    <div class="stat-grid" style="margin-bottom:16px">
      <div class="stat"><div class="num">${health.last_maintenance_at ? fmtTime(health.last_maintenance_at) : "从未"}</div><div class="label">上次维护</div></div>
      <div class="stat"><div class="num">${fmtNum(health.stats?.timeline_events || 0)}</div><div class="label">时间线事件</div></div>
      <div class="stat"><div class="num">${fmtNum(health.stats?.archived_memories || 0)}</div><div class="label">已归档记忆</div></div>
    </div>
    <div class="card">
      <div class="card-title">运行维护</div>
      <div class="card-hint">执行记忆衰减（每日减权 + 按权重阈值压缩/归档/删除低价值记忆）与保留清理（清理已总结的过期时间线）。</div>
      <div class="toolbar">
        <button class="btn primary" id="mt-run">立即维护</button>
        <button class="btn" id="mt-decay">立即执行衰减检测</button>
      </div>
      <div id="mt-report"></div>
    </div>
    <div class="card">
      <div class="card-title">危险操作</div>
      <div class="card-hint">清空前会自动备份数据库到 data/backups。</div>
      <div class="toolbar">
        <button class="btn" id="bk-run">立即备份数据库</button>
        <button class="btn danger" id="clear-run">清空全部记忆数据</button>
      </div>
    </div>`;
  $("#mt-run").addEventListener("click", async () => {
    const reportBox = $("#mt-report");
    reportBox.innerHTML = '<div class="loading">维护中…</div>';
    const res = await apiPost("maintenance/run");
    const decay = res.report.decay;
    const dailyDecay = res.report.daily_decay;
    const retention = res.report.retention;
    const decayLine = decay.ok ? `处理 ${decay.processed} 条（${decay.mode}）` : "衰减未启用";
    const dailyLine = dailyDecay.ok
      ? `处理 ${dailyDecay.processed} 条，归档判定 ${dailyDecay.archived} 条（${dailyDecay.rate_percent}%/天）`
      : "每日减权未启用";
    reportBox.innerHTML = `
      <div class="card" style="margin-top:12px">
        <div class="meta-grid" style="grid-template-columns:1fr 1fr">
          <div class="meta-item"><div class="k">每日减权</div><div class="v">${esc(dailyLine)}</div></div>
          <div class="meta-item"><div class="k">记忆衰减</div><div class="v">${esc(decayLine)}</div></div>
          <div class="meta-item"><div class="k">时间线清理</div><div class="v">${retention.timeline_removed} 条</div></div>
        </div>
      </div>`;
    toast("维护完成", "ok");
    refreshHealth();
  });
  $("#mt-decay").addEventListener("click", async () => {
    const reportBox = $("#mt-report");
    reportBox.innerHTML = '<div class="loading">衰减检测中…</div>';
    const res = await apiPost("maintenance/decay");
    const d = res.report || {};
    reportBox.innerHTML = `
      <div class="card" style="margin-top:12px">
        <div class="meta-item"><div class="k">每日减权结果</div><div class="v">${d.ok ? `处理 ${d.processed} 条，归档判定 ${d.archived} 条（${d.rate_percent}%/天，阈值 ${d.threshold}）` : (d.reason || "未启用")}</div></div>
      </div>`;
    toast("衰减检测完成", "ok");
    refreshHealth();
  });
  $("#bk-run").addEventListener("click", async () => {
    const res = await apiPost("backup");
    if (res.result) toast(`已备份到 ${res.result.filename}`, "ok");
  });
  $("#clear-run").addEventListener("click", () =>
    confirmModal("清空全部记忆", "将删除全部记忆、时间线、向量与日志（先自动备份）。请输入确认词「清空」确认。", async () => {
      toast("该操作需在控制台确认（见日志）", "err");
    })
  );
}

/* ================================================================== 设置 */

async function renderSettings() {
  load();
  await loadSettings();
  const schema = state.settingsSchema;
  const values = state.settingsValues;
  const typeLabels = { bool: "开关", int: "整数", float: "小数", string: "文本" };
  $("#view").innerHTML = `
    <div style="background:rgba(22,163,74,0.1);border:1px solid rgba(22,163,74,0.45);color:#16a34a;font-weight:700;font-size:14px;border-radius:10px;padding:12px 16px;margin-bottom:16px">设置修改后<b>自动保存</b>（与陪伴插件一致）；想整体还原可直接点模块的「恢复默认」。</div>
    ${Object.keys(schema)
    .map(
      (module) => `
      <div class="settings-module" data-module="${esc(module)}">
        <div class="settings-head">
          <div>
            <div class="title">${esc(schema[module].description || module)}</div>
            <div class="desc">${esc(schema[module].hint || "")}</div>
          </div>
          <span class="chev">▼</span>
        </div>
        <div class="settings-body">
          ${Object.entries(schema[module].items || {})
            .map(([key, item]) => {
              const value = (values[module] || {})[key];
              return settingsControl(module, key, item, value);
            })
            .join("")}
          <div class="settings-actions">
            <button class="btn" data-act="reset" data-module="${esc(module)}">恢复默认</button>
          </div>
        </div>
      </div>`
    )
    .join("")
    || '<div class="empty">未找到配置</div>'}`;

  document.querySelectorAll(".settings-head").forEach((head) =>
    head.addEventListener("click", () => {
      head.classList.toggle("open");
      head.nextElementSibling.classList.toggle("open");
    })
  );
  document.querySelectorAll(".toggle[data-key]").forEach((t) =>
    t.addEventListener("click", () => {
      t.classList.toggle("on");
      // dataset.key 是 "module.key" 点号形式，输入框 id 为下划线形式
      const input = document.getElementById(`set-${t.dataset.key.replace(/\./g, "_")}`);
      const on = t.classList.contains("on");
      if (input) input.value = on ? "true" : "false";
      // 自动保存（0.78+）：切换即保存
      const [module, key] = t.dataset.key.split(".");
      saveSettingsKey(module, key, on);
    })
  );
  document.querySelectorAll("[data-skey]").forEach((ctl) =>
    ctl.addEventListener("change", () => {
      const [module, key] = ctl.dataset.skey.split(".");
      saveSettingsKey(module, key, ctl.value ?? "");
    })
  );
  document.querySelectorAll('[data-act="reset"]').forEach((btn) =>
    btn.addEventListener("click", async () => {
      await apiPost("config/module/reset", { module: btn.dataset.module });
      toast("已恢复默认", "ok");
      renderSettings();
    })
  );
}

function settingsControl(module, key, item, value) {
  const dotted = `${module}.${key}`;
  const id = `set-${dotted.replace(/\./g, "_")}`;
  const isSpecial = item._special === "select_provider";
  let options = item.options || [];
  let ctl = "";
  if (item.type === "bool") {
    const on = value === true || value === "true" || value === "1" || value === "开";
    ctl = `
      <div class="toggle ${on ? "on" : ""}" data-key="${esc(dotted)}"></div>
      <input type="hidden" id="${id}" value="${on ? "true" : "false"}" />`;
  } else if (isSpecial && item.type === "string") {
    let providerList = state.providerOptions;
    if (dotted.includes("embedding")) providerList = state.embeddingOptions;
    if (dotted.includes("rerank")) providerList = state.rerankOptions;
    const emptyLabel = dotted.includes("media_describe")
      ? "跟随默认（AstrBot 图片理解模型）"
      : "跟随默认";
    const nonEmpty = (providerList || []).filter((opt) => opt.id);
    ctl = `<select id="${id}" data-skey="${esc(dotted)}">
      <option value="" ${!String(value) ? "selected" : ""}>${emptyLabel}</option>
      ${nonEmpty.map((opt) => `<option value="${esc(opt.id)}" ${String(value) === opt.id ? "selected" : ""}>${esc(opt.label)}</option>`).join("")}
    </select>`;
  } else if (options && options.length) {
    ctl = `<select id="${id}" data-skey="${esc(dotted)}">
      ${options.map((opt) => `<option value="${esc(opt)}" ${String(value) === String(opt) ? "selected" : ""}>${esc(opt)}</option>`).join("")}
    </select>`;
  } else if (item.type === "int") {
    ctl = `<input id="${id}" type="number" step="1" data-skey="${esc(dotted)}" value="${esc(value ?? item.default ?? 0)}" />`;
  } else if (item.type === "float") {
    ctl = `<input id="${id}" type="number" step="0.05" data-skey="${esc(dotted)}" value="${esc(value ?? item.default ?? 0)}" />`;
  } else {
    ctl = `<input id="${id}" data-skey="${esc(dotted)}" value="${esc(value ?? item.default ?? "")}" />`;
  }
  return `
    <div class="settings-item">
      <div>
        <div class="label">${esc(item.description || key)} <span class="text-3 mono" style="font-size:11px;font-weight:400">${esc(key)}</span></div>
        <div class="hint">${esc(item.hint || "")}</div>
      </div>
      <div class="ctl">${ctl}</div>
    </div>`;
}

async function saveSettingsKey(module, key, raw) {
  // 自动保存（0.78 起与陪伴插件一致）：单键保存 + 刷新配置快照（不重渲染，保留折叠状态）
  const item = ((state.settingsSchema[module] || {}).items || {})[key] || {};
  let value = raw;
  if (item.type === "bool") value = raw === true || raw === "true" || raw === "1";
  else if (item.type === "int") value = parseInt(raw, 10) || 0;
  else if (item.type === "float") value = parseFloat(raw) || 0;
  else value = String(raw ?? "");
  const res = await apiPost("config/module/update", { module, values: { [key]: value } });
  if (res && res.updated) {
    await loadSettings(true);
    toast(res.message || "已保存", "ok");
    await refreshHealth();
  } else {
    toast((res && res.message) || "保存失败", "err");
  }
}

/* ================================================================== boot */

(async () => {
  await boot();
})();
