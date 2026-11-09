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

export async function startAnnouncementWorker({
  apiKey = requiredEnv("BINANCE_API_KEY"),
  apiSecret = requiredEnv("BINANCE_API_SECRET"),
  databaseUrl = requiredEnv("DATABASE_URL"),
  cmsFactory = (configuration) => new Cms({ configurationWebsocketStreams: configuration }),
  poolFactory = (options) => new Pool(options),
  logger = console,
} = {}) {
  const pool = poolFactory({ connectionString: databaseUrl, max: 3, application_name: "binance-cms-announcement-worker" });
  const store = new AnnouncementStore(pool);
  await store.initialize();
  await store.setState("STARTING", { startedAt: new Date().toISOString() });

  const client = cmsFactory({
    apiKey,
    apiSecret,
    wsURL: process.env.BINANCE_CMS_WS_URL || CMS_WS_STREAMS_PROD_URL,
    reconnectDelay: 5000,
  });

  let connection;
  let closed = false;
  let writeQueue = Promise.resolve();

  try {
    connection = await client.websocketStreams.connect();
    const stream = connection.comAnnouncementEn();
    await store.setState("LISTENING");
    logger.info("Binance CMS announcement stream connected; read-only ingestion active");

    stream.on("message", (message) => {
      writeQueue = writeQueue.then(async () => {
        if (closed) return;
        const receivedAt = new Date().toISOString();
        await store.setState("RECEIVING", { lastMessageAt: receivedAt });
        try {
          const event = normalizeAnnouncementMessage(message, receivedAt);
          const inserted = await store.save(event);
          if (inserted) {
            await store.setState("LISTENING", { lastMessageAt: receivedAt, lastPersistedAt: new Date().toISOString() });
            logger.info("Binance announcement persisted", { catalogId: event.catalogId, eventType: event.eventType, contentHash: event.contentHash });
          } else {
            await store.setState("LISTENING", { lastMessageAt: receivedAt });
            logger.info("Duplicate Binance announcement ignored", { contentHash: event.contentHash });
          }
        } catch (error) {
          await store.setState("DEGRADED", { lastMessageAt: receivedAt, lastError: String(error?.message || error).slice(0, 500) });
          logger.error("Announcement rejected or persistence failed", { error: String(error?.message || error).slice(0, 500) });
        }
      }).catch(async (error) => {
        await store.setState("DEGRADED", { lastError: String(error?.message || error).slice(0, 500) });
        logger.error("Announcement processing queue failed", { error: String(error?.message || error).slice(0, 500) });
      });
    });

    // The SDK's stream handler only supports "message". Transport-level
    // lifecycle events belong to WebsocketStreamsConnection.on().
    connection.on("error", (error) => {
      const message = String(error?.message || error).slice(0, 500);
      logger.error("Binance CMS connection error", { error: message });
      if (!closed) {
        void store.setState("DEGRADED", { lastError: message }).catch(() => {});
      }
    });
    connection.on("close", (code, reason) => {
      const message = `WebSocket closed (code=${code ?? "unknown"}, reason=${String(reason ?? "").slice(0, 200)})`;
      logger.warn("Binance CMS connection closed", { code, reason: String(reason ?? "").slice(0, 200) });
      if (!closed) {
        void store.setState("DEGRADED", { lastError: message }).catch(() => {});
      }
    });

    const shutdown = async (signal = "shutdown") => {
      if (closed) return;
      closed = true;
      logger.info("Stopping announcement worker", { signal });
      await writeQueue;
      await store.setState("STOPPED").catch(() => {});
      try { stream.unsubscribe(); } catch {}
      try { await connection.disconnect(); } catch {}
      await pool.end();
    };

    return { shutdown, stream, connection, store, pool };
  } catch (error) {
    await store.setState("FAILED", { lastError: String(error?.message || error).slice(0, 500) }).catch(() => {});
    await pool.end();
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
