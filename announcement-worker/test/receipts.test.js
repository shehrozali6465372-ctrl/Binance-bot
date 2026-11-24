import assert from "node:assert/strict";
import test from "node:test";
import {
  createSourceIngestionReceipt,
  loadReceiptSigningConfig,
  receiptPayloadForEvent,
} from "../src/receipts.js";

const key = Buffer.from("cms-test-key-material-at-least-thirty-two-bytes", "utf8");
const event = {
  sourceId: "a".repeat(64),
  contentHash: "b".repeat(64),
  topic: "com_announcement_en",
  catalogId: "48",
  catalogName: "New Cryptocurrency Listing",
  eventType: "listing",
  title: "Binance will list Example (EXM)",
  body: "Official announcement body",
  disclaimer: "Risk notice",
  publisher: "Binance",
  sourceUrl: "https://www.binance.com/en/support/announcement",
  publishedAt: "2026-11-23T23:00:00.000Z",
  observedAt: "2026-11-24T00:00:00.000Z",
};

function env(overrides = {}) {
  return {
    BINANCE_CMS_RECEIPT_HMAC_KEYRING_JSON: JSON.stringify({ "cms-key-v1": key.toString("hex") }),
    BINANCE_CMS_RECEIPT_ACTIVE_KEY_ID: "cms-key-v1",
    BINANCE_CMS_RECEIPT_TRUSTED_KEY_IDS: "cms-key-v1",
    ...overrides,
  };
}

test("receipt payload binds worker authority, topic, catalog, IDs, hashes, timestamps and schema version", () => {
  assert.deepEqual(receiptPayloadForEvent(event), {
    authority_id: "binance_announcement_cms",
    schema_version: "cms-announcement-normalized-v1",
    topic: event.topic,
    catalog_id: event.catalogId,
    source_id: event.sourceId,
    content_hash: event.contentHash,
    catalog_name: event.catalogName,
    event_type: event.eventType,
    title: event.title,
    body: event.body,
    disclaimer: event.disclaimer,
    publisher: event.publisher,
    source_url: event.sourceUrl,
    published_at: "2026-11-23T23:00:00.000000+00:00",
    observed_at: "2026-11-24T00:00:00.000000+00:00",
  });
});

test("receipt is deterministic and uses the shared Python source receipt envelope", () => {
  const config = loadReceiptSigningConfig(env());
  const first = createSourceIngestionReceipt(event, config);
  const second = createSourceIngestionReceipt(event, config);
  assert.deepEqual(first, second);
  assert.deepEqual(Object.keys(first).sort(), ["authority_id", "key_id", "payload_hash", "signature", "version"].sort());
  assert.equal(first.version, 1);
  assert.equal(first.authority_id, "binance_announcement_cms");
  assert.equal(first.key_id, "cms-key-v1");
  assert.equal(first.payload_hash, "8bb92169d013274a44e6bdb269c174591fc561b97d2845e9677389ca57856b20");
  assert.equal(first.signature, "aff3ba4db5d87ce89b6be773780d5a1833bd90f11411d2274517785c17243dfb");
  assert.match(first.payload_hash, /^[a-f0-9]{64}$/);
  assert.match(first.signature, /^[a-f0-9]{64}$/);
});

test("missing receipt configuration is explicit and does not invent a key", () => {
  assert.equal(loadReceiptSigningConfig({}), null);
});

test("partial receipt configuration fails closed", () => {
  assert.throws(() => loadReceiptSigningConfig({
    BINANCE_CMS_RECEIPT_ACTIVE_KEY_ID: "cms-key-v1",
  }), /receipt signing configuration is incomplete/);
});

test("active signer must be provisioned and explicitly trusted", () => {
  const secondKey = Buffer.from("second-cms-key-material-at-least-thirty-two-bytes", "utf8");
  assert.throws(() => loadReceiptSigningConfig(env({
    BINANCE_CMS_RECEIPT_HMAC_KEYRING_JSON: JSON.stringify({
      "cms-key-v1": key.toString("hex"), "other-key": secondKey.toString("hex"),
    }),
    BINANCE_CMS_RECEIPT_TRUSTED_KEY_IDS: "other-key",
  })), /active key must be explicitly trusted/);
  assert.throws(() => loadReceiptSigningConfig(env({
    BINANCE_CMS_RECEIPT_ACTIVE_KEY_ID: "missing-key",
  })), /active key must exist/);
});

test("receipt keyring rejects duplicate trusted IDs and keys shorter than 32 bytes", () => {
  assert.throws(() => loadReceiptSigningConfig(env({
    BINANCE_CMS_RECEIPT_TRUSTED_KEY_IDS: "cms-key-v1,cms-key-v1",
  })), /trusted key IDs contain duplicates/);
  assert.throws(() => loadReceiptSigningConfig(env({
    BINANCE_CMS_RECEIPT_HMAC_KEYRING_JSON: JSON.stringify({ "cms-key-v1": Buffer.from("short").toString("hex") }),
  })), /shorter than 32 bytes/);
});

test("receipt creation rejects malformed normalized event identities", () => {
  const config = loadReceiptSigningConfig(env());
  assert.throws(() => createSourceIngestionReceipt({ ...event, contentHash: "bad" }, config), /content hash/);
});


test("receipt keyring rejects duplicate JSON object keys before JSON.parse can collapse them", () => {
  const duplicate = `{"cms-key-v1":"${key.toString("hex")}","cms-key-v1":"${key.toString("hex")}"}`;
  assert.throws(() => loadReceiptSigningConfig(env({
    BINANCE_CMS_RECEIPT_HMAC_KEYRING_JSON: duplicate,
  })), /invalid or duplicate key IDs/);
});
