#!/usr/bin/env bash
# 종합게임 아레나 - 데이터 백업 (stats.json / legends.db / 로그큐)
# cron 예: 0 4 * * * /home/hxxsx4/arena/arenalogbot/scripts/backup.sh >> /home/hxxsx4/arena/backup.log 2>&1
set -euo pipefail

SHARED_DIR="${ARENA_SHARED_DIR:-/home/hxxsx4/shared_data}"
BACKUP_DIR="${ARENA_BACKUP_DIR:-$SHARED_DIR/backups}"
ARENA_ROOT="${ARENA_ROOT:-$HOME/arena}"
KEEP="${ARENA_BACKUP_KEEP:-14}"

mkdir -p "$BACKUP_DIR"
STAMP="$(date +%Y%m%d-%H%M%S)"
DEST="$BACKUP_DIR/arena-$STAMP.tar.gz"

FILES=()
# 포인트(공유)
[ -f "$SHARED_DIR/stats.json" ] && FILES+=("$SHARED_DIR/stats.json")
# 펫/베팅 DB (tmux면 각 리포 폴더, docker면 공유 볼륨)
for db in \
  "$ARENA_ROOT/arenapetbot/legends.db" \
  "$ARENA_ROOT/arenamatchbot/legends.db" \
  "$SHARED_DIR/pet_legends.db" \
  "$SHARED_DIR/match_legends.db"; do
  [ -f "$db" ] && FILES+=("$db")
done
# 저장된 경매 방
[ -d "$SHARED_DIR/auctions" ] && FILES+=("$SHARED_DIR/auctions")
# 추가 경로(콤마 구분)
if [ -n "${ARENA_BACKUP_EXTRA:-}" ]; then
  IFS=',' read -ra EX <<< "$ARENA_BACKUP_EXTRA"
  for p in "${EX[@]}"; do [ -e "$p" ] && FILES+=("$p"); done
fi

if [ ${#FILES[@]} -eq 0 ]; then
  echo "[$(date '+%F %T')] 백업할 파일 없음"; exit 0
fi

tar -czf "$DEST" "${FILES[@]}" 2>/dev/null
echo "[$(date '+%F %T')] 백업 완료: $DEST ($(du -h "$DEST" | cut -f1))"

# 최근 KEEP개만 유지
ls -1t "$BACKUP_DIR"/arena-*.tar.gz 2>/dev/null | tail -n +"$((KEEP+1))" | xargs -r rm -f
