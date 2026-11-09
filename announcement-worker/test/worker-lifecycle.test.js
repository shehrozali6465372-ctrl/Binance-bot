import assert from "node:assert/strict";
import test from "node:test";
import { startAnnouncementWorker } from "../src/worker.js";

class FakePool {
  constructor({ failInitialize = false } = {}) {
    this.queries = [];
    this.ended = false;
    this.failInitialize = failInitialize;
  }

  async query(sql, values = []) {
    this.queries.push({ sql, values });
    if (this.failInitialize && sql.includes("CREATE TABLE IF NOT EXISTS")) {
      throw new Error("offline simulated schema initialization failure");
    }
    if (sql.includes("INSERT INTO binance_announcement_events")) {
      return { rowCount: 1, rows: [{ id: 7 }] };
    }
    return { rowCount: 1, rows: [] };
  }

  async end() {
    this.ended = true;
  }
}

class FakeStream {
  constructor() {
    this.listeners = new Map();
    this.unsubscribed = false;
  }

  on(event, callback) {
    if (event !== "message") throw new Error("unsupported stream event");
    this.listeners.set(event, callback);
  }

  emitMessage(message) {
    this.listeners.get("message")?.(message);
  }

  unsubscribe() {
    this.unsubscribed = true;
  }
}

class FakeConnection {
  constructor() {
    this.listeners = new Map();
    this.stream = new FakeStream();
    this.disconnected = false;
  }

  comAnnouncementEn() {
    return this.stream;
  }

  on(event, callback) {
    this.listeners.set(event, callback);
  }

  emit(event, ...args) {
    this.listeners.get(event)?.(...args);
  }

  async disconnect() {
    this.disconnected = true;
  }
}

const logger = {
  info() {},
  warn() {},
  error() {},
};

async function startWithFakes({ connectError } = {}) {
  const pool = new FakePool();
  const connection = new FakeConnection();
  const configuration = {};
  const worker = await startAnnouncementWorker({
    apiKey: "offline-test-key",
    apiSecret: "offline-test-secret",
    databaseUrl: "postgresql://offline.invalid/db",
    cmsFactory: (value) => {
      Object.assign(configuration, value);
      return {
        websocketStreams: {
          connect: async () => {
            if (connectError) throw connectError;
            return connection;
          },
        },
      };
    },
    poolFactory: () => pool,
    logger,
  });
  return { worker, pool, connection, configuration };
}

test("worker consumes a mocked CMS message and shuts down all resources", async () => {
  const { worker, pool, connection, configuration } = await startWithFakes();
  assert.equal(configuration.apiKey, "offline-test-key");
  assert.equal(configuration.apiSecret, "offline-test-secret");

  connection.stream.emitMessage({
    catalogId: 48,
    catalogName: "New Cryptocurrency Listing",
    publishDate: Date.now(),
    title: "Binance will list Example (BTC)",
    body: "Mock announcement body",
    disclaimer: "",
  });
  await new Promise((resolve) => setImmediate(resolve));

  assert.equal(
    pool.queries.filter(({ sql }) => sql.includes("INSERT INTO binance_announcement_events")).length,
    1,
  );
  await worker.shutdown("test");
  assert.equal(connection.stream.unsubscribed, true);
  assert.equal(connection.disconnected, true);
  assert.equal(pool.ended, true);
  assert.ok(pool.queries.some(({ values }) => values[0] === "STOPPED"));
});

test("transport errors mark DEGRADED and reconnect open restores LISTENING", async () => {
  const { worker, pool, connection } = await startWithFakes();
  connection.emit("error", new Error("offline simulated socket error"));
  await new Promise((resolve) => setImmediate(resolve));
  assert.ok(pool.queries.some(({ values }) => values[0] === "DEGRADED"));

  connection.emit("open");
  await new Promise((resolve) => setImmediate(resolve));
  const states = pool.queries
    .filter(({ sql }) => sql.includes("binance_announcement_worker_state"))
    .map(({ values }) => values[0]);
  assert.equal(states.at(-1), "LISTENING");
  await worker.shutdown("test");
});

test("failed initial connection records FAILED and closes the database pool", async () => {
  const pool = new FakePool();
  await assert.rejects(
    startAnnouncementWorker({
      apiKey: "offline-test-key",
      apiSecret: "offline-test-secret",
      databaseUrl: "postgresql://offline.invalid/db",
      cmsFactory: () => ({
        websocketStreams: {
          connect: async () => {
            throw new Error("offline simulated connection failure");
          },
        },
      }),
      poolFactory: () => pool,
      logger,
    }),
    /offline simulated connection failure/,
  );
  assert.ok(pool.queries.some(({ values }) => values[0] === "FAILED"));
  assert.equal(pool.ended, true);
});


test("database initialization failure still closes the pool", async () => {
  const pool = new FakePool({ failInitialize: true });
  let cmsFactoryCalled = false;
  await assert.rejects(
    startAnnouncementWorker({
      apiKey: "offline-test-key",
      apiSecret: "offline-test-secret",
      databaseUrl: "postgresql://offline.invalid/db",
      cmsFactory: () => {
        cmsFactoryCalled = true;
        throw new Error("CMS must not initialize after database failure");
      },
      poolFactory: () => pool,
      logger,
    }),
    /offline simulated schema initialization failure/,
  );
  assert.equal(cmsFactoryCalled, false);
  assert.ok(pool.queries.some(({ values }) => values[0] === "FAILED"));
  assert.equal(pool.ended, true);
});
