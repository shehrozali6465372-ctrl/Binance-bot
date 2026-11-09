import { createHash } from "node:crypto";

export const ANNOUNCEMENT_SOURCE_URL = "https://www.binance.com/en/support/announcement";
export const ANNOUNCEMENT_TOPIC = "com_announcement_en";

function parseJson(value, label) {
  if (typeof value !== "string") return value;
  try {
    return JSON.parse(value);
  } catch {
    throw new Error(label + " is not valid JSON");
  }
}

function canonicalJson(value) {
  return JSON.stringify(value, (_key, item) => {
    if (typeof item === "bigint") return item.toString();
    if (item && typeof item === "object" && !Array.isArray(item)) {
      return Object.fromEntries(Object.entries(item).sort(([a], [b]) => a.localeCompare(b)));
    }
    return item;
  });
}

function sha256(value) {
  return createHash("sha256").update(value, "utf8").digest("hex");
}

function safeText(value, field, maxLength, required = false) {
  if (value == null && !required) return "";
  if (typeof value !== "string") throw new Error(field + " must be a string");
  const normalized = value.normalize("NFC").trim();
  if (required && !normalized) throw new Error(field + " is required");
  if (normalized.length > maxLength) throw new Error(field + " exceeds maximum length");
  return normalized;
}

function normalizeCatalogId(value) {
  if ((typeof value !== "number" && typeof value !== "string" && typeof value !== "bigint") || String(value).trim() === "") {
    throw new Error("catalogId is required");
  }
  const normalized = String(value).trim();
  if (!/^[0-9]+$/.test(normalized)) throw new Error("catalogId must be numeric");
  return normalized;
}

function classifyEvent(catalogName, title) {
  const value = (catalogName + " " + title).toLowerCase();
  if (/delist|remove.*trading/.test(value)) return "delisting";
  if (/new listing|list.*token|launchpool|launchpad/.test(value)) return "listing";
  if (/suspend|resume.*trading/.test(value)) return "suspension";
  if (/maintenance|wallet.*upgrade/.test(value)) return "maintenance";
  if (/network upgrade|hard fork|upgrade/.test(value)) return "upgrade";
  if (/security|incident|vulnerability/.test(value)) return "security_incident";
  if (/integrat/.test(value)) return "integration";
  if (/launch|release/.test(value)) return "launch";
  return "other";
}

/**
 * Accepts the documented CMS WebSocket envelope or its decoded announcement payload.
 * No article permalink or unique announcement ID is invented: the official push payload
 * does not document either field.
 */
export function normalizeAnnouncementMessage(input, observedAt = new Date().toISOString()) {
  const envelope = parseJson(input, "WebSocket message");
  if (!envelope || typeof envelope !== "object" || Array.isArray(envelope)) {
    throw new Error("WebSocket message must be an object");
  }

  let payload = envelope;
  if (Object.hasOwn(envelope, "type") || Object.hasOwn(envelope, "topic") || Object.hasOwn(envelope, "data")) {
    if (envelope.type !== "DATA") throw new Error("unsupported CMS message type");
    if (envelope.topic !== ANNOUNCEMENT_TOPIC) throw new Error("unexpected CMS topic");
    payload = parseJson(envelope.data, "CMS data payload");
  }

  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    throw new Error("announcement payload must be an object");
  }

  const catalogId = normalizeCatalogId(payload.catalogId);
  const catalogName = safeText(payload.catalogName ?? "Uncategorized", "catalogName", 200);
  const title = safeText(payload.title, "title", 1000, true);
  const body = safeText(payload.body ?? "", "body", 100000);
  const disclaimer = safeText(payload.disclaimer ?? "", "disclaimer", 10000);

  const publishDate = typeof payload.publishDate === "bigint" ? Number(payload.publishDate) : payload.publishDate;
  if (typeof publishDate !== "number" || !Number.isSafeInteger(publishDate) || publishDate <= 0) {
    throw new Error("publishDate must be a positive safe integer in milliseconds");
  }

  const publishedAtDate = new Date(publishDate);
  if (!Number.isFinite(publishedAtDate.getTime())) throw new Error("publishDate is outside supported date range");
  const observedDate = new Date(observedAt);
  if (!Number.isFinite(observedDate.getTime())) throw new Error("observedAt must be a valid timestamp");
  if (publishedAtDate.getTime() > observedDate.getTime() + 5 * 60 * 1000) {
    throw new Error("publishDate is more than five minutes in the future");
  }

  const normalizedPayload = {
    catalogId,
    catalogName,
    publishDate,
    title,
    body,
    disclaimer,
  };
  const contentHash = sha256(canonicalJson(normalizedPayload));
  // The push schema exposes no stable article ID. This fingerprint identifies an exact
  // observed payload; it is not claimed to identify an article across edited revisions.
  const sourceId = sha256([catalogId, publishDate, title].join("\u001f"));

  return Object.freeze({
    sourceId,
    contentHash,
    sourceUrl: ANNOUNCEMENT_SOURCE_URL,
    publisher: "Binance",
    topic: ANNOUNCEMENT_TOPIC,
    eventType: classifyEvent(catalogName, title),
    catalogId,
    catalogName,
    title,
    body,
    disclaimer,
    publishedAt: publishedAtDate.toISOString(),
    observedAt: observedDate.toISOString(),
    rawPayload: normalizedPayload,
  });
}
