from datetime import datetime, timezone

import discord
from discord.ext import commands

from utils.logs import BAN_LOG_CH, is_target_guild

_AUDIT_WINDOW_SEC = 8


class BanLoggerCog(commands.Cog):
    """서버 차단(밴)/차단 해제 로그를 기록하는 Cog.

    누가 차단했는지/사유는 감사 로그에서 조회합니다.
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _send(self, embed: discord.Embed):
        if not BAN_LOG_CH:
            return
        await self.bot.wait_until_ready()
        channel = self.bot.get_channel(BAN_LOG_CH)
        if isinstance(channel, discord.TextChannel):
            try:
                await channel.send(embed=embed)
            except Exception as e:
                print(f"[ERROR] 차단 로그 전송 실패: {e}")
        else:
            print(f"[ERROR] 차단 로그 채널을 찾을 수 없음: ID {BAN_LOG_CH}")

    async def _find_audit(self, guild: discord.Guild, action: discord.AuditLogAction, target_id: int):
        """최근 감사 로그에서 대상에 대한 실행자/사유를 찾습니다."""
        try:
            async for entry in guild.audit_logs(limit=5, action=action):
                if (discord.utils.utcnow() - entry.created_at).total_seconds() > _AUDIT_WINDOW_SEC:
                    break
                tid = getattr(getattr(entry, "target", None), "id", None)
                if tid == target_id:
                    return entry.user, entry.reason
        except discord.Forbidden:
            print("[ban audit] 감사 로그 접근 권한이 없습니다.")
        except Exception as e:
            print(f"[ban audit] 조회 실패: {e}")
        return None, None

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User):
        if not is_target_guild(guild):
            return
        actor, reason = await self._find_audit(guild, discord.AuditLogAction.ban, user.id)
        embed = discord.Embed(
            title="🔨 서버 차단",
            description=f"{user.mention} ({user}) 님이 서버에서 차단되었습니다.",
            color=discord.Color.dark_red(),
            timestamp=datetime.now(timezone.utc),
        )
        if getattr(user, "display_avatar", None):
            embed.set_thumbnail(url=user.display_avatar.url)
        embed.add_field(name="실행자", value=actor.mention if actor else "알 수 없음", inline=True)
        embed.add_field(name="사유", value=reason or "사유 미기재", inline=False)
        embed.set_footer(text=f"유저 ID: {user.id}")
        await self._send(embed)

    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User):
        if not is_target_guild(guild):
            return
        actor, reason = await self._find_audit(guild, discord.AuditLogAction.unban, user.id)
        embed = discord.Embed(
            title="♻️ 차단 해제",
            description=f"{user.mention} ({user}) 님의 서버 차단이 해제되었습니다.",
            color=discord.Color.green(),
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(name="실행자", value=actor.mention if actor else "알 수 없음", inline=True)
        embed.set_footer(text=f"유저 ID: {user.id}")
        await self._send(embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(BanLoggerCog(bot))
