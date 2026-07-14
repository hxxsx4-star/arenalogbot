# main.py — 종합게임 아레나 로그봇
import configparser

import discord
from discord.ext import commands

from utils.logs import init_log_queue

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


if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit("🚨 토큰이 비어 있습니다. config.ini 파일을 확인하세요.")
    bot = LogBot()
    bot.run(TOKEN)
