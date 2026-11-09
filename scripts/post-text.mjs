#!/usr/bin/env node
/**
 * Deprecated direct publisher.
 *
 * All Binance Square publishing must pass through the Python PostPublisher
 * and its durable publication ledger. This script intentionally performs
 * no network requests to prevent bypassing authorization/idempotency checks.
 */
console.error(JSON.stringify({
  success: false,
  error: "Direct publishing is disabled. Use the controlled agent publishing gateway."
}));
process.exit(2);
