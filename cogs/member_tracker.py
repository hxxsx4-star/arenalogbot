import discord
from discord.ext import commands
from datetime import datetime

from utils.logs import JOIN_LOG_CH, LEAVE_LOG_CH


class MemberTrackerCog(commands.Cog):
    """서버 멤버 입장 및 퇴장 로그를 기록하는 Cog"""
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _send_log(self, channel_id: int, embed: discord.Embed):
        if not channel_id:
            return

        await self.bot.wait_until_ready()

        channel = self.bot.get_channel(channel_id)
        if isinstance(channel, discord.TextChannel):
            try:
                await channel.send(embed=embed)
            except discord.Forbidden:
                print(f"[ERROR] 멤버 로그 채널 권한 부족: #{channel.name}")
            except Exception as e:
                print(f"[ERROR] 멤버 로그 전송 실패: {e}")
        else:
            print(f"[ERROR] 멤버 로그 채널을 찾을 수 없음: ID {channel_id}")

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """멤버가 서버에 들어왔을 때 로그를 기록합니다."""
        embed = discord.Embed(
            title="👋 멤버 입장",
            description=f"{member.mention} ({member.name}) 님이 서버에 입장하셨습니다!",
            color=discord.Color.green(),
            timestamp=datetime.now()
        )
        if member.display_avatar:
            embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_footer(text=f"유저 ID: {member.id}")

        await self._send_log(JOIN_LOG_CH, embed)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        """멤버가 서버를 나갔을 때(추방 포함) 로그를 기록합니다."""
        embed = discord.Embed(
            title="👣 멤버 퇴장",
            description=f"{member.mention} ({member.name}) 님이 서버를 나갔습니다.",
            color=discord.Color.dark_grey(),
            timestamp=datetime.now()
        )
        if member.display_avatar:
            embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_footer(text=f"유저 ID: {member.id}")

        await self._send_log(LEAVE_LOG_CH, embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(MemberTrackerCog(bot))
