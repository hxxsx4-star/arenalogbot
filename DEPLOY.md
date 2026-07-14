# 배포 가이드 (docker compose)

4개 봇을 한 서버에서 함께 실행합니다. 포인트(`stats.json`)와 로그 큐(`log_queue.db`)를
공유 볼륨으로 묶기 때문에 **반드시 같은 호스트**에서 돌려야 합니다.

## 1) 4개 리포를 나란히 clone
```
mkdir arena && cd arena
git clone <arenalogbot>   ; git clone <arenapetbot>
git clone <arenamatchbot> ; git clone <arenamainbot>
```
```
arena/
 ├─ arenalogbot/   ← docker-compose.yml 여기
 ├─ arenapetbot/
 ├─ arenamatchbot/
 └─ arenamainbot/
```

## 2) 토큰 입력 & 실행
```
cd arenalogbot
cp .env.example .env      # 4개 봇 토큰 입력
docker compose up -d --build
docker compose logs -f    # 로그 확인
```

## 권장 사양 (서버 1개 · 활성 수천 명)
- 권장: **4 vCPU / 8GB RAM / SSD 40GB**
- 최소: 2 vCPU / 4GB
- 단일코어 성능이 중요(이미지 렌더링). 샤딩은 서버 1개라 불필요.

## 참고
- 각 봇은 `DISCORD_TOKEN` 환경변수로 토큰을 받습니다. (config.ini 불필요)
- `ARENA_SHARED_DIR=/data` 공유 볼륨에 stats.json / log_queue.db 저장.
- 펫/내전봇의 sqlite(legends.db)는 `ARENA_DB_PATH`로 각각 분리 저장.
- 로그 큐는 로그봇이 6시간마다 자동 정리(전송 완료 3일 경과분 삭제).
- 단일 프로세스 관리를 systemd로 하고 싶으면 각 봇 폴더에서 `python main.py`를
  유닛으로 등록해도 됩니다. (compose가 더 간단)
