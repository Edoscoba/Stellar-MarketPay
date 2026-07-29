/**
 * src/middleware/requestCoalescer.js
 * Cache-stampede protection via single-flight request coalescing (#91).
 *
 * Right after a CDN/origin purge, many concurrent viewers of a popular
 * job/profile page miss the cache at once. Without coalescing, each of
 * those requests independently re-runs the (DB) origin fetch — a "thundering
 * herd" that can overwhelm the database. coalesce() ensures only the first
 * caller for a given key actually runs `fn`; every other concurrent caller
 * for the same key awaits that same in-flight promise and gets its result.
 *
 * Scoped to a single process — sufficient for the origin API tier here,
 * since each instance still only coalesces its own concurrent misses down
 * to one DB query rather than N. For a fleet of origin instances behind a
 * CDN, the CDN's own per-object request collapsing is the outer layer of
 * defense (see docs/CDN_STRATEGY.md).
 */
"use strict";

const inFlight = new Map();

/**
 * @template T
 * @param {string} key
 * @param {() => Promise<T>} fn
 * @returns {Promise<T>}
 */
async function coalesce(key, fn) {
  const existing = inFlight.get(key);
  if (existing) return existing;

  const promise = Promise.resolve()
    .then(() => fn())
    .finally(() => {
      inFlight.delete(key);
    });

  inFlight.set(key, promise);
  return promise;
}

/** Test/metrics hook — number of distinct keys currently in flight. */
function _inFlightCount() {
  return inFlight.size;
}

module.exports = { coalesce, _inFlightCount };
