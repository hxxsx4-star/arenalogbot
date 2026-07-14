import json

import discord
from discord.ext import commands, tasks

from utils.logs import fetch_pending, mark_posted, mark_failed, purge_posted

# 한 번에 처리할 로그 수 (초당 처리량 = BATCH / 루프주기)
DRAIN_BATCH = 100
# 정리: 전송 완료 후 이 시간(초)이 지난 로그는 큐에서 삭제 (기본 3일)
PURGE_OLDER_THAN_SEC = 3 * 24 * 3600


class LogRelayCog(commands.Cog):
    """공유 로그 큐를 비우며, 다른 봇(펫/메인/내전)이 남긴 로그를 채널에 최종 기록합니다.

    "모든 로그는 로그봇이 작성한다"는 원칙에 따라, 실제 채널 전송은 이 봇에서만 이뤄집니다.
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.drain_queue.start()
        self.cleanup_queue.start()

    def cog_unload(self):
        self.drain_queue.cancel()
        self.cleanup_queue.cancel()

    @tasks.loop(seconds=1.5)
    async def drain_queue(self):
        try:
            rows = await fetch_pending(DRAIN_BATCH)
        except Exception as e:
            print(f"🚨 로그 큐 조회 실패: {e}")
            return

        posted, failed = [], []
        for row in rows:
            row_id, channel_id, embed_json = row["id"], row["channel_id"], row["embed_json"]
            try:
                channel = self.bot.get_channel(channel_id) or await self.bot.fetch_channel(channel_id)
                if channel is None:
                    failed.append(row_id)
                    continue
                embed = discord.Embed.from_dict(json.loads(embed_json))
                await channel.send(embed=embed)
                posted.append(row_id)
            except Exception as e:
                print(f"🚨 로그 릴레이 실패 (id={row_id}, ch={channel_id}): {e}")
                failed.append(row_id)

        await mark_posted(posted)
        await mark_failed(failed)

    @tasks.loop(hours=6)
    async def cleanup_queue(self):
        """큐 DB가 무한정 커지지 않도록 오래된(전송 완료) 로그를 주기적으로 정리."""
        try:
            # 하루 한 번꼴(매 4번째 실행)로만 VACUUM 실행해 파일 크기까지 회수
            do_vacuum = (getattr(self, "_cleanup_ticks", 0) % 4) == 0
            self._cleanup_ticks = getattr(self, "_cleanup_ticks", 0) + 1
            deleted = await purge_posted(PURGE_OLDER_THAN_SEC, vacuum=do_vacuum)
            if deleted:
                print(f"🧹 로그 큐 정리: {deleted}건 삭제 (vacuum={do_vacuum})")
        except Exception as e:
            print(f"🚨 로그 큐 정리 실패: {e}")

    @drain_queue.before_loop
    async def before_drain(self):
        await self.bot.wait_until_ready()

    @cleanup_queue.before_loop
    async def before_cleanup(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(LogRelayCog(bot))
