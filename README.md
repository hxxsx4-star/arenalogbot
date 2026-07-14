# arenalogbot

종합게임 아레나 **로그봇**.

모든 로그(입장/퇴장/채팅/음성 + 다른 봇들이 남긴 내전·포인트·펫·아이템·상점 로그)를
이 봇이 유일하게 채널에 기록합니다.

- `cogs/member_tracker.py` : 입장/퇴장 로그
- `cogs/message_logger.py` : 채팅(수정/삭제) 로그
- `cogs/voice_logger.py`   : 음성 로그 (이동/연결끊김 실행자 포함)
- `cogs/log_relay.py`      : 공유 로그 큐를 비워 다른 봇들의 로그를 채널에 전송
- `utils/logs.py`          : 4개 봇이 공유하는 로그 채널 ID + 공유 큐 API

## 실행
```
cp config.ini.example config.ini   # 토큰 입력
pip install -r requirements.txt
python main.py
```
