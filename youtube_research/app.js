import { research, summarize, sortRows, formatCount, fetchChannelDetail, summarizeChannel, bucketViews, niceTicks } from "./lib.js";

const $ = (id) => document.getElementById(id);
const STORE = "youtube_research.settings";
const FIELDS = ["key", "query", "days", "maxSeconds", "order", "perChannelLimit", "targetCount", "threshold"];

const state = { rows: [], sortKey: "multiplier", sortDir: "desc", opts: null };

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
        cell("", { className: "left channel" }, channelButton(r)),
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

function channelButton(r) {
  const b = el("button", { type: "button", className: "linkish", textContent: r.channelTitle });
  b.addEventListener("click", () => openChannel(r));
  return b;
}

const SVG_NS = "http://www.w3.org/2000/svg";

function svgEl(tag, attrs = {}, style = {}) {
  const n = document.createElementNS(SVG_NS, tag);
  for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, String(v));
  Object.assign(n.style, style);
  return n;
}

function svgText(x, y, anchor, text) {
  const t = svgEl("text", { x, y, "text-anchor": anchor, "font-size": 11 }, { fill: "var(--muted)" });
  t.textContent = text;
  return t;
}

function renderChart(buckets) {
  const W = Math.max(300, $("chart").clientWidth || 640);
  const narrow = W < 500;
  const H = narrow ? 220 : 240, L = narrow ? 46 : 52, R = 10, T = 12, B = 30;
  const ticks = niceTicks(Math.max(...buckets.map((b) => b.views), 0));
  const top = ticks[ticks.length - 1];
  const y = (v) => T + (H - T - B) * (1 - v / top);
  const svg = svgEl("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": "投稿日別の再生数" });
  for (const t of ticks) {
    svg.append(svgEl("line", { x1: L, x2: W - R, y1: y(t), y2: y(t) }, { stroke: "var(--line)", strokeWidth: 1 }));
    svg.append(svgText(L - 6, y(t) + 4, "end", formatCount(t)));
  }
  const bw = (W - L - R) / buckets.length;
  const every = Math.ceil(buckets.length / (narrow ? 5 : 8));
  buckets.forEach((b, i) => {
    if (b.views > 0) {
      const rect = svgEl(
        "rect",
        { x: L + i * bw + bw * 0.12, y: y(b.views), width: Math.max(bw * 0.76, 1), height: (H - T - B) * (b.views / top) },
        { fill: "var(--accent)" },
      );
      const title = svgEl("title");
      title.textContent = `${b.label}: ${b.views.toLocaleString()}回(${b.count}本)`;
      rect.append(title);
      svg.append(rect);
    }
    if ((buckets.length - 1 - i) % every === 0) svg.append(svgText(L + i * bw + bw / 2, H - 10, "middle", b.label));
  });
  $("chart").replaceChildren(svg);
}

let detailToken = 0;
let listScrollY = 0;

function showList() {
  detailToken++;
  $("detail").hidden = true;
  $("form").hidden = false;
  $("results").hidden = false;
  window.scrollTo(0, listScrollY);
}

async function openChannel(row) {
  if (!state.opts) return;
  const { key, days, maxSeconds } = state.opts;
  const token = ++detailToken;
  listScrollY = window.scrollY;
  $("form").hidden = true;
  $("results").hidden = true;
  $("detail").hidden = false;
  $("chTitle").textContent = row.channelTitle;
  $("ytLink").href = `https://www.youtube.com/channel/${encodeURIComponent(row.channelId)}`;
  $("chError").textContent = "";
  $("chStatus").textContent = "取得中…";
  $("chTiles").replaceChildren();
  $("chartCard").hidden = true;
  $("topCard").hidden = true;
  window.scrollTo(0, 0);
  try {
    const { channel, rows, quotaUnits } = await fetchChannelDetail(
      { key, channelId: row.channelId, days, maxSeconds },
      fetch.bind(window),
      ({ message }) => {
        if (token === detailToken) $("chStatus").textContent = message;
      },
    );
    if (token !== detailToken) return;
    const s = summarizeChannel(rows, channel.subscribers, days);
    const tiles = [
      ["登録者数", formatCount(channel.subscribers)],
      [`直近${days}日の投稿本数`, `${s.count}本`],
      ["直近の平均再生", s.avgViews === null ? "-" : formatCount(Math.round(s.avgViews))],
      ["直近の再生倍率", s.multiplier === null ? "-" : `${s.multiplier.toFixed(1)}倍`],
      ["投稿頻度", `週${s.perWeek.toFixed(1)}本`],
      ["平均いいね/再生", s.avgLikeRatio === null ? "-" : `${(s.avgLikeRatio * 100).toFixed(2)}%`],
    ];
    $("chTiles").replaceChildren(
      ...tiles.map(([k, v]) => el("div", { className: "tile" }, el("div", { className: "v", textContent: v }), el("div", { className: "k", textContent: k }))),
    );
    $("chStatus").textContent = `${s.count}本を集計しました(API 利用枠 約${quotaUnits}消費)`;
    if (s.count === 0) {
      $("chStatus").textContent = "この期間に、条件に合う動画がありませんでした。期間や動画の長さを変えて、もう一度取得してください。";
      return;
    }
    $("chartNote").textContent = `${days > 90 ? "週" : "日"}ごとに、その期間に投稿された動画の現在の再生数を合計しています。YouTube の API では、本人以外は日ごとの再生数の推移を取得できません。`;
    $("chartCard").hidden = false;
    renderChart(bucketViews(rows, days));
    $("topCard").hidden = false;
    $("topList").replaceChildren(
      ...sortRows(rows, "views", "desc")
        .slice(0, 10)
        .map((r) =>
          el(
            "li",
            {},
            link(`https://www.youtube.com/watch?v=${encodeURIComponent(r.id)}`, r.title),
            el("span", { className: "meta", textContent: `${r.views.toLocaleString()}回 ・ ${r.publishedAt.slice(0, 10)}` }),
          ),
        ),
    );
  } catch (e) {
    if (token !== detailToken) return;
    $("chStatus").textContent = "";
    $("chError").textContent = friendlyError(e);
  }
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
    state.opts = { key: $("key").value.trim(), days: Number($("days").value), maxSeconds: Number($("maxSeconds").value) };
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
$("back").addEventListener("click", showList);
$("sortSel").addEventListener("change", () => {
  const [key, dir] = $("sortSel").value.split(":");
  state.sortKey = key;
  state.sortDir = dir;
  renderTable();
});

loadSettings();
try {
  navigator.storage?.persist?.().catch(() => {});
} catch {}
