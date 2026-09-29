import test from "node:test";
import assert from "node:assert/strict";
import {
  parseDuration, research, summarize, sortRows, toRow, formatCount,
  fetchChannelDetail, summarizeChannel, bucketViews, niceTicks,
} from "../lib.js";

test("parseDuration", () => {
  assert.equal(parseDuration("PT45S"), 45);
  assert.equal(parseDuration("PT1M5S"), 65);
  assert.equal(parseDuration("PT1H2M3S"), 3723);
  assert.equal(parseDuration("PT3M"), 180);
  assert.ok(Number.isNaN(parseDuration("bogus")));
});

function video(i, channel, duration = "PT30S", extra = {}) {
  return {
    id: `v${i}`,
    snippet: { title: `t${i}`, channelId: channel, channelTitle: channel, publishedAt: "2026-09-01T00:00:00Z", thumbnails: {} },
    contentDetails: { duration },
    statistics: { viewCount: String(1000 * i), likeCount: String(10 * i) },
    ...extra,
  };
}

function fakeFetch(videos, channels, { pageSize = 50 } = {}) {
  const calls = [];
  const fn = async (url) => {
    const u = new URL(url);
    const path = u.pathname.split("/").pop();
    calls.push(path);
    const json = (body, status = 200) => ({ ok: status < 400, status, json: async () => body });
    if (path === "search") {
      const start = Number(u.searchParams.get("pageToken") || 0);
      const slice = videos.slice(start, start + pageSize);
      const next = start + pageSize < videos.length ? String(start + pageSize) : undefined;
      return json({ items: slice.map((v) => ({ id: { videoId: v.id } })), nextPageToken: next });
    }
    if (path === "videos") {
      const ids = u.searchParams.get("id").split(",");
      return json({ items: videos.filter((v) => ids.includes(v.id)) });
    }
    if (path === "channels") {
      const ids = u.searchParams.get("id").split(",");
      return json({ items: channels.filter((c) => ids.includes(c.id)) });
    }
    throw new Error(`unexpected ${path}`);
  };
  fn.calls = calls;
  return fn;
}

const base = { key: "k", query: "q", days: 30, maxSeconds: 60, perChannelLimit: 20, targetCount: 200, order: "viewCount" };
const ch = (id, subs, hidden = false) => ({ id, statistics: hidden ? { hiddenSubscriberCount: true } : { subscriberCount: String(subs) } });

test("research filters by duration and per-channel cap and computes multiplier", async () => {
  const videos = [video(1, "A"), video(2, "A", "PT2M"), video(3, "A"), video(4, "A"), video(5, "B")];
  const f = fakeFetch(videos, [ch("A", 100), ch("B", 500)]);
  const { rows } = await research({ ...base, perChannelLimit: 2 }, f);
  assert.deepEqual(rows.map((r) => r.id), ["v1", "v3", "v5"]);
  assert.equal(rows[0].multiplier, 1000 / 100);
  assert.equal(rows[2].multiplier, 5000 / 500);
});

test("research stops at targetCount and paginates", async () => {
  const videos = Array.from({ length: 120 }, (_, i) => video(i + 1, `C${i}`));
  const channels = videos.map((v) => ch(v.snippet.channelId, 1000));
  const f = fakeFetch(videos, channels);
  const { rows, quotaUnits } = await research({ ...base, targetCount: 60 }, f);
  assert.equal(rows.length, 60);
  assert.equal(f.calls.filter((c) => c === "search").length, 2);
  assert.equal(quotaUnits, 2 * 100 + 2 + 2);
});

test("hidden subscribers give null multiplier", async () => {
  const f = fakeFetch([video(1, "H")], [ch("H", 0, true)]);
  const { rows } = await research(base, f);
  assert.equal(rows[0].subscribers, null);
  assert.equal(rows[0].multiplier, null);
});

test("API errors surface reason", async () => {
  const f = async () => ({ ok: false, status: 403, json: async () => ({ error: { message: "quota", errors: [{ reason: "quotaExceeded" }] } }) });
  await assert.rejects(research(base, f), (e) => e.reason === "quotaExceeded");
});

test("summarize and sort", () => {
  const rows = [
    toRow(video(1, "A"), ch("A", 100)),
    toRow(video(2, "B"), ch("B", 100000)),
    toRow(video(3, "A", "PT30S", { statistics: { viewCount: "3000" } }), ch("A", 100)),
  ];
  const s = summarize(rows, 10);
  assert.equal(s.count, 3);
  assert.equal(s.totalViews, 6000);
  assert.equal(s.growingChannels, 1);
  assert.ok(Math.abs(s.avgLikeRatio - 0.01) < 1e-9);
  assert.deepEqual(sortRows(rows, "multiplier", "desc").map((r) => r.id), ["v3", "v1", "v2"]);
  assert.deepEqual(sortRows(rows, "likes", "desc").map((r) => r.id), ["v2", "v1", "v3"]);
});

test("formatCount", () => {
  assert.equal(formatCount(null), "非公開");
  assert.equal(formatCount(2070), "2070");
  assert.equal(formatCount(172000), "17.2万");
  assert.equal(formatCount(57790000), "5779万");
});

const NOW = new Date("2026-09-30T12:00:00Z");
const ago = (h) => new Date(NOW.getTime() - h * 3600000).toISOString();

function detailFetch({ playlist, videos, subs = "2070" }) {
  const calls = [];
  const fn = async (url) => {
    const u = new URL(url);
    const path = u.pathname.split("/").pop();
    calls.push(path);
    const json = (body) => ({ ok: true, status: 200, json: async () => body });
    if (path === "channels")
      return json({ items: [{ id: "A", snippet: { title: "チャンネルA" }, statistics: { subscriberCount: subs, videoCount: "44" }, contentDetails: { relatedPlaylists: { uploads: "UUA" } } }] });
    if (path === "playlistItems") {
      const start = Number(u.searchParams.get("pageToken") || 0);
      const slice = playlist.slice(start, start + 2);
      return json({
        items: slice.map((p) => ({ contentDetails: { videoId: p.id, videoPublishedAt: p.at } })),
        nextPageToken: start + 2 < playlist.length ? String(start + 2) : undefined,
      });
    }
    if (path === "videos") {
      const ids = u.searchParams.get("id").split(",");
      return json({ items: videos.filter((v) => ids.includes(v.id)) });
    }
    throw new Error(`unexpected ${path}`);
  };
  fn.calls = calls;
  return fn;
}

const dv = (id, at, views, duration = "PT30S") => ({
  id,
  snippet: { title: id, channelId: "A", channelTitle: "チャンネルA", publishedAt: at, thumbnails: {} },
  contentDetails: { duration },
  statistics: { viewCount: String(views), likeCount: String(views / 100) },
});

test("fetchChannelDetail stops at the period cutoff and filters by duration", async () => {
  const playlist = [
    { id: "n1", at: ago(1) },
    { id: "n2", at: ago(48) },
    { id: "n3", at: ago(24 * 10) },
    { id: "old", at: ago(24 * 40) },
    { id: "older", at: ago(24 * 50) },
  ];
  const videos = [dv("n1", ago(1), 1000), dv("n2", ago(48), 3000, "PT5M"), dv("n3", ago(24 * 10), 2000)];
  const f = detailFetch({ playlist, videos });
  const { channel, rows, quotaUnits } = await fetchChannelDetail({ key: "k", channelId: "A", days: 30, maxSeconds: 60 }, f, () => {}, NOW);
  assert.deepEqual(rows.map((r) => r.id), ["n1", "n3"]);
  assert.equal(channel.subscribers, 2070);
  assert.equal(f.calls.filter((c) => c === "playlistItems").length, 2);
  assert.equal(quotaUnits, 1 + 2 + 1);
});

test("fetchChannelDetail rejects an unknown channel", async () => {
  const f = async () => ({ ok: true, status: 200, json: async () => ({ items: [] }) });
  await assert.rejects(fetchChannelDetail({ key: "k", channelId: "X", days: 30, maxSeconds: 60 }, f, () => {}, NOW), /チャンネルが見つかりません/);
});

test("summarizeChannel", () => {
  const rows = [toRow(dv("a", ago(1), 1000), { statistics: { subscriberCount: "100" } }), toRow(dv("b", ago(2), 3000), { statistics: { subscriberCount: "100" } })];
  const s = summarizeChannel(rows, 100, 30);
  assert.equal(s.count, 2);
  assert.equal(s.avgViews, 2000);
  assert.equal(s.multiplier, 20);
  assert.ok(Math.abs(s.perWeek - 2 / (30 / 7)) < 1e-9);
  assert.ok(Math.abs(s.avgLikeRatio - 0.01) < 1e-9);
  assert.equal(summarizeChannel([], null, 30).multiplier, null);
});

test("bucketViews places videos by age and drops out-of-range ones", () => {
  const rows = [
    toRow(dv("today", ago(6), 500), { statistics: {} }),
    toRow(dv("today2", ago(3), 100), { statistics: {} }),
    toRow(dv("d2", ago(30), 200), { statistics: {} }),
    toRow(dv("far", ago(24 * 31), 999), { statistics: {} }),
  ];
  const b = bucketViews(rows, 30, NOW);
  assert.equal(b.length, 30);
  assert.equal(b[29].views, 600);
  assert.equal(b[29].count, 2);
  assert.equal(b[28].views, 200);
  assert.equal(b.reduce((a, x) => a + x.views, 0), 800);
  assert.equal(b[29].label, "09/30");
  assert.equal(bucketViews([], 365, NOW).length, 53);
});

test("niceTicks", () => {
  assert.deepEqual(niceTicks(100), [0, 25, 50, 75, 100]);
  assert.deepEqual(niceTicks(0), [0, 1]);
  const t = niceTicks(730000);
  assert.ok(t[t.length - 1] >= 730000 && t[0] === 0);
});
