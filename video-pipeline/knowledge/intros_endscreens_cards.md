# Automating Intros, End Screens, and Cards for 37 Faceless YouTube Channels

## Research Date: February 23, 2026

---

## KEY TAKEAWAYS

### What CAN Be Automated (Render-Time)
- Intro generation (0.5-4s branded bumpers)
- Outro background segment (clean 20s segment for end screen overlay)
- Audio stingers (TTS/recorded voice + audio sting)
- Video rendering with intro/outro appended

### What CANNOT Be Automated via API
- End screens (must be added in YouTube Studio)
- Info cards (must be added in YouTube Studio)
- YouTube Data API has NO endpoints for end screen/card editing

### What CAN Be Measured via API
- `end_screen_element_impressions`, `end_screen_element_clicks`, `end_screen_element_click_rate`
- `cardImpressions`, `cardClicks`, `cardClickRate`
- Traffic source `END_SCREEN` for tracking referral views
- Audience retention via `elapsedVideoTimeRatio` (100 data points)

---

## PLATFORM CONSTRAINTS

### End Screens
- Last 5-20 seconds of video only
- Max 4 elements (16:9 aspect ratio)
- Video must be >= 25 seconds
- Suppresses card teasers and watermarks while shown
- NOT available for "made for kids" videos
- Elements: subscribe, video (best for viewer/most recent/specific), playlist, channel, link

### Info Cards
- Max 5 cards per video
- Each card has a start time
- Types: video, playlist, channel, link
- NOT available for "made for kids" videos
- May not show if Content ID claim + campaign active

---

## INTRO DESIGN FOR FACELESS CHANNELS

### Three Variants
1. **Micro-intro (0.5-1.5s)**: Logo animation + audio sting
2. **Short branded bumper (2-4s)**: Brand colors + tagline + motion background
3. **Voice stinger (3-5s)**: Single sentence TTS + sting

### Per-Channel Branding
Each channel needs:
- Logo animation (consistent style, different colors per channel)
- Audio sting (can be shared or channel-specific)
- Color palette matching channel brand
- Tagline/catch phrase

---

## END SCREEN STRATEGY (Per Video)

### Default Layout
- Element A: **Subscribe** button
- Element B: **Best for viewer** OR **Most recent upload**
- Element C: **Pinned playlist** matching video topic
- Element D (optional): Cross-channel promo

### Timing
- Stagger elements (subscribe at 5s from end, playlist at 10s, best-for-viewer throughout)
- Always render 20-second clean outro with CTA audio

---

## CARD STRATEGY (Per Video)

### Default Pattern
- Card 1 (early, 5-15% of video): "Basics playlist" or "Start here"
- Card 2 (mid, 40-60%): "Most related video" when topic changes
- Card 3 (late, 70-85%): "Next episode" or "Deep dive"

### Content ID Risk
- If video likely to get Content ID claims, reduce card reliance
- Shift CTA emphasis to end screens and audio prompts

---

## ARCHITECTURE FOR 37 CHANNELS

### Two-Layer System
1. **Automated render layer**: Generate intro/outro, embed in video file
2. **Semi-automated interactive layer**: Generate VideoElementsPlan JSON → human applies in Studio

### Data Model
```
ChannelConfig:
  - channel_id, brand_id, intro_policy, outro_policy
  - end_screen_strategy: {layout, use_best_for_viewer, include_subscribe, pinned_playlist}
  - card_strategy: {max_cards, trigger_model, allowed_types}
  - cross_promo_policy: allowlist/denylist

VideoElementsPlan (per video):
  - endscreen: [up to 4 elements with timing]
  - cards: [up to 5 cards with start times]
  - targets: referenced video/playlist/channel IDs
  - eligibility_checks: {duration_ok, made_for_kids_ok, content_id_risk}
```

---

## QUOTA IMPACT

| Operation | Quota Cost |
|-----------|-----------|
| videos.update | 50 |
| thumbnails.set | 50 |
| playlistItems.insert/update/delete | 50 |
| playlists.insert/update/delete | 50 |
| videos.insert | 100 |
| watermarks.set/unset | 50 |

Daily limit: 10,000 units. End screen/card changes have ZERO quota cost (Studio only).

---

## PHASED IMPLEMENTATION

| Phase | Milestones | Effort |
|-------|-----------|--------|
| 1. Foundations | Config schema, asset manifest, quota scheduler, analytics ingestion | 4-8 weeks |
| 2. Intro MVP | FFmpeg render pipeline, intro/outro templates, retention measurement | 6-10 weeks |
| 3. End Screen Planning | Planner + HITL queue + Studio checklist | 6-12 weeks |
| 4. Card Planning | Card planner + transcript triggers + Content ID warnings | 6-12 weeks |
| 5. Multi-tenant | Per-channel overrides, cross-promo governance, token rotation | 6-14 weeks |
| 6. Optimization | Bandit learning, intro variant testing, automated playbook updates | 4-10 weeks |

---

## IMMEDIATE ACTIONS FOR OUR PIPELINE

1. Create branded intro templates (logo + audio sting) for each channel
2. Add 20-second clean outro segment to all new videos
3. Generate VideoElementsPlan JSON during upload
4. Build Studio application checklist for manual end screen/card setup
5. Track end screen/card metrics via Analytics API for optimization
