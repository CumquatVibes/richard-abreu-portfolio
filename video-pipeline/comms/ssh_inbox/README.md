# SSH Inbox — PC Drops Files Here Directly

The PC writes task/status files here via SSH. No git round-trip needed.

## How the PC sends a message:

```bash
# One-liner from PC:
ssh richardabreu@<mac-ip> "cat > ~/Projects/RichardAbreuPortfolio/video-pipeline/comms/ssh_inbox/$(date +%Y%m%d_%H%M%S)_task.json" << 'EOF'
{
  "from": "pc",
  "to": "mac",
  "created": "2026-04-05T12:00:00",
  "priority": "high",
  "type": "info",
  "subject": "TTS batch complete",
  "details": "All 374 scripts voiced. Ready for video production."
}
EOF

# Or use scp:
scp task.json richardabreu@<mac-ip>:~/Projects/RichardAbreuPortfolio/video-pipeline/comms/ssh_inbox/

# Or quick status update:
ssh richardabreu@<mac-ip> "echo 'TTS done, 374 scripts voiced' > ~/Projects/RichardAbreuPortfolio/video-pipeline/comms/ssh_inbox/$(date +%Y%m%d_%H%M%S)_status.txt"
```

## Mac reads it:
```bash
python sync_comms.py --check-ssh
```

The Mac cron checks this folder every sync cycle (7:30 AM ET).
Files are moved to pc_to_mac/ after processing.
