import { Cms, CMS_WS_STREAMS_PROD_URL } from "@binance/cms";
import pg from "pg";
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
} = {}) {
  databaseUrl = requireVerifiedPostgresUrl(databaseUrl, "DATABASE_URL");
  const maxTimerDelayMs = 2_147_483_647;
  if (!Number.isSafeInteger(heartbeatIntervalMs) || heartbeatIntervalMs < 1 || heartbeatIntervalMs > maxTimerDelayMs) {
    throw new RangeError(`heartbeatIntervalMs must be between 1 and ${maxTimerDelayMs}`);
  }
  if (!Number.isSafeInteger(heartbeatTimeoutMs) || heartbeatTimeoutMs < 1 || heartbeatTimeoutMs > maxTimerDelayMs) {
    throw new RangeError(`heartbeatTimeoutMs must be between 1 and ${maxTimerDelayMs}`);
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

    // Register transport handlers immediately: the socket can fail while the
    // first post-connect database state write is still pending.
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

    stream = connection.comAnnouncementEn();
    await persistOperationalState({}, "LISTENING");
    logger.info("Binance CMS announcement stream connected; read-only ingestion active");

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
            logger.info("Binance announcement persisted", { catalogId: event.catalogId, eventType: event.eventType, contentHash: event.contentHash });
          } else {
            await persistOperationalState({ lastMessageAt: receivedAt });
            logger.info("Duplicate Binance announcement ignored", { contentHash: event.contentHash });
          }
        } catch (error) {
          await markDegraded("message", error, { lastMessageAt: receivedAt });
          logger.error("Announcement rejected or persistence failed", { error: String(error?.message || error).slice(0, 500) });
        }
      }).catch(async (error) => {
        await markDegraded("queue", error);
        logger.error("Announcement processing queue failed", { error: String(error?.message || error).slice(0, 500) });
      });
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
            // Do not close the pool under in-flight writes. Report the bounded
            // shutdown timeout now, then release resources once the queue settles.
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

    return { shutdown, stream, connection, store, pool };
  } catch (error) {
    await store.setState("FAILED", { lastError: String(error?.message || error).slice(0, 500) }).catch(() => {});
    try { stream?.unsubscribe(); } catch {}
    try { await connection?.disconnect(); } catch {}
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
