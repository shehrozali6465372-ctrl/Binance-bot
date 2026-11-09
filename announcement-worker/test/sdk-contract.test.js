import assert from "node:assert/strict";
import test from "node:test";
import { Cms, CMS_WS_STREAMS_PROD_URL } from "@binance/cms";

test("official Binance CMS package exports and constructor contract", () => {
  assert.equal(typeof Cms, "function");
  assert.equal(typeof CMS_WS_STREAMS_PROD_URL, "string");
  assert.match(CMS_WS_STREAMS_PROD_URL, /^wss:\/\//);

  const client = new Cms({
    configurationWebsocketStreams: {
      apiKey: "offline-test-api-key",
      apiSecret: "offline-test-api-secret",
      wsURL: CMS_WS_STREAMS_PROD_URL,
      reconnectDelay: 5000,
    },
  });

  assert.equal(typeof client.websocketStreams.connect, "function");
  assert.equal(typeof client.websocketStreams, "object");
});
