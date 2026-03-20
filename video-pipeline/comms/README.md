# Mac ↔ PC Communication Protocol

## How it works

Each machine drops JSON task files into `comms/`. The other machine picks them up.

- `comms/mac_to_pc/` — Tasks the Mac needs the PC to do
- `comms/pc_to_mac/` — Tasks the PC needs the Mac to do
- `comms/status/` — Machine-readable status snapshots (auto-generated)

## File naming

`YYYYMMDD_HHMMSS_<short_slug>.json`

## Task schema

```json
{
  "from": "mac",
  "to": "pc",
  "created": "2026-03-20T01:30:00",
  "priority": "high",
  "status": "pending",
  "type": "sync_videos|run_tts|rerender|info|request",
  "subject": "Short description",
  "details": "Full details here",
  "completed_at": null
}
```

## Workflow

1. Sender creates a task file in the appropriate outbox folder
2. Receiver reads pending tasks, acts on them, sets `status: "done"` + `completed_at`
3. Both machines run `sync_comms.py` as part of their nightly cron to:
   - Generate a fresh status snapshot
   - Git commit + push any new/updated comms
   - Pull the other machine's messages

## Status snapshots

`comms/status/mac_status.json` and `comms/status/pc_status.json` are auto-generated
summaries of each machine's pipeline state — DB counts, disk usage, cron health, etc.
These are the single source of truth for "what does the other machine look like right now?"
