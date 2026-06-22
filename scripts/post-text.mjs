#!/usr/bin/env node

/**
 * Binance Square Post Script
 * Posts text content to Binance Square via Creator Center API
 * 
 * Usage:
 *   BINANCE_SQUARE_OPENAPI_KEY=xxx node scripts/post-text.mjs --text "Hello Square"
 * 
 * Environment variables:
 *   BINANCE_SQUARE_OPENAPI_KEY - API key from Binance Square Creator Center
 */

import { request as httpsRequest } from 'https';

function parseArgs() {
  const args = process.argv.slice(2);
  const opts = {};
  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--text' && i + 1 < args.length) {
      opts.text = args[i + 1];
      i++;
    }
  }
  return opts;
}

function makeRequest(url, method, headers, body) {
  return new Promise((resolve, reject) => {
    const urlObj = new URL(url);
    const options = {
      hostname: urlObj.hostname,
      port: 443,
      path: urlObj.pathname + urlObj.search,
      method,
      headers,
      timeout: 30000,
    };
    const req = httpsRequest(options, (res) => {
      let data = '';
      res.on('data', (chunk) => { data += chunk; });
      res.on('end', () => {
        resolve({
          status: res.statusCode,
          body: data,
        });
      });
    });
    req.on('error', (err) => reject(err));
    req.on('timeout', () => { req.destroy(); reject(new Error('Request timeout')); });
    if (body) req.write(body);
    req.end();
  });
}

async function main() {
  const opts = parseArgs();
  
  const apiKey = process.env.BINANCE_SQUARE_OPENAPI_KEY;
  if (!apiKey) {
    console.error(JSON.stringify({
      success: false,
      error: 'BINANCE_SQUARE_OPENAPI_KEY environment variable is not set',
    }));
    process.exit(1);
  }

  if (!opts.text) {
    console.error(JSON.stringify({
      success: false,
      error: 'No text provided. Use --text "your post content"',
    }));
    process.exit(1);
  }

  const payload = JSON.stringify({
    contentType: 1,
    bodyTextOnly: opts.text,
  });

  const headers = {
    'X-Square-OpenAPI-Key': apiKey,
    'Content-Type': 'application/json',
    'clienttype': 'binanceSkill',
  };

  try {
    const response = await makeRequest(
      'https://www.binance.com/bapi/composite/v1/public/pgc/openApi/content/add',
      'POST',
      headers,
      payload
    );

    let parsed;
    try {
      parsed = JSON.parse(response.body);
    } catch {
      parsed = { rawBody: response.body };
    }

    const result = {
      success: parsed.code === '000000',
      httpStatus: response.status,
      code: parsed.code,
      message: parsed.message || parsed.messageDetail || null,
      postId: parsed.data?.id || null,
      shareLink: parsed.data?.shareLink || null,
      raw: response.body,
    };

    console.log(JSON.stringify(result));

    if (!result.success) {
      process.exit(2);
    }
  } catch (err) {
    console.error(JSON.stringify({
      success: false,
      error: err.message,
    }));
    process.exit(1);
  }
}

main();
