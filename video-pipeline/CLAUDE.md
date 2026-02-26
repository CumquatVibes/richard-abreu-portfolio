# Video Pipeline — AI Assistant Guide

You are managing an automated YouTube video production pipeline that uses a
Thompson Sampling multi-armed bandit system to optimize video performance
across 38 niche channels.

## How the Bandit System Works

Each channel has multiple "arms" — combinations of:
- Voice profile (neutral_male, storyteller, calm_narrator, friendly_casual, warm_female)
- Script format (listicle, explainer, compilation, shorts_facts, news_recap)
- Thumbnail style (bold_text, clean_minimal, curiosity_gap)

Arm naming convention: `{channel_id}__{voice}__{format}__{thumbnail}`
Example: `richtech__neutral_male__listicle__curiosity_gap`

### Selection (Thompson Sampling)
When producing a video, the system samples from a Beta(alpha, beta) distribution
for each arm. Arms with higher observed rewards get sampled higher on average,
but new/low-pull arms still get explored. The arm with the highest sample wins.

- alpha = (avg_reward × total_pulls) + 1
- beta = ((1 - avg_reward) × total_pulls) + 1

### Reward Function (multi-objective, range: -20 to ~80)
After YouTube Analytics returns data (7d and 28d windows), each video gets a reward:
- Watch time value: 0-20 pts (estimatedMinutesWatched / 100, capped at 1.0)
- Retention: 0-20 pts (averageViewPercentage / 50%, capped at 1.0)
- Engagement: 0-15 pts ((likes + 2×comments + 3×shares) / views / 0.1)
- CTR: 0-10 pts (click-through rate / 10%)
- Subscriber growth: 0-15 pts (net subs / 10)
- Cost penalty: 0 to -10 ($5+ per video = max penalty)
- Risk penalty: 0 to -20 (from preflight compliance scores)

Rewards are normalized to [0,1] for the Beta distribution update.

### Retraining Triggers
The system auto-resets low-pull arms when:
1. Performance drift: recent 5 videos regress >15% vs baseline 20
2. Stale arms: no pulls in 14+ days → reset to uniform prior
3. Copyright incidents: conservative arms get prioritized

### Current State
- 441 arms across 38 channels
- Metrics now flowing from YouTube Analytics API (7d + 28d windows)
- Top performing channels by reward: EvaReyes, RichMusic, HowToUseAI
- Most channels are very new (<50 views) — still in heavy exploration phase

### What You Should Do
1. When producing videos, always use `select_arm(channel_id)` to pick the template
2. After analytics pulls, the system auto-updates arm rewards via `update_arm()`
3. Check `get_arm_report(channel_id)` to see which arms are winning per channel
4. Deactivate consistently underperforming arms with `deactivate_arm(arm_name)`
   only after 10+ pulls with avg_reward < 0.05
5. Never manually override arm selection — let Thompson Sampling explore

## Key Files
- utils/bandits.py — Thompson Sampling implementation
- utils/analytics.py — YouTube Analytics pull + reward computation
- utils/telemetry.py — SQLite DB (output/pipeline.db) with videos, metrics,
  template_arms, decisions tables
- batch_produce.py — Main production orchestrator (calls select_arm)
- run_channel_optimization.sh — Nightly cron that pulls analytics + updates arms

## Cost Tracking
- TTS costs: ElevenLabs $0.30 per 1K characters (Scale tier)
- B-roll costs: Gemini Flash free tier (tracked as $0.00 per call, update if on paid plan)
- Costs are logged per video via `update_costs()` in utils/telemetry.py
- Total pipeline spend so far: ~$499 across 249 videos (~$2.76 avg)
- Weekly digest via `generate_weekly_digest()` in utils/alerts.py

## Rules
- DO NOT spend money (TTS, API calls, uploads) without explicit human approval
- DO NOT deactivate arms with fewer than 10 pulls
- DO NOT reset arm statistics unless a retraining trigger fires
- Let the exploration/exploitation balance happen naturally
