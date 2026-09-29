import { research, summarize, sortRows, formatCount } from "./lib.js";

const $ = (id) => document.getElementById(id);
const STORE = "youtube_research.settings";
const FIELDS = ["key", "query", "days", "maxSeconds", "order", "perChannelLimit", "targetCount", "threshold"];

const state = { rows: [], sortKey: "multiplier", sortDir: "desc" };

const COLUMNS = [
  { key: "thumbnail", label: "", sortable: false, left: true },
  { key: "title", label: "タイトル", left: true },
  { key: "channelTitle", label: "チャンネル", left: true },
  { key: "subscribers", label: "登録者" },
  { key: "views", label: "再生回数" },
  { key: "likes", label: "いいね" },
  { key: "likeRatio", label: "いいね/再生" },
  { key: "publishedAt", label: "投稿日" },
  { key: "multiplier", label: "再生倍率" },
];

function loadSettings() {
  try {
    const saved = JSON.parse(localStorage.getItem(STORE) || "{}");
    for (const f of FIELDS) if (saved[f] !== undefined) $(f).value = saved[f];
  } catch {}
}

function saveSettings() {
  try {
    localStorage.setItem(STORE, JSON.stringify(Object.fromEntries(FIELDS.map((f) => [f, $(f).value]))));
  } catch {}
}

function el(tag, props = {}, ...children) {
  const node = document.createElement(tag);
  Object.assign(node, props);
  for (const c of children) node.append(c);
  return node;
}

function link(href, text) {
  return el("a", { href, textContent: text, target: "_blank", rel: "noopener noreferrer" });
}

function renderTiles(rows) {
  const threshold = Number($("threshold").value) || 0;
  const s = summarize(rows, threshold);
  const pct = (v) => (v === null ? "-" : `${(v * 100).toFixed(1)}%`);
  const items = [
    ["該当動画数", s.count.toLocaleString()],
    ["直近の総再生回数", formatCount(s.totalViews)],
    ["平均いいね/再生比率", pct(s.avgLikeRatio)],
    ["再生倍率の平均", s.avgMultiplier === null ? "-" : `${s.avgMultiplier.toFixed(1)}倍`],
    [`伸びているch数(${threshold}倍以上)`, String(s.growingChannels)],
  ];
  $("tiles").replaceChildren(
    ...items.map(([k, v]) => el("div", { className: "tile" }, el("div", { className: "v", textContent: v }), el("div", { className: "k", textContent: k }))),
  );
}

function renderTable() {
  const threshold = Number($("threshold").value) || 0;
  let rows = state.rows;
  if ($("onlyHot").checked) rows = rows.filter((r) => r.multiplier !== null && r.multiplier >= threshold);
  rows = sortRows(rows, state.sortKey, state.sortDir);

  const sel = `${state.sortKey}:${state.sortDir}`;
  if ([...$("sortSel").options].some((o) => o.value === sel)) $("sortSel").value = sel;

  const arrow = (k) => (state.sortKey === k ? (state.sortDir === "asc" ? " ▲" : " ▼") : "");
  $("table").tHead.replaceChildren(
    el(
      "tr",
      {},
      ...COLUMNS.map((c) => {
        const th = el("th", { textContent: c.label + (c.label ? arrow(c.key) : ""), className: c.left ? "left" : "" });
        if (c.sortable !== false) {
          th.addEventListener("click", () => {
            state.sortDir = state.sortKey === c.key && state.sortDir === "desc" ? "asc" : "desc";
            state.sortKey = c.key;
            renderTable();
          });
        }
        return th;
      }),
    ),
  );

  $("table").tBodies[0].replaceChildren(
    ...rows.map((r) => {
      const videoUrl = `https://www.youtube.com/watch?v=${encodeURIComponent(r.id)}`;
      const channelUrl = `https://www.youtube.com/channel/${encodeURIComponent(r.channelId)}`;
      const hot = r.multiplier !== null && r.multiplier >= threshold;
      const img = el("img", { src: r.thumbnail, alt: "", loading: "lazy" });
      const cell = (label, props, ...children) => {
        const td = el("td", props, ...children);
        td.setAttribute("data-label", label);
        return td;
      };
      return el(
        "tr",
        {},
        cell("", { className: "left thumb" }, r.thumbnail ? wrap(videoUrl, img) : ""),
        cell("", { className: "left title" }, link(videoUrl, r.title)),
        cell("", { className: "left channel" }, link(channelUrl, r.channelTitle)),
        cell("登録者", { textContent: formatCount(r.subscribers) }),
        cell("再生回数", { textContent: r.views.toLocaleString() }),
        cell("いいね", { textContent: r.likes === null ? "非公開" : r.likes.toLocaleString() }),
        cell("いいね/再生", { textContent: r.likeRatio === null ? "-" : `${(r.likeRatio * 100).toFixed(2)}%` }),
        cell("投稿日", { textContent: r.publishedAt.slice(0, 10) }),
        cell("再生倍率", { className: hot ? "hot" : "", textContent: r.multiplier === null ? "-" : `${r.multiplier.toFixed(1)}倍` }),
      );
    }),
  );
}

function wrap(href, child) {
  const a = link(href, "");
  a.replaceChildren(child);
  return a;
}

function friendlyError(e) {
  if (e.reason === "quotaExceeded") return "API の1日の利用枠を使い切りました。太平洋時間の0時(日本時間 16〜17時頃)にリセットされます。";
  if (e.reason === "keyInvalid" || /API key not valid/i.test(e.message)) return "API キーが正しくありません。キーを確認してください。";
  if (e.reason === "accessNotConfigured" || /has not been used|is disabled/i.test(e.message))
    return "このキーのプロジェクトで YouTube Data API v3 が有効になっていません。Google Cloud で有効化してください。";
  return `取得に失敗しました: ${e.message}`;
}

$("form").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  saveSettings();
  $("error").textContent = "";
  $("go").disabled = true;
  $("bar").hidden = false;
  try {
    const { rows, quotaUnits } = await research(
      {
        key: $("key").value.trim(),
        query: $("query").value.trim(),
        days: Number($("days").value),
        maxSeconds: Number($("maxSeconds").value),
        order: $("order").value,
        perChannelLimit: Math.max(1, Number($("perChannelLimit").value) || 20),
        targetCount: Number($("targetCount").value),
      },
      fetch.bind(window),
      ({ ratio, message }) => {
        $("barFill").style.width = `${Math.round(ratio * 100)}%`;
        $("status").textContent = message;
      },
    );
    state.rows = rows;
    $("results").hidden = false;
    $("status").textContent = `${rows.length}本を取得しました(API 利用枠 約${quotaUnits}消費)`;
    renderTiles(rows);
    renderTable();
  } catch (e) {
    $("error").textContent = friendlyError(e);
    $("status").textContent = "";
  } finally {
    $("go").disabled = false;
    $("bar").hidden = true;
  }
});

$("threshold").addEventListener("input", () => {
  saveSettings();
  renderTiles(state.rows);
  renderTable();
});
$("onlyHot").addEventListener("change", renderTable);
$("sortSel").addEventListener("change", () => {
  const [key, dir] = $("sortSel").value.split(":");
  state.sortKey = key;
  state.sortDir = dir;
  renderTable();
});

loadSettings();
