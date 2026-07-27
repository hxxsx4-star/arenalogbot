from datetime import datetime, timezone

import discord
from discord.ext import commands

from utils.logs import VOICE_LOG_CH, is_target_guild

# 감사 로그로 "누가 옮겼는지 / 누가 끊었는지" 추적할 때 인정할 시간 창(초)
_AUDIT_WINDOW_SEC = 6


class VoiceLoggerCog(commands.Cog):
    """음성 채널 입장/퇴장/이동 로그를 기록하는 Cog.

    이동·연결끊김의 경우 감사 로그를 조회해 '실행자'를 함께 기록합니다.
    (디스코드 감사 로그 특성상 대상 유저가 명시되지 않으므로, 짧은 시간 창 내
     해당 액션이 있으면 그 실행자를 표기하는 best-effort 방식입니다.)
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _send_log(self, embed: discord.Embed):
        if not VOICE_LOG_CH:
            return
        await self.bot.wait_until_ready()
        channel = self.bot.get_channel(VOICE_LOG_CH)
        if isinstance(channel, discord.TextChannel):
            if channel.permissions_for(channel.guild.me).send_messages:
                try:
                    await channel.send(embed=embed)
                except Exception as e:
                    print(f"[ERROR] 음성 로그 전송 실패: {e}")
            else:
                print(f"[ERROR] 음성 로그 채널 권한 부족: #{channel.name} ({VOICE_LOG_CH}).")
        else:
            print(f"[ERROR] 음성 로그 채널을 찾을 수 없음: ID {VOICE_LOG_CH}")

    async def _find_actor(self, guild: discord.Guild, action: discord.AuditLogAction,
                          target_id: int = None, change_key: str = None):
        """최근 감사 로그에서 해당 액션의 실행자(다른 사람)를 찾습니다. 없으면 None(본인 행동).

        change_key 를 주면 그 항목이 실제로 바뀐 기록만 인정합니다.
        (member_update 에는 닉네임 변경 등도 섞여 있어, 걸러내지 않으면
         엉뚱한 사람이 '차단한 사람'으로 표시될 수 있습니다.)
        """
        try:
            async for entry in guild.audit_logs(limit=8, action=action):
                if (discord.utils.utcnow() - entry.created_at).total_seconds() > _AUDIT_WINDOW_SEC:
                    break
                # 대상이 명시된 경우(예: member_disconnect 일부)에는 대상 일치 확인
                entry_target_id = getattr(getattr(entry, "target", None), "id", None)
                if entry_target_id is not None and target_id is not None and entry_target_id != target_id:
                    continue
                if change_key is not None:
                    changed = {c.attribute for c in getattr(entry, "changes", [])}
                    if change_key not in changed:
                        continue
                # 실행자가 대상 본인이면 '본인 행동'으로 간주
                if entry.user and entry.user.id == target_id:
                    return None
                return entry.user
        except discord.Forbidden:
            print("[voice audit] 감사 로그 접근 권한이 없습니다. (봇에 '감사 로그 보기' 권한 필요)")
        except Exception as e:
            print(f"[voice audit] 조회 실패: {e}")
        return None

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        if member.bot or not is_target_guild(member.guild):
            return

        # 1) 음성 채널 입장 (본인 행동만 가능)
        if not before.channel and after.channel:
            embed = discord.Embed(
                description=f"➡️ {member.mention} 님이 음성 채널 '{after.channel.name}'에 참여했습니다.",
                color=discord.Color.green(),
                timestamp=datetime.now(timezone.utc),
            )
            embed.set_footer(text=f"유저 ID: {member.id}")
            await self._send_log(embed)

        # 2) 음성 채널 퇴장 (본인 퇴장 or 강제 연결끊김)
        elif before.channel and not after.channel:
            actor = await self._find_actor(member.guild, discord.AuditLogAction.member_disconnect, member.id)
            if actor:
                desc = (
                    f"🔌 {member.mention} 님이 음성 채널 '{before.channel.name}'에서 "
                    f"**연결 끊김** 처리되었습니다.\n실행자: {actor.mention}"
                )
                color = discord.Color.dark_red()
            else:
                desc = f"⬅️ {member.mention} 님이 음성 채널 '{before.channel.name}'에서 나갔습니다."
                color = discord.Color.red()
            embed = discord.Embed(description=desc, color=color, timestamp=datetime.now(timezone.utc))
            embed.set_footer(text=f"유저 ID: {member.id}")
            await self._send_log(embed)

        # 3) 음성 채널 이동 (본인 이동 or 다른 사람이 옮김)
        elif before.channel and after.channel and before.channel != after.channel:
            actor = await self._find_actor(member.guild, discord.AuditLogAction.member_move, member.id)
            if actor:
                desc = (
                    f"↪️ {member.mention} 님이 '{before.channel.name}' → '{after.channel.name}' 로 "
                    f"**이동되었습니다.**\n옮긴 사람: {actor.mention}"
                )
                color = discord.Color.orange()
            else:
                desc = f"↪️ {member.mention} 님이 음성 채널을 '{before.channel.name}'에서 '{after.channel.name}'(으)로 이동했습니다."
                color = discord.Color.blue()
            embed = discord.Embed(description=desc, color=color, timestamp=datetime.now(timezone.utc))
            embed.set_footer(text=f"유저 ID: {member.id}")
            await self._send_log(embed)

        # 4) 같은 채널에 머무르면서 상태만 바뀐 경우
        #    (마이크/헤드셋 끄기, 서버 차단, 화면 공유, 카메라)
        else:
            await self._log_state_change(member, before, after)

    async def _log_state_change(self, member, before, after):
        """음성 상태 변경 로그. 서버 차단(mute/deaf)은 실행자도 함께 찾는다."""
        channel = after.channel or before.channel
        if channel is None:
            return

        # (before, after, 켜졌을 때 문구, 꺼졌을 때 문구, 감사로그 change key)
        # change key 가 None 이면 본인만 할 수 있는 조작(디스코드가 타인 조작을 허용하지 않음)
        checks = [
            (before.self_mute, after.self_mute,
             "🔇 마이크를 껐습니다", "🎙️ 마이크를 켰습니다", None),
            (before.self_deaf, after.self_deaf,
             "🔕 헤드셋(소리)을 껐습니다", "🔔 헤드셋(소리)을 켰습니다", None),
            (before.self_stream, after.self_stream,
             "🖥️ 화면 공유를 시작했습니다", "🖥️ 화면 공유를 종료했습니다", None),
            (before.self_video, after.self_video,
             "📹 카메라를 켰습니다", "📷 카메라를 껐습니다", None),
            (before.mute, after.mute,
             "🚫 서버 마이크가 차단됐습니다", "✅ 서버 마이크 차단이 해제됐습니다", "mute"),
            (before.deaf, after.deaf,
             "🚫 서버 소리가 차단됐습니다", "✅ 서버 소리 차단이 해제됐습니다", "deaf"),
        ]

        for was, now, on_text, off_text, change_key in checks:
            if was == now:
                continue
            text = on_text if now else off_text
            if change_key:
                # 서버 차단/해제는 관리자가 건 것이므로 누가 했는지 찾는다.
                actor = await self._find_actor(
                    member.guild, discord.AuditLogAction.member_update,
                    member.id, change_key=change_key)
                who = actor.mention if actor else "본인"
                color = discord.Color.dark_orange()
            else:
                # 마이크/헤드셋/화면공유/카메라는 본인만 조작할 수 있다.
                who = "본인"
                color = discord.Color.greyple()
            embed = discord.Embed(
                description=f"{text} — {member.mention} (`{channel.name}`)\n실행자: {who}",
                color=color,
                timestamp=datetime.now(timezone.utc),
            )
            embed.set_footer(text=f"유저 ID: {member.id}")
            await self._send_log(embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(VoiceLoggerCog(bot))
