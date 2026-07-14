import json

import discord
from discord.ext import commands, tasks

from utils.logs import fetch_pending, mark_posted, mark_failed


class LogRelayCog(commands.Cog):
    """공유 로그 큐를 비우며, 다른 봇(펫/메인/내전)이 남긴 로그를 채널에 최종 기록합니다.

    "모든 로그는 로그봇이 작성한다"는 원칙에 따라, 실제 채널 전송은 이 봇에서만 이뤄집니다.
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.drain_queue.start()

    def cog_unload(self):
        self.drain_queue.cancel()

    @tasks.loop(seconds=2)
    async def drain_queue(self):
        try:
            rows = await fetch_pending(30)
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

    @drain_queue.before_loop
    async def before_drain(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(LogRelayCog(bot))
