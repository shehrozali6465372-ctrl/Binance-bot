[Reading 403 lines from start (total: 403 lines, 0 remaining)]

import { Cms, CMS_WS_STREAMS_PROD_URL } from "@binance/cms";
import pg from "pg";
import { createServer } from "node:http";
import { normalizeAnnouncementMessage } from "./normalize.js";
import { AnnouncementStore } from "./store.js";

const { Pool } = pg;

function requiredEnv(name) {
  const value = process.env[name];
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(name + " environment variable is required");
  }
  return value.trim();
}

function requireVerifiedPostgresUrl(value, name) {
  let parsed;
  try { parsed = new URL(value); }
  catch { throw new Error(`${name} must be a valid PostgreSQL connection URL`); }
  if (!["postgres:", "postgresql:"].includes(parsed.protocol)) {
    throw new Error(`${name} must use the PostgreSQL protocol`);
  }
  if (parsed.searchParams.get("sslmode") !== "verify-full") {
    throw new Error(`${name} must include sslmode=verify-full`);
  }
  return value;
}

function createHealthServer({ handler }) {
  return {
    server: createServer((request, response) => {
      Promise.resolve(handler(request)).then((result) => {
        response.writeHead(result.statusCode, {
          "content-type": "application/json; charset=utf-8",
          "cache-control": "no-store",
        });
        response.end(JSON.stringify(result.body));
      }).catch(() => {
        response.writeHead(500);
        response.end();
      });
    }),
    listen(port, host) {
      return new Promise((resolve, reject) => {
        const server = this.server;
        const onError = (error) => {
          server.off("listening", onListening);
          reject(error);
        };
        const onListening = () => {
          server.off("error", onError);
          resolve();
        };
        server.once("error", onError);
        server.once("listening", onListening);
        server.listen(port, host);
      });
    },
    address() { return this.server.address(); },
    close() {
      if (!this.server.listening) return Promise.resolve();
      return new Promise((resolve, reject) => {
        this.server.close((error) => error ? reject(error) : resolve());
      });
    },
  };
}

export async function startAnnouncementWorker({
  apiKey = requiredEnv("BINANCE_API_KEY"),
  apiSecret = requiredEnv("BINANCE_API_SECRET"),
  databaseUrl = requiredEnv("DATABASE_URL"),
  cmsFactory = (configuration) => new Cms({ configurationWebsocketStreams: configuration }),
  poolFactory = (options) => new Pool(options),
  logger = console,
  shutdownTimeoutMs = 30_000,
  heartbeatIntervalMs = 30_000,
  heartbeatTimeoutMs = 10_000,
  healthServerFactory = createHealthServer,
  publicServiceUrl = process.env.PUBLIC_SERVICE_URL,
  keepaliveIntervalMs = 13 * 60 * 1000,
  fetchImpl = globalThis.fetch,
} = {}) {
  databaseUrl = requireVerifiedPostgresUrl(databaseUrl, "DATABASE_URL");
  const maxTimerDelayMs = 2_147_483_647;
  if (!Number.isSafeInteger(heartbeatIntervalMs) || heartbeatIntervalMs < 1 || heartbeatIntervalMs > maxTimerDelayMs) {
    throw new RangeError(`heartbeatIntervalMs must be between 1 and ${maxTimerDelayMs}`);
  }
  if (!Number.isSafeInteger(heartbeatTimeoutMs) || heartbeatTimeoutMs < 1 || heartbeatTimeoutMs > maxTimerDelayMs) {
    throw new RangeError(`heartbeatTimeoutMs must be between 1 and ${maxTimerDelayMs}`);
  }
  if (!Number.isSafeInteger(keepaliveIntervalMs) || keepaliveIntervalMs < 1 || keepaliveIntervalMs > maxTimerDelayMs) {
    throw new RangeError(`keepaliveIntervalMs must be between 1 and ${maxTimerDelayMs}`);
  }

  let parsedPublicServiceUrl;
  if (publicServiceUrl !== undefined && publicServiceUrl !== "") {
    try { parsedPublicServiceUrl = new URL(publicServiceUrl); } catch { /* checked below */ }
    if (!parsedPublicServiceUrl || parsedPublicServiceUrl.protocol !== "https:" ||
        parsedPublicServiceUrl.username || parsedPublicServiceUrl.password) {
      throw new Error("PUBLIC_SERVICE_URL must be an absolute HTTPS URL without embedded credentials");
    }
    if (typeof fetchImpl !== "function") {
      throw new Error("fetch implementation is required when PUBLIC_SERVICE_URL is configured");
    }
  }

  const pool = poolFactory({
    connectionString: databaseUrl,
    max: 3,
    connectionTimeoutMillis: 10_000,
    application_name: "binance-cms-announcement-worker",
  });
  const store = new AnnouncementStore(pool);
  let connection;
  let stream;
  let closed = false;
  let acceptingMessages = true;
  let shutdownPromise;
  let resourcesClosed = false;
  let writeQueue = Promise.resolve();
  let heartbeatInterval;
  let heartbeatTimeout;
  let healthServer;
  let keepaliveInterval;
  let keepaliveInFlight = false;
  let awaitingHeartbeatPong = false;
  const degradationReasons = new Map();

  const persistOperationalState = async (fields = {}, healthyStatus = "LISTENING") => {
    const errors = [...degradationReasons.values()];
    await store.setState(errors.length ? "DEGRADED" : healthyStatus, {
      ...fields,
      lastError: errors.length ? errors.join("; ").slice(0, 500) : null,
    });
  };

  const markDegraded = async (kind, error, fields = {}) => {
    const message = String(error?.message || error).slice(0, 500);
    degradationReasons.set(kind, message);
    try {
      await persistOperationalState(fields);
    } catch (stateError) {
      logger.error("Could not persist degraded announcement worker state", {
        reason: kind,
        error: String(stateError?.message || stateError).slice(0, 500),
      });
    }
  };

  const clearDegraded = async (kind, fields = {}) => {
    degradationReasons.delete(kind);
    try {
      await persistOperationalState(fields);
    } catch (stateError) {
      logger.error("Could not persist recovered announcement worker state", {
        reason: kind,
        error: String(stateError?.message || stateError).slice(0, 500),
      });
    }
  };

  const clearPendingHeartbeat = () => {
    awaitingHeartbeatPong = false;
    if (heartbeatTimeout) clearTimeout(heartbeatTimeout);
    heartbeatTimeout = undefined;
  };

  try {
    await store.initialize();
    await store.setState("STARTING", { startedAt: new Date().toISOString() });

    const client = cmsFactory({
      apiKey,
      apiSecret,
      wsURL: process.env.BINANCE_CMS_WS_URL || CMS_WS_STREAMS_PROD_URL,
      reconnectDelay: 5000,
    });
    connection = await client.websocketStreams.connect();
    stream = connection.comAnnouncementEn();
    await store.setState("LISTENING");
    logger.info("Binance CMS announcement stream connected; read-only ingestion active");

    const healthHandler = (request) => {
      if (request.method !== "GET" || request.url?.split("?", 1)[0] !== "/health") {
        return { statusCode: 404, body: { status: "not_found" } };
      }
      return {
        statusCode: 200,
        body: { status: "ok", service: "binance-cms-announcement-worker" },
      };
    };
    healthServer = healthServerFactory({ handler: healthHandler });
    await healthServer.listen(Number(process.env.PORT || 10000), "0.0.0.0");

    if (parsedPublicServiceUrl) {
      keepaliveInterval = setInterval(async () => {
        if (closed || keepaliveInFlight) return;
        keepaliveInFlight = true;
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 10_000);
        timeout.unref?.();
        try {
          const response = await fetchImpl(parsedPublicServiceUrl, {
            method: "GET",
            signal: controller.signal,
            headers: { "user-agent": "binance-cms-worker-keepalive/1.0" },
          });
          if (!response?.ok) {
            logger.warn("CMS worker keepalive health request returned non-2xx", { status: response?.status });
          }
        } catch (error) {
          if (!closed) {
            logger.warn("CMS worker keepalive health request failed", {
              error: String(error?.message || error).slice(0, 200),
            });
          }
        } finally {
          clearTimeout(timeout);
          keepaliveInFlight = false;
        }
      }, keepaliveIntervalMs);
      keepaliveInterval.unref?.();
    }

    stream.on("message", (message) => {
      if (!acceptingMessages) return;
      writeQueue = writeQueue.then(async () => {
        const receivedAt = new Date().toISOString();
        await persistOperationalState({ lastMessageAt: receivedAt }, "RECEIVING");
        try {
          const event = normalizeAnnouncementMessage(message, receivedAt);
          const inserted = await store.save(event);
          degradationReasons.delete("message");
          degradationReasons.delete("queue");
          if (inserted) {
            await persistOperationalState({ lastMessageAt: receivedAt, lastPersistedAt: new Date().toISOString() });
            logger.info("Binance announcement persisted", {
              catalogId: event.catalogId,
              eventType: event.eventType,
              contentHash: event.contentHash,
            });
          } else {
            await persistOperationalState({ lastMessageAt: receivedAt });
            logger.info("Duplicate Binance announcement ignored", { contentHash: event.contentHash });
          }
        } catch (error) {
          await markDegraded("message", error, { lastMessageAt: receivedAt });
          logger.error("Announcement rejected or persistence failed", {
            error: String(error?.message || error).slice(0, 500),
          });
        }
      }).catch(async (error) => {
        await markDegraded("queue", error);
        logger.error("Announcement processing queue failed", {
          error: String(error?.message || error).slice(0, 500),
        });
      });
    });

    // The SDK's stream handler only supports "message". Transport-level
    // lifecycle events belong to WebsocketStreamsConnection.on().
    connection.on("open", () => {
      if (!closed) {
        clearPendingHeartbeat();
        degradationReasons.delete("transport");
        degradationReasons.delete("heartbeat");
        void persistOperationalState().catch((error) => {
          logger.error("Could not persist recovered WebSocket state", {
            error: String(error?.message || error).slice(0, 500),
          });
        });
      }
    });
    connection.on("error", (error) => {
      const message = String(error?.message || error).slice(0, 500);
      logger.error("Binance CMS connection error", { error: message });
      if (!closed) void markDegraded("transport", message);
    });
    connection.on("close", (code, reason) => {
      const message = `WebSocket closed (code=${code ?? "unknown"}, reason=${String(reason ?? "").slice(0, 200)})`;
      logger.warn("Binance CMS connection closed", { code, reason: String(reason ?? "").slice(0, 200) });
      if (!closed) {
        clearPendingHeartbeat();
        void markDegraded("transport", message);
      }
    });
    connection.on("pong", () => {
      if (closed || !awaitingHeartbeatPong) return;
      clearPendingHeartbeat();
      void clearDegraded("heartbeat");
      logger.info("Binance CMS heartbeat pong received");
    });

    heartbeatInterval = setInterval(() => {
      if (closed || awaitingHeartbeatPong) return;
      let connected = false;
      try { connected = connection.isConnected(); } catch {}
      if (!connected) {
        void markDegraded("transport", new Error("Binance CMS connection is not open during heartbeat check"));
        return;
      }

      awaitingHeartbeatPong = true;
      heartbeatTimeout = setTimeout(() => {
        if (closed || !awaitingHeartbeatPong) return;
        clearPendingHeartbeat();
        void markDegraded("heartbeat", new Error("Binance CMS heartbeat pong timeout"));
      }, heartbeatTimeoutMs);
      heartbeatTimeout.unref?.();

      try {
        connection.pingServer();
      } catch (error) {
        clearPendingHeartbeat();
        void markDegraded("heartbeat", error);
      }
    }, heartbeatIntervalMs);
    heartbeatInterval.unref?.();

    const finalizeShutdown = async () => {
      if (resourcesClosed) return;
      resourcesClosed = true;
      await store.setState("STOPPED").catch(() => {});
      try { await healthServer.close(); } catch {}
      try { await connection.disconnect(); } catch {}
      await pool.end();
    };

    const shutdown = (signal = "shutdown") => {
      if (shutdownPromise) return shutdownPromise;

      // Stop intake synchronously before observing the queue. Message callbacks
      // accepted before this point remain in writeQueue and must be drained.
      acceptingMessages = false;
      closed = true;
      if (heartbeatInterval) clearInterval(heartbeatInterval);
      if (keepaliveInterval) clearInterval(keepaliveInterval);
      clearPendingHeartbeat();
      logger.info("Stopping announcement worker", { signal });
      try { stream.unsubscribe(); } catch {}

      const acceptedWrites = writeQueue;
      shutdownPromise = (async () => {
        let timeoutHandle;
        const timeout = new Promise((_, reject) => {
          timeoutHandle = setTimeout(() => {
            const error = new Error(`Announcement worker shutdown exceeded ${shutdownTimeoutMs}ms while draining accepted writes`);
            error.code = "ERR_SHUTDOWN_TIMEOUT";
            reject(error);
          }, shutdownTimeoutMs);
        });

        try {
          await Promise.race([acceptedWrites, timeout]);
        } catch (error) {
          if (error?.code === "ERR_SHUTDOWN_TIMEOUT") {
            void acceptedWrites.finally(finalizeShutdown).catch((cleanupError) => {
              logger.error("Deferred shutdown cleanup failed", {
                error: String(cleanupError?.message || cleanupError).slice(0, 500),
              });
            });
          }
          throw error;
        } finally {
          clearTimeout(timeoutHandle);
        }

        await finalizeShutdown();
      })();
      return shutdownPromise;
    };

    return { shutdown, stream, connection, store, pool, healthServer };
  } catch (error) {
    await store.setState("FAILED", { lastError: String(error?.message || error).slice(0, 500) }).catch(() => {});
    try { stream?.unsubscribe(); } catch {}
    try { await connection?.disconnect(); } catch {}
    try { await healthServer?.close?.(); } catch {}
    await pool.end().catch(() => {});
    throw error;
  }
}

if (import.meta.url === `file://${process.argv[1]}`) {
  startAnnouncementWorker()
    .then(({ shutdown }) => {
      let stopping = false;
      const stop = async (signal) => {
        if (stopping) return;
        stopping = true;
        try { await shutdown(signal); process.exitCode = 0; }
        catch (error) { console.error("Worker shutdown failed", error); process.exitCode = 1; }
      };
      process.once("SIGTERM", () => void stop("SIGTERM"));
      process.once("SIGINT", () => void stop("SIGINT"));
    })
    .catch((error) => {
      console.error("Binance announcement worker failed to start", String(error?.message || error));
      process.exitCode = 1;
    });
}

[executed on device: localhost (e87fd591-3c93-40d6-8543-95eabff1ca2f)]
