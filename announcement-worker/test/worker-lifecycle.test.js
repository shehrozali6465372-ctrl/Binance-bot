import assert from "node:assert/strict";
import test from "node:test";
import { startAnnouncementWorker } from "../src/worker.js";

class FakePool {
  constructor({ failInitialize = false, insertBarrier = null, onInsertStarted = null, failStateUpdates = {} } = {}) {
    this.queries = [];
    this.ended = false;
    this.failInitialize = failInitialize;
    this.insertBarrier = insertBarrier;
    this.onInsertStarted = onInsertStarted;
    this.failStateUpdates = { ...failStateUpdates };
  }

  async query(sql, values = []) {
    this.queries.push({ sql, values });
    if (this.failInitialize && sql.includes("SELECT id FROM binance_announcement_events")) {
      throw new Error("offline simulated runtime schema permission failure");
    }
    if (sql.includes("binance_announcement_worker_state")) {
      const state = values[0];
      if ((this.failStateUpdates[state] || 0) > 0) {
        this.failStateUpdates[state] -= 1;
        throw new Error(`offline simulated ${state} state update failure`);
      }
    }
    if (sql.includes("INSERT INTO binance_announcement_events")) {
      this.onInsertStarted?.();
      if (this.insertBarrier) await this.insertBarrier;
      return { rowCount: 1, rows: [{ id: this.queries.length }] };
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
    this.pingCount = 0;
    this.onPing = null;
  }

  isConnected() {
    return !this.disconnected;
  }

  pingServer() {
    this.pingCount += 1;
    this.onPing?.();
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

async function startWithFakes({ connectError, poolOptions, shutdownTimeoutMs, heartbeatIntervalMs, heartbeatTimeoutMs } = {}) {
  const pool = new FakePool(poolOptions);
  const connection = new FakeConnection();
  const configuration = {};
  const worker = await startAnnouncementWorker({
    apiKey: "offline-test-key",
    apiSecret: "offline-test-secret",
    databaseUrl: "postgresql://offline.invalid/db?sslmode=verify-full",
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
    poolFactory: (options) => {
      Object.assign(configuration.poolOptions ??= {}, options);
      return pool;
    },
    logger,
    shutdownTimeoutMs,
    heartbeatIntervalMs,
    heartbeatTimeoutMs,
  });
  return { worker, pool, connection, configuration, poolOptions: configuration.poolOptions };
}

test("worker bounds PostgreSQL connection establishment", async () => {
  const { worker, poolOptions } = await startWithFakes();
  assert.equal(poolOptions.connectionTimeoutMillis, 10_000);
  await worker.shutdown();
});

test("worker rejects invalid heartbeat timing before creating a database pool", async () => {
  let poolFactoryCalled = false;
  await assert.rejects(startAnnouncementWorker({
    apiKey: "offline-test-key",
    apiSecret: "offline-test-secret",
    databaseUrl: "postgresql://offline.invalid/db?sslmode=verify-full",
    heartbeatIntervalMs: 0,
    poolFactory: () => { poolFactoryCalled = true; throw new Error("pool must not be created"); },
    logger,
  }), /heartbeatIntervalMs must be between 1 and 2147483647/);
  assert.equal(poolFactoryCalled, false);
});

test("worker sends WebSocket heartbeats and restores LISTENING after a pong", async () => {
  const { worker, pool, connection } = await startWithFakes({ heartbeatIntervalMs: 5, heartbeatTimeoutMs: 20 });
  connection.onPing = () => setImmediate(() => connection.emit("pong"));
  await new Promise((resolve) => setTimeout(resolve, 20));
  assert.ok(connection.pingCount > 0, "worker should actively ping the CMS socket");
  const states = pool.queries
    .filter(({ sql }) => sql.includes("binance_announcement_worker_state"))
    .map(({ values }) => values[0]);
  assert.equal(states.at(-1), "LISTENING", "a successful pong should refresh healthy state");
  await worker.shutdown("test");
});

test("worker marks the CMS stream DEGRADED when heartbeat pong times out", async () => {
  const { worker, pool, connection } = await startWithFakes({ heartbeatIntervalMs: 5, heartbeatTimeoutMs: 5 });
  await new Promise((resolve) => setTimeout(resolve, 20));
  assert.ok(connection.pingCount > 0, "worker should send a ping before waiting for pong");
  const degraded = pool.queries.find(({ sql, values }) =>
    sql.includes("binance_announcement_worker_state") && values[0] === "DEGRADED" &&
    String(values[4] || "").includes("heartbeat pong timeout"),
  );
  assert.ok(degraded, "missing pong should be recorded as DEGRADED with a diagnostic");
  await worker.shutdown("test");
});

test("shutdown stops heartbeat scheduling and cancels an outstanding pong timeout", async () => {
  const { worker, connection, pool } = await startWithFakes({ heartbeatIntervalMs: 5, heartbeatTimeoutMs: 100 });
  await new Promise((resolve) => setTimeout(resolve, 12));
  assert.ok(connection.pingCount > 0);
  await worker.shutdown("test");
  const pingCountAtShutdown = connection.pingCount;
  await new Promise((resolve) => setTimeout(resolve, 15));
  assert.equal(connection.pingCount, pingCountAtShutdown, "no heartbeat should run after shutdown");
  const states = pool.queries
    .filter(({ sql }) => sql.includes("binance_announcement_worker_state"))
    .map(({ values }) => values[0]);
  assert.equal(states.at(-1), "STOPPED");
});

test("heartbeat recovery does not erase an unrelated database degradation", async () => {
  const { worker, pool, connection } = await startWithFakes({
    poolOptions: { failStateUpdates: { RECEIVING: 1 } },
    heartbeatIntervalMs: 5,
    heartbeatTimeoutMs: 20,
  });
  connection.onPing = () => setImmediate(() => connection.emit("pong"));
  connection.stream.emitMessage({
    catalogId: 48,
    catalogName: "New Cryptocurrency Listing",
    publishDate: Date.now(),
    title: "Database failure must remain degraded (DBX)",
    body: "Mock announcement body",
    disclaimer: "",
  });
  await new Promise((resolve) => setTimeout(resolve, 20));
  const latest = pool.queries
    .filter(({ sql }) => sql.includes("binance_announcement_worker_state"))
    .at(-1);
  assert.equal(latest.values[0], "DEGRADED");
  assert.match(latest.values[4], /offline simulated RECEIVING state update failure/);
  await worker.shutdown("test");
});

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


function deferred() {
  let resolve;
  const promise = new Promise((done) => { resolve = done; });
  return { promise, resolve };
}

test("shutdown drains every accepted message queued behind a delayed database write", async () => {
  const insertBarrier = deferred();
  const firstInsertStarted = deferred();
  const { worker, pool, connection } = await startWithFakes({
    poolOptions: {
      insertBarrier: insertBarrier.promise,
      onInsertStarted: () => firstInsertStarted.resolve(),
    },
  });
  const message = (title) => ({
    catalogId: 48,
    catalogName: "New Cryptocurrency Listing",
    publishDate: Date.now(),
    title,
    body: "Mock announcement body",
    disclaimer: "",
  });

  connection.stream.emitMessage(message("First queued announcement (AAA)"));
  connection.stream.emitMessage(message("Second queued announcement (BBB)"));
  await firstInsertStarted.promise;

  const shutdown = worker.shutdown("SIGTERM");
  connection.stream.emitMessage(message("Must not be accepted after shutdown (CCC)"));
  insertBarrier.resolve();
  await shutdown;

  const persistedCount = pool.queries.filter(({ sql }) =>
    sql.includes("INSERT INTO binance_announcement_events"),
  ).length;
  assert.equal(persistedCount, 2, "both messages accepted before shutdown must persist");
  assert.equal(connection.stream.unsubscribed, true);
  assert.equal(connection.disconnected, true);
  assert.equal(pool.ended, true);
});

test("shutdown timeout leaves the pool open until accepted writes settle", async () => {
  const insertBarrier = deferred();
  const firstInsertStarted = deferred();
  const { worker, pool, connection } = await startWithFakes({
    poolOptions: {
      insertBarrier: insertBarrier.promise,
      onInsertStarted: () => firstInsertStarted.resolve(),
    },
    shutdownTimeoutMs: 10,
  });

  connection.stream.emitMessage({
    catalogId: 48,
    catalogName: "New Cryptocurrency Listing",
    publishDate: Date.now(),
    title: "Delayed announcement (DDD)",
    body: "Mock announcement body",
    disclaimer: "",
  });
  await firstInsertStarted.promise;

  await assert.rejects(worker.shutdown("SIGTERM"), {
    code: "ERR_SHUTDOWN_TIMEOUT",
  });
  assert.equal(connection.stream.unsubscribed, true);
  assert.equal(pool.ended, false, "pool must stay open while an accepted write is in flight");

  insertBarrier.resolve();
  for (let attempt = 0; attempt < 10 && !pool.ended; attempt += 1) {
    await new Promise((resolve) => setImmediate(resolve));
  }
  assert.equal(pool.ended, true, "resources close after the accepted write settles");
});

test("write queue recovers after RECEIVING and DEGRADED state updates both fail", async () => {
  const pool = new FakePool({ failStateUpdates: { RECEIVING: 1, DEGRADED: 1 } });
  const connection = new FakeConnection();
  const worker = await startAnnouncementWorker({
    apiKey: "offline-test-key",
    apiSecret: "offline-test-secret",
    databaseUrl: "postgresql://offline.invalid/db?sslmode=verify-full",
    cmsFactory: () => ({ websocketStreams: { connect: async () => connection } }),
    poolFactory: () => pool,
    logger,
  });

  const message = (symbol) => ({
    catalogId: 48,
    catalogName: "New Cryptocurrency Listing",
    publishDate: Date.now(),
    title: `Recovery announcement (${symbol})`,
    body: "Mock announcement body",
    disclaimer: "",
  });
  connection.stream.emitMessage(message("FIRST"));
  await new Promise((resolve) => setImmediate(resolve));
  connection.stream.emitMessage(message("RECOVERED"));
  await new Promise((resolve) => setImmediate(resolve));
  await new Promise((resolve) => setImmediate(resolve));

  const inserted = pool.queries.filter(({ sql }) => sql.includes("INSERT INTO binance_announcement_events"));
  assert.equal(inserted.length, 1, "the next accepted message must run after the prior callback rejects");
  assert.match(inserted[0].values[6], /RECOVERED/);
  await worker.shutdown("test");
});

test("startup failure after websocket connect disconnects the opened connection", async () => {
  const pool = new FakePool({ failStateUpdates: { LISTENING: 1 } });
  const connection = new FakeConnection();
  await assert.rejects(
    startAnnouncementWorker({
      apiKey: "offline-test-key",
      apiSecret: "offline-test-secret",
      databaseUrl: "postgresql://offline.invalid/db?sslmode=verify-full",
      cmsFactory: () => ({ websocketStreams: { connect: async () => connection } }),
      poolFactory: () => pool,
      logger,
    }),
    /offline simulated LISTENING state update failure/,
  );
  assert.equal(connection.disconnected, true, "startup cleanup must close a socket opened before failure");
  assert.equal(pool.ended, true);
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
      databaseUrl: "postgresql://offline.invalid/db?sslmode=verify-full",
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


test("runtime schema permission failure prevents CMS startup and closes the pool", async () => {
  const pool = new FakePool({ failInitialize: true });
  let cmsFactoryCalled = false;
  await assert.rejects(
    startAnnouncementWorker({
      apiKey: "offline-test-key",
      apiSecret: "offline-test-secret",
      databaseUrl: "postgresql://offline.invalid/db?sslmode=verify-full",
      cmsFactory: () => {
        cmsFactoryCalled = true;
        throw new Error("CMS must not initialize after database failure");
      },
      poolFactory: () => pool,
      logger,
    }),
    /offline simulated runtime schema permission failure/,
  );
  assert.equal(cmsFactoryCalled, false);
  assert.ok(pool.queries.some(({ values }) => values[0] === "FAILED"));
  assert.equal(pool.ended, true);
});


test("worker rejects a database URL without verified TLS before creating a pool", async () => {
  let poolFactoryCalled = false;
  await assert.rejects(startAnnouncementWorker({
    apiKey: "offline-test-key",
    apiSecret: "offline-test-secret",
    databaseUrl: "postgresql://offline.invalid/db",
    poolFactory: () => { poolFactoryCalled = true; throw new Error("pool must not be created"); },
    logger,
  }), /DATABASE_URL must include sslmode=verify-full/);
  assert.equal(poolFactoryCalled, false);
});
