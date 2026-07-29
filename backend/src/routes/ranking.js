/**
 * ML ranking API routes — predictive match recommendations for jobs and freelancers.
 */
"use strict";

const express = require("express");
const router = express.Router();
const { createRateLimiter } = require("../middleware/rateLimiter");
const {
  getRankedJobsForFreelancer,
  getRankedFreelancersForJob,
  getShadowModeStats,
  runFairnessAudit,
  CONFIG,
} = require("../services/mlRankingService");

const rankingRateLimiter = createRateLimiter(60, 1);

/**
 * @openapi
 * /api/ranking/jobs/{publicKey}:
 *   get:
 *     summary: ML-ranked job recommendations for a freelancer
 *     tags: [Ranking]
 *     parameters:
 *       - in: path
 *         name: publicKey
 *         required: true
 *         schema: { type: string }
 *       - in: query
 *         name: limit
 *         schema: { type: integer, default: 10 }
 *     responses:
 *       200:
 *         description: Ranked open jobs with match scores and cold-start fallback metadata
 */
router.get("/jobs/:publicKey", rankingRateLimiter, async (req, res, next) => {
  try {
    const limit = req.query.limit ? Number(req.query.limit) : undefined;
    const result = await getRankedJobsForFreelancer(req.params.publicKey, limit);
    res.json({ success: true, data: result.data, meta: result.meta });
  } catch (e) {
    next(e);
  }
});

/**
 * @openapi
 * /api/ranking/freelancers/{jobId}:
 *   get:
 *     summary: ML-ranked freelancer recommendations for a job
 *     tags: [Ranking]
 */
router.get("/freelancers/:jobId", rankingRateLimiter, async (req, res, next) => {
  try {
    const limit = req.query.limit ? Number(req.query.limit) : undefined;
    const result = await getRankedFreelancersForJob(req.params.jobId, limit);
    res.json({ success: true, data: result.data, meta: result.meta });
  } catch (e) {
    next(e);
  }
});

router.get("/health", (_req, res) => {
  res.json({
    success: true,
    data: {
      enabled: CONFIG.enabled,
      shadowMode: CONFIG.shadowMode,
      latencyBudgetMs: CONFIG.latencyBudgetMs,
      coldStartMinHistory: CONFIG.coldStartMinHistory,
      explorationBudget: CONFIG.explorationBudget,
    },
  });
});

router.get("/shadow-stats", rankingRateLimiter, async (_req, res, next) => {
  try {
    const stats = await getShadowModeStats();
    res.json({ success: true, data: stats });
  } catch (e) {
    next(e);
  }
});

router.get("/fairness-audit", rankingRateLimiter, async (_req, res, next) => {
  try {
    const audit = await runFairnessAudit();
    res.json({ success: true, data: audit });
  } catch (e) {
    next(e);
  }
});

module.exports = router;
