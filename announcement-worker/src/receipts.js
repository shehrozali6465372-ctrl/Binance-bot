import { createHash, createHmac } from "node:crypto";

const RECEIPT_VERSION = 1;
const DOMAIN = Buffer.from("binance-square-w2e:source-ingestion-receipt:v1\0", "utf8");
const AUTHORITY_ID = "binance_announcement_cms";
const TOPIC = "com_announcement_en";
const KEY_ID_PATTERN = /^[A-Za-z0-9._-]{1,128}$/;
const HASH_PATTERN = /^[a-f0-9]{64}$/;
const REQUIRED_ENV = [
  "BINANCE_CMS_RECEIPT_HMAC_KEYRING_JSON",
  "BINANCE_CMS_RECEIPT_ACTIVE_KEY_ID",
  "BINANCE_CMS_RECEIPT_TRUSTED_KEY_IDS",
];

function assertJsonValue(value) {
  if (value === null || typeof value === "string" || typeof value === "boolean") return;
  if (typeof value === "number" && Number.isFinite(value) && Number.isSafeInteger(value)) return;
  if (Array.isArray(value)) {
    for (const item of value) assertJsonValue(item);
    return;
  }
  if (value && Object.getPrototypeOf(value) === Object.prototype) {
    for (const [key, item] of Object.entries(value)) {
      if (typeof key !== "string") throw new TypeError("receipt payload object keys must be strings");
      assertJsonValue(item);
    }
    return;
  }
  throw new TypeError("receipt payload contains a non-JSON value");
}

function canonicalJson(value) {
  if (!value || typeof value !== "object" || Array.isArray(value) || Object.getPrototypeOf(value) !== Object.prototype) {
    throw new TypeError("receipt payload must be a non-empty object");
  }
  assertJsonValue(value);
  const sortRecursively = (item) => {
    if (Array.isArray(item)) return item.map(sortRecursively);
    if (item && typeof item === "object") {
      return Object.fromEntries(Object.keys(item).sort().map((key) => [key, sortRecursively(item[key])]));
    }
    return item;
  };
  // Python's shared receipt contract uses json.dumps(sort_keys=True, ensure_ascii=True).
  return JSON.stringify(sortRecursively(value)).replace(/[\u007f-\uffff]/g, (character) =>
    `\\u${character.charCodeAt(0).toString(16).padStart(4, "0")}`,
  );
}

function signingBytes(version, authorityId, keyId, payloadHash) {
  const envelope = { authority_id: authorityId, key_id: keyId, payload_hash: payloadHash, version };
  return Buffer.concat([DOMAIN, Buffer.from(canonicalJson(envelope), "utf8")]);
}

export function loadReceiptSigningConfig(env = process.env) {
  const values = REQUIRED_ENV.map((name) => String(env[name] ?? "").trim());
  if (values.every((value) => !value)) return null;
  if (values.some((value) => !value)) {
    throw new Error("CMS receipt signing configuration is incomplete");
  }

  let rawKeyring;
  try { rawKeyring = JSON.parse(values[0]); }
  catch { throw new Error("CMS receipt keyring configuration is invalid"); }
  if (!rawKeyring || typeof rawKeyring !== "object" || Array.isArray(rawKeyring)) {
    throw new Error("CMS receipt keyring must be a JSON object");
  }
  // Key IDs have a deliberately narrow unescaped ASCII syntax. Scan the flat
  // keyring text so JSON.parse cannot silently collapse duplicate object keys.
  const rawKeyIds = [...values[0].matchAll(/"([^"\\]+)"\s*:/g)].map((match) => match[1]);
  if (rawKeyIds.length !== Object.keys(rawKeyring).length
      || rawKeyIds.some((keyId) => !KEY_ID_PATTERN.test(keyId))
      || new Set(rawKeyIds).size !== rawKeyIds.length) {
    throw new Error("CMS receipt keyring contains invalid or duplicate key IDs");
  }

  const keyring = new Map();
  for (const [keyId, keyHex] of Object.entries(rawKeyring)) {
    if (!KEY_ID_PATTERN.test(keyId) || typeof keyHex !== "string" || !/^(?:[a-fA-F0-9]{2})+$/.test(keyHex)) {
      throw new Error("CMS receipt keyring entry is invalid");
    }
    const key = Buffer.from(keyHex, "hex");
    if (key.length < 32) throw new Error("CMS receipt keyring key is shorter than 32 bytes");
    keyring.set(keyId, key);
  }

  const activeKeyId = values[1];
  if (!KEY_ID_PATTERN.test(activeKeyId)) throw new Error("CMS receipt active key ID is invalid");
  const trustedIds = values[2].split(",").map((item) => item.trim()).filter(Boolean);
  if (trustedIds.some((item) => !KEY_ID_PATTERN.test(item))) throw new Error("CMS receipt trusted key ID is invalid");
  if (new Set(trustedIds).size !== trustedIds.length) throw new Error("CMS receipt trusted key IDs contain duplicates");
  if (trustedIds.some((item) => !keyring.has(item))) throw new Error("CMS receipt trusted key IDs must exist in the keyring");
  if (!keyring.has(activeKeyId)) throw new Error("CMS receipt active key must exist in the keyring");
  if (!trustedIds.includes(activeKeyId)) throw new Error("CMS receipt active key must be explicitly trusted");

  return Object.freeze({ activeKeyId, signingKey: keyring.get(activeKeyId) });
}

function canonicalDatabaseTimestamp(value, field) {
  if (typeof value !== "string" || !Number.isFinite(Date.parse(value))) {
    throw new TypeError(`CMS receipt ${field} timestamp is invalid`);
  }
  return new Date(value).toISOString().replace(/\.(\d{3})Z$/, ".$1000+00:00");
}

export function receiptPayloadForEvent(event) {
  if (!event || typeof event !== "object") throw new TypeError("CMS event is required for receipt creation");
  if (event.topic !== TOPIC) throw new TypeError("CMS receipt topic is invalid");
  if (!/^\d+$/.test(String(event.catalogId ?? ""))) throw new TypeError("CMS receipt catalog ID is invalid");
  if (!HASH_PATTERN.test(event.sourceId ?? "")) throw new TypeError("CMS receipt source ID fingerprint is invalid");
  if (!HASH_PATTERN.test(event.contentHash ?? "")) throw new TypeError("CMS receipt content hash is invalid");
  if (event.publisher !== "Binance" || event.sourceUrl !== "https://www.binance.com/en/support/announcement") {
    throw new TypeError("CMS receipt publisher or source URL is invalid");
  }
  for (const field of ["catalogName", "eventType", "title", "body", "disclaimer"]) {
    if (typeof event[field] !== "string") throw new TypeError(`CMS receipt ${field} must be text`);
  }
  return {
    authority_id: AUTHORITY_ID,
    schema_version: "cms-announcement-normalized-v1",
    topic: event.topic,
    catalog_id: String(event.catalogId),
    source_id: event.sourceId,
    content_hash: event.contentHash,
    catalog_name: event.catalogName,
    event_type: event.eventType,
    title: event.title,
    body: event.body,
    disclaimer: event.disclaimer,
    publisher: event.publisher,
    source_url: event.sourceUrl,
    published_at: canonicalDatabaseTimestamp(event.publishedAt, "publishedAt"),
    observed_at: canonicalDatabaseTimestamp(event.observedAt, "observedAt"),
  };
}

export function createSourceIngestionReceipt(event, config) {
  if (!config || !KEY_ID_PATTERN.test(config.activeKeyId) || !Buffer.isBuffer(config.signingKey) || config.signingKey.length < 32) {
    throw new TypeError("CMS receipt signing configuration is invalid");
  }
  const payloadHash = createHash("sha256").update(canonicalJson(receiptPayloadForEvent(event)), "utf8").digest("hex");
  const signature = createHmac("sha256", config.signingKey)
    .update(signingBytes(RECEIPT_VERSION, AUTHORITY_ID, config.activeKeyId, payloadHash))
    .digest("hex");
  return Object.freeze({
    version: RECEIPT_VERSION,
    authority_id: AUTHORITY_ID,
    key_id: config.activeKeyId,
    payload_hash: payloadHash,
    signature,
  });
}

export function validateSourceIngestionReceipt(receipt) {
  const expected = ["authority_id", "key_id", "payload_hash", "signature", "version"];
  if (!receipt || typeof receipt !== "object" || Array.isArray(receipt)
      || Object.keys(receipt).sort().join("|") !== expected.join("|")) {
    throw new TypeError("CMS ingestion receipt envelope is invalid");
  }
  if (receipt.version !== RECEIPT_VERSION || receipt.authority_id !== AUTHORITY_ID
      || !KEY_ID_PATTERN.test(receipt.key_id ?? "") || !HASH_PATTERN.test(receipt.payload_hash ?? "")
      || !HASH_PATTERN.test(receipt.signature ?? "")) {
    throw new TypeError("CMS ingestion receipt envelope is invalid");
  }
  return receipt;
}
