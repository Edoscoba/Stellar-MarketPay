/**
 * scripts/load-test/stampede-k6.js
 *
 * Simulates the cache-stampede scenario from #91: a popular job page gets
 * purged (on-chain event fires), then a burst of concurrent viewers all
 * miss the cache at once. Verifies the origin absorbs the spike without a
 * proportional spike in DB load — i.e. that request coalescing
 * (backend/src/middleware/requestCoalescer.js) is doing its job.
 *
 * Usage:
 *   1. Note the job id you're about to hammer, e.g. JOB_ID=job-1
 *   2. Trigger (or simulate) its invalidation: POST /api/cdn/webhook with
 *      { "eventType": "escrow_released", "jobId": "job-1" }, or just wait
 *      for the natural 30s edge TTL to lapse.
 *   3. Immediately run this script against the same job id:
 *        k6 run -e BASE_URL=https://app.example.com -e JOB_ID=job-1 scripts/load-test/stampede-k6.js
 *
 * Expected outcome (see docs/CDN_STRATEGY.md#stampede-protection): despite
 * hundreds of concurrent requests arriving in the same instant, backend
 * DB query volume for that job should stay flat — check
 * marketpay_db_connections and request latency don't spike proportionally
 * to VU count. A regression here (latency scaling with VUs) means
 * coalescing broke.
 */
import http from "k6/http";
import { check } from "k6";

const BASE_URL = __ENV.BASE_URL || "http://localhost:4000";
const JOB_ID = __ENV.JOB_ID || "job-1";

export const options = {
  scenarios: {
    post_invalidation_spike: {
      executor: "shared-iterations",
      vus: 300,
      iterations: 300,
      maxDuration: "20s",
    },
  },
  thresholds: {
    // If coalescing works, latency should stay close to a single origin
    // fetch's latency even at 300 concurrent VUs — not scale linearly.
    http_req_duration: ["p(99)<1000"],
    http_req_failed: ["rate<0.01"],
  },
};

export default function stampedeScenario() {
  const res = http.get(`${BASE_URL}/api/jobs/${JOB_ID}`, { tags: { name: "job_detail_stampede" } });
  check(res, {
    "status is 200 or 404": (r) => r.status === 200 || r.status === 404,
    "did not error under load": (r) => r.status < 500,
  });
}
