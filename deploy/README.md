# 배포/운영 (안정성)

VM(우분투)에서 4개 봇 + 경매 웹을 **자동 재시작(systemd)** 으로 돌리고,
데이터를 **자동 백업**하는 방법입니다. (지금의 tmux 수동 실행을 대체)

전제: 리포들이 `~/arena/` 아래에 있음 (`~/arena/arenalogbot`, `arenapetbot`, ...).
사용자명은 `hxxsx4` 기준. 다르면 아래 파일들의 `hxxsx4` 경로/User 를 바꾸세요.

---

## 1) systemd 자동 재시작 (부팅/크래시 자동 복구)

### ⚠️ 먼저 tmux에서 돌던 봇/웹을 모두 종료하세요 (중복 실행 방지)
tmux 안에서 각 `python main.py` / `uvicorn` 을 `Ctrl+C` 로 끄거나, `tmux kill-server`.

### 설치
```bash
cd ~/arena/arenalogbot

# 유닛 설치
sudo cp deploy/systemd/arena-*.service /etc/systemd/system/

# 경매 웹 환경변수 파일
sudo mkdir -p /etc/arena
sudo cp deploy/systemd/auctionweb.env.example /etc/arena/auctionweb.env
sudo nano /etc/arena/auctionweb.env      # 토큰/도메인/시크릿 채우기

# 적용 + 부팅시 자동시작 + 지금 켜기
sudo systemctl daemon-reload
sudo systemctl enable --now arena-logbot arena-petbot arena-matchbot arena-mainbot arena-auctionweb
```

### 관리
```bash
sudo systemctl status arena-petbot        # 상태
journalctl -u arena-petbot -f             # 실시간 로그
sudo systemctl restart arena-mainbot      # 재시작
sudo systemctl stop arena-auctionweb      # 정지

# 코드 업데이트 후:
cd ~/arena/arenapetbot && git pull && sudo systemctl restart arena-petbot
```

> 봇 토큰: 각 봇은 리포 폴더의 `config.ini` 를 읽습니다(그대로 사용).
> 경매 웹만 `/etc/arena/auctionweb.env` 의 값을 사용합니다.

---

## 2) 데이터 자동 백업

`stats.json`(포인트), `legends.db`(펫/베팅), 저장된 경매 방을 매일 백업합니다.

### 수동 실행 (테스트)
```bash
~/arena/arenalogbot/scripts/backup.sh
ls ~/shared_data/backups/       # arena-YYYYMMDD-HHMMSS.tar.gz
```

### 매일 자동 (cron)
```bash
crontab -e
```
맨 아래에 추가 (매일 새벽 4시):
```
0 4 * * * /home/hxxsx4/arena/arenalogbot/scripts/backup.sh >> /home/hxxsx4/arena/backup.log 2>&1
```

- 백업 위치: `~/shared_data/backups/` (환경변수 `ARENA_BACKUP_DIR` 로 변경 가능)
- 보관 개수: 최근 14개 (`ARENA_BACKUP_KEEP`)
- 추가 파일 백업: `ARENA_BACKUP_EXTRA=/경로1,/경로2`

### 복구
```bash
tar -xzf ~/shared_data/backups/arena-YYYYMMDD-HHMMSS.tar.gz -C /
```
(봇 정지 후 복구 → 재시작 권장)

---

## 참고: 경매 재시작 복구
경매 웹은 진행 중인 경매를 `~/shared_data/auctions/` 에 저장해서,
재시작/크래시해도 **진행 상태(입찰·포인트·순서)가 복구**됩니다. (별도 설정 불필요)
