# main.py — 종합게임 아레나 로그봇
import configparser
import json
import time
import traceback
import urllib.request

import discord
from discord.ext import commands

from utils.logs import ERROR_LOG_CH, init_log_queue

# --- 설정 로드 ---
config = configparser.ConfigParser()
config.read("config.ini", encoding="utf-8")
TOKEN = config.get("Settings", "token", fallback="").strip()
# config.ini 가 없으면 환경변수(DISCORD_TOKEN)에서 토큰을 읽습니다. (도커/CI 배포용)
if not TOKEN:
    import os
    TOKEN = os.environ.get("DISCORD_TOKEN", "").strip()


class LogBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        intents.voice_states = True
        super().__init__(command_prefix=".", intents=intents)

    async def setup_hook(self):
        # 공유 로그 큐 준비 (다른 봇들이 남긴 로그를 이 봇이 최종 기록)
        init_log_queue()
        print("✅ 로그 큐 초기화 완료")

        cogs_to_load = [
            "cogs.log_relay",        # 공유 큐 → 채널 전송 (핵심)
            "cogs.member_tracker",   # 입장/퇴장 로그
            "cogs.message_logger",   # 채팅(수정/삭제) 로그
            "cogs.voice_logger",     # 음성 로그 (이동/연결끊김 실행자 포함)
            "cogs.ban_logger",       # 서버 차단/해제 로그
            "cogs.role_logger",      # 역할 지급/회수 로그 (실행자 포함)
            "cogs.backup",           # 매일 자정 백업 파일 전송
        ]
        for cog in cogs_to_load:
            try:
                await self.load_extension(cog)
                print(f"✅ '{cog}' 로드 성공")
            except Exception as e:
                print(f"❌ '{cog}' 로드 중 오류 발생: {e}")

    async def on_ready(self):
        print("=====================================")
        print(f"🤖 로그봇 로그인 완료: {self.user}")
        print("=====================================")

    async def on_error(self, event_method, *args, **kwargs):
        # 이벤트 핸들러(on_message 등) 내부에서 발생한 예외는 봇을 죽이지 않고
        # 여기로 넘어옵니다. 콘솔에도 남기고, 운영자가 바로 볼 수 있게 디스코드에도 알립니다.
        err_text = traceback.format_exc()
        print(f"🚨 [이벤트 오류: {event_method}]\n{err_text}")
        channel = self.get_channel(ERROR_LOG_CH)
        if channel:
            try:
                await channel.send(
                    f"⚠️ **이벤트 처리 중 오류** (`{event_method}`)\n```py\n{err_text[-1800:]}\n```"
                )
            except Exception as e:
                print(f"🚨 [오류 로그 전송 실패] {e}")


def _report_crash_to_discord(token: str, error_text: str):
    """봇 프로세스 자체가 죽는 크래시는 게이트웨이 연결이 끊긴 상태라
    on_error 로 잡을 수 없습니다. 봇 토큰으로 REST API를 직접 호출해 알립니다."""
    if not ERROR_LOG_CH or not token:
        return
    try:
        content = f"🚨 **로그봇 프로세스가 예기치 않게 종료되었습니다 (자동 재시작 예정)**\n```py\n{error_text[-1800:]}\n```"
        req = urllib.request.Request(
            f"https://discord.com/api/v10/channels/{ERROR_LOG_CH}/messages",
            data=json.dumps({"content": content}).encode("utf-8"),
            headers={
                "Authorization": f"Bot {token}",
                "Content-Type": "application/json",
                # Discord 는 기본 Python-urllib User-Agent 를 403 으로 막는다.
                # 이게 없으면 크래시 알림이 조용히 실패한다.
                "User-Agent": "DiscordBot (https://arenamatch.p-e.kr, 1.0)",
            },
            method="POST",
        )
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        print(f"🚨 [크래시 알림 전송 실패] {e}")


if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit("🚨 토큰이 비어 있습니다. config.ini 파일을 확인하세요.")

    BACKOFF_START = 5
    BACKOFF_MAX = 300
    backoff = BACKOFF_START

    while True:
        bot = LogBot()
        try:
            bot.run(TOKEN)
            # 예외 없이 run()이 끝났다면 close() 등으로 정상 종료된 것 → 재시작하지 않음
            break
        except discord.LoginFailure:
            # 토큰이 잘못된 경우: 재시작해봐야 계속 실패하므로 바로 중단
            print("🚨 로그인 실패: 토큰(config.ini / DISCORD_TOKEN)을 확인하세요.")
            raise
        except Exception:
            err_text = traceback.format_exc()
            print(f"🚨 [봇 종료 - 예외 발생]\n{err_text}")
            _report_crash_to_discord(TOKEN, err_text)
            print(f"⏳ {backoff}초 후 자동 재시작합니다...")
            time.sleep(backoff)
            backoff = min(backoff * 2, BACKOFF_MAX)
            continue
