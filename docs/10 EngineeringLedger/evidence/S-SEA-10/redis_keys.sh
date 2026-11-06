#!/bin/sh
# Poll the local stack's Redis for showtime 367's seat locks, one line per poll with a UTC timestamp.
cd "D:/Project/FrontRow/frontrow_aws/.claude/worktrees/agent-aeb2d4b7b2960e43d" || exit 1
OUT="C:/Users/ani87/AppData/Local/Temp/claude/D--Project-FrontRow/d4c8cb4d-bfdd-4164-87cf-a71f5965b831/scratchpad/sea10_keys.log"
: > "$OUT"
i=0
while [ $i -lt 60 ]; do
  i=$((i + 1))
  keys=$(MSYS_NO_PATHCONV=1 docker compose -p frontrow exec -T redis redis-cli KEYS 'lock:seat:367:*' | tr '\n' ' ')
  echo "$(date -u +%H:%M:%S) [$keys]" >> "$OUT"
done
