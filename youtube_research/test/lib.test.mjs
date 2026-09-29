import test from "node:test";
import assert from "node:assert/strict";
import { parseDuration, research, summarize, sortRows, toRow, formatCount } from "../lib.js";

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
