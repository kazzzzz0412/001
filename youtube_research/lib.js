export const SEARCH_PAGE_SIZE = 50;
export const MAX_SEARCH_PAGES = 10;
const API = "https://www.googleapis.com/youtube/v3";

export function parseDuration(iso) {
  const m = /^P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?$/.exec(iso || "");
  if (!m) return NaN;
  const [, d, h, mi, s] = m.map((v) => (v === undefined ? 0 : Number(v)));
  return d * 86400 + h * 3600 + mi * 60 + s;
}

export function buildUrl(path, params) {
  const url = new URL(`${API}/${path}`);
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== "") url.searchParams.set(k, String(v));
  }
  return url.toString();
}

export function publishedAfter(days, now = new Date()) {
  return new Date(now.getTime() - days * 86400000).toISOString();
}

export async function apiGet(fetchFn, path, params, key) {
  const res = await fetchFn(buildUrl(path, { ...params, key }));
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    const err = body.error || {};
    const reason = err.errors && err.errors[0] && err.errors[0].reason;
    const e = new Error(err.message || `HTTP ${res.status}`);
    e.reason = reason;
    e.status = res.status;
    throw e;
  }
  return body;
}

export function chunk(arr, size) {
  const out = [];
  for (let i = 0; i < arr.length; i += size) out.push(arr.slice(i, i + size));
  return out;
}

export async function research(opts, fetchFn = fetch, onProgress = () => {}) {
  const { key, query, days, maxSeconds, perChannelLimit, targetCount, order } = opts;
  const after = publishedAfter(days);
  const picked = [];
  const perChannel = new Map();
  const seen = new Set();
  let pageToken;
  let searchCalls = 0;

  for (let page = 0; page < MAX_SEARCH_PAGES && picked.length < targetCount; page++) {
    onProgress({ ratio: Math.min(picked.length / targetCount, 0.9), message: `動画を検索中… ${picked.length}/${targetCount}` });
    const search = await apiGet(
      fetchFn,
      "search",
      {
        part: "snippet",
        type: "video",
        q: query,
        order,
        publishedAfter: after,
        videoDuration: "short",
        maxResults: SEARCH_PAGE_SIZE,
        pageToken,
      },
      key,
    );
    searchCalls++;
    const ids = (search.items || []).map((it) => it.id && it.id.videoId).filter((id) => id && !seen.has(id));
    ids.forEach((id) => seen.add(id));
    if (ids.length) {
      const details = await apiGet(
        fetchFn,
        "videos",
        { part: "snippet,contentDetails,statistics", id: ids.join(","), maxResults: SEARCH_PAGE_SIZE },
        key,
      );
      const byId = new Map((details.items || []).map((v) => [v.id, v]));
      for (const id of ids) {
        const v = byId.get(id);
        if (!v || picked.length >= targetCount) continue;
        if (!(parseDuration(v.contentDetails.duration) <= maxSeconds)) continue;
        const ch = v.snippet.channelId;
        if ((perChannel.get(ch) || 0) >= perChannelLimit) continue;
        perChannel.set(ch, (perChannel.get(ch) || 0) + 1);
        picked.push(v);
      }
    }
    pageToken = search.nextPageToken;
    if (!pageToken) break;
  }

  onProgress({ ratio: 0.92, message: "チャンネル情報を取得中…" });
  const channelIds = [...new Set(picked.map((v) => v.snippet.channelId))];
  const channels = new Map();
  const chunks = await Promise.all(
    chunk(channelIds, 50).map((ids) =>
      apiGet(fetchFn, "channels", { part: "snippet,statistics", id: ids.join(","), maxResults: 50 }, key),
    ),
  );
  for (const c of chunks) for (const ch of c.items || []) channels.set(ch.id, ch);

  onProgress({ ratio: 1, message: "完了" });
  return {
    rows: picked.map((v) => toRow(v, channels.get(v.snippet.channelId))),
    quotaUnits: searchCalls * 100 + searchCalls + chunk(channelIds, 50).length,
  };
}

export function toRow(video, channel) {
  const stats = video.statistics || {};
  const cs = (channel && channel.statistics) || {};
  const views = Number(stats.viewCount || 0);
  const likes = stats.likeCount === undefined ? null : Number(stats.likeCount);
  const subscribers = !channel || cs.hiddenSubscriberCount || cs.subscriberCount === undefined ? null : Number(cs.subscriberCount);
  const thumbs = video.snippet.thumbnails || {};
  return {
    id: video.id,
    title: video.snippet.title,
    channelId: video.snippet.channelId,
    channelTitle: video.snippet.channelTitle,
    thumbnail: (thumbs.medium || thumbs.default || {}).url || "",
    publishedAt: video.snippet.publishedAt,
    views,
    likes,
    subscribers,
    likeRatio: likes !== null && views > 0 ? likes / views : null,
    multiplier: subscribers ? views / subscribers : null,
  };
}

const mean = (xs) => (xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : null);

export function summarize(rows, threshold) {
  const growing = new Set(rows.filter((r) => r.multiplier !== null && r.multiplier >= threshold).map((r) => r.channelId));
  return {
    count: rows.length,
    totalViews: rows.reduce((a, r) => a + r.views, 0),
    avgLikeRatio: mean(rows.map((r) => r.likeRatio).filter((v) => v !== null)),
    avgMultiplier: mean(rows.map((r) => r.multiplier).filter((v) => v !== null)),
    growingChannels: growing.size,
  };
}

export function sortRows(rows, key, dir) {
  const sign = dir === "asc" ? 1 : -1;
  return [...rows].sort((a, b) => {
    const x = a[key];
    const y = b[key];
    if (x === null || x === undefined) return y === null || y === undefined ? 0 : 1;
    if (y === null || y === undefined) return -1;
    return (x < y ? -1 : x > y ? 1 : 0) * sign;
  });
}

export function formatCount(n) {
  if (n === null || n === undefined) return "非公開";
  if (n >= 1e8) return `${(n / 1e8).toFixed(1)}億`;
  if (n >= 1e4) return `${(n / 1e4).toFixed(n >= 1e6 ? 0 : 1)}万`;
  return String(n);
}
