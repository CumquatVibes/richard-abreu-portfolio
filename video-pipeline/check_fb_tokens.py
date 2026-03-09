#!/usr/bin/env python3
"""Check Facebook token health and warn if expiring soon."""
import sys
sys.path.insert(0, ".")
from utils.facebook import check_token_expiry
result = check_token_expiry(warn_days=14)
for k, v in result.items():
    status = v.get("status", "unknown")
    days = v.get("days_left", "N/A")
    print("  %s token: %s (days_left=%s)" % (k, status, days))
