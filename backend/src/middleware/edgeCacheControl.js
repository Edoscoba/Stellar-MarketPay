/**
 * src/middleware/edgeCacheControl.js
 * Sets Cache-Control + Surrogate-Key/Cache-Tag headers per content-type tier
 * so the CDN edge (Fastly reads Surrogate-Key, Cloudflare Enterprise reads
 * Cache-Tag) knows both how long to cache a response and which tag(s) to
 * drop it under during a targeted purge (#91).
 *
 * See services/cdn/cacheStrategy.js for the TTL/content-type definitions.
 */
"use strict";

const { CONTENT_TYPES, cacheControlFor } = require("../services/cdn/cacheStrategy");

/**
 * @param {string} type one of CONTENT_TYPES
 * @param {{ surrogateKeys?: string[] | ((req: import('express').Request) => string[]) }} [opts]
 */
function edgeCacheControl(type, { surrogateKeys } = {}) {
  return (req, res, next) => {
    res.set("Cache-Control", cacheControlFor(type));

    const keys = typeof surrogateKeys === "function" ? surrogateKeys(req) : surrogateKeys;
    if (keys && keys.length) {
      res.set("Surrogate-Key", keys.join(" "));
      res.set("Cache-Tag", keys.join(","));
    }
    next();
  };
}

module.exports = { edgeCacheControl, CONTENT_TYPES };
