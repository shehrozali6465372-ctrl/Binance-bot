import test from "node:test";
import assert from "node:assert/strict";
import {
  ANNOUNCEMENT_TOPIC,
  ANNOUNCEMENT_SOURCE_URL,
  normalizeAnnouncementMessage,
} from "../src/normalize.js";

const observedAt = "2026-11-10T00:00:00.000Z";
const payload = {
  catalogId: 48,
  catalogName: "New Cryptocurrency Listing",
  publishDate: Date.parse("2026-11-09T23:00:00.000Z"),
  title: "Binance Will List Example (EXM)",
  body: "Official announcement body",
  disclaimer: "Risk notice",
};

test("normalizes documented DATA envelope with JSON-string payload", () => {
  const event = normalizeAnnouncementMessage({
    type: "DATA",
    topic: ANNOUNCEMENT_TOPIC,
    data: JSON.stringify(payload),
  }, observedAt);

  assert.equal(event.publisher, "Binance");
  assert.equal(event.topic, ANNOUNCEMENT_TOPIC);
  assert.equal(event.sourceUrl, ANNOUNCEMENT_SOURCE_URL);
  assert.equal(event.catalogId, "48");
  assert.equal(event.eventType, "listing");
  assert.equal(event.title, payload.title);
  assert.equal(event.publishedAt, "2026-11-09T23:00:00.000Z");
  assert.match(event.sourceId, /^[a-f0-9]{64}$/);
  assert.match(event.contentHash, /^[a-f0-9]{64}$/);
});

test("normalizes decoded SDK payload", () => {
  const event = normalizeAnnouncementMessage(payload, observedAt);
  assert.equal(event.catalogName, payload.catalogName);
  assert.equal(event.body, payload.body);
});

test("exact duplicate payload has deterministic content fingerprint", () => {
  const first = normalizeAnnouncementMessage(payload, observedAt);
  const second = normalizeAnnouncementMessage(payload, observedAt);
  assert.equal(first.contentHash, second.contentHash);
});

test("changed body produces a distinct content fingerprint", () => {
  const first = normalizeAnnouncementMessage(payload, observedAt);
  const second = normalizeAnnouncementMessage({ ...payload, body: "Edited body" }, observedAt);
  assert.notEqual(first.contentHash, second.contentHash);
});

test("rejects non-announcement topic", () => {
  assert.throws(() => normalizeAnnouncementMessage({
    type: "DATA", topic: "another_topic", data: JSON.stringify(payload),
  }, observedAt), /unexpected CMS topic/);
});

test("rejects malformed inner JSON", () => {
  assert.throws(() => normalizeAnnouncementMessage({
    type: "DATA", topic: ANNOUNCEMENT_TOPIC, data: "{bad",
  }, observedAt), /not valid JSON/);
});

test("rejects missing title and invalid publish timestamp", () => {
  assert.throws(() => normalizeAnnouncementMessage({ ...payload, title: " " }, observedAt), /title is required/);
  assert.throws(() => normalizeAnnouncementMessage({ ...payload, publishDate: "yesterday" }, observedAt), /publishDate/);
});

test("rejects future timestamps beyond tolerated clock skew", () => {
  const future = Date.parse("2026-11-10T00:10:00.000Z");
  assert.throws(() => normalizeAnnouncementMessage({ ...payload, publishDate: future }, observedAt), /more than five minutes/);
});

test("rejects unsafe catalog identifiers and oversized text", () => {
  assert.throws(() => normalizeAnnouncementMessage({ ...payload, catalogId: "48;DROP TABLE" }, observedAt), /catalogId/);
  assert.throws(() => normalizeAnnouncementMessage({ ...payload, title: "x".repeat(1001) }, observedAt), /maximum length/);
});
