from datetime import datetime, timezone

import discord
from discord.ext import commands

from utils.logs import ROLE_LOG_CH, is_target_guild

# 감사 로그로 "누가 역할을 주고/뺐는지" 추적할 때 인정할 시간 창(초)
_AUDIT_WINDOW_SEC = 6


class RoleLoggerCog(commands.Cog):
    """멤버의 역할 지급/회수 로그를 기록하는 Cog.

    누가 역할을 주고 뺐는지 감사 로그(member_role_update)를 조회해 함께 기록합니다.
    (감사 로그 접근 권한이 없거나 조회 실패 시 '알 수 없음'으로 표기.)
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _send_log(self, embed: discord.Embed):
        if not ROLE_LOG_CH:
            return
        await self.bot.wait_until_ready()
        channel = self.bot.get_channel(ROLE_LOG_CH)
        if isinstance(channel, discord.TextChannel):
            if channel.permissions_for(channel.guild.me).send_messages:
                try:
                    await channel.send(embed=embed)
                except Exception as e:
                    print(f"[ERROR] 역할 로그 전송 실패: {e}")
            else:
                print(f"[ERROR] 역할 로그 채널 권한 부족: #{channel.name} ({ROLE_LOG_CH}).")
        else:
            print(f"[ERROR] 역할 로그 채널을 찾을 수 없음: ID {ROLE_LOG_CH}")

    async def _find_actor(self, guild: discord.Guild, target_id: int, want_role_id: int, added: bool):
        """member_role_update 감사 로그에서 실행자를 찾습니다. 없으면 None."""
        try:
            async for entry in guild.audit_logs(limit=6, action=discord.AuditLogAction.member_role_update):
                if (discord.utils.utcnow() - entry.created_at).total_seconds() > _AUDIT_WINDOW_SEC:
                    break
                if getattr(getattr(entry, "target", None), "id", None) != target_id:
                    continue
                changed = getattr(entry.after if added else entry.before, "roles", None)
                if changed and any(r.id == want_role_id for r in changed):
                    return entry.user
                # 변경 상세를 못 얻어도 대상/시간이 맞으면 그 실행자로 간주(best-effort)
                return entry.user
        except discord.Forbidden:
            print("[role audit] 감사 로그 접근 권한이 없습니다. (봇에 '감사 로그 보기' 권한 필요)")
        except Exception as e:
            print(f"[role audit] 조회 실패: {e}")
        return None

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if after.bot or not is_target_guild(after.guild):
            return

        before_ids = {r.id for r in before.roles}
        after_ids = {r.id for r in after.roles}
        added = [r for r in after.roles if r.id not in before_ids]
        removed = [r for r in before.roles if r.id not in after_ids]
        if not added and not removed:
            return

        for role in added:
            actor = await self._find_actor(after.guild, after.id, role.id, added=True)
            who = actor.mention if actor else "알 수 없음"
            embed = discord.Embed(
                description=(f"🟢 {after.mention} 님에게 **{role.mention}** 역할이 지급되었습니다.\n"
                             f"지급한 사람: {who}"),
                color=discord.Color.green(),
                timestamp=datetime.now(timezone.utc),
            )
            embed.set_footer(text=f"대상 ID: {after.id}"
                                  + (f" · 실행자 ID: {actor.id}" if actor else ""))
            await self._send_log(embed)

        for role in removed:
            actor = await self._find_actor(after.guild, after.id, role.id, added=False)
            who = actor.mention if actor else "알 수 없음"
            embed = discord.Embed(
                description=(f"🔴 {after.mention} 님의 **{role.mention}** 역할이 회수되었습니다.\n"
                             f"회수한 사람: {who}"),
                color=discord.Color.dark_orange(),
                timestamp=datetime.now(timezone.utc),
            )
            embed.set_footer(text=f"대상 ID: {after.id}"
                                  + (f" · 실행자 ID: {actor.id}" if actor else ""))
            await self._send_log(embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(RoleLoggerCog(bot))
