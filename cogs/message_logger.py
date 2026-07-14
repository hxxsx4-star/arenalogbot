import discord
from discord.ext import commands

from utils.logs import CHAT_LOG_CH


class MessageLoggerCog(commands.Cog):
    """메시지 수정/삭제(채팅) 로그를 기록하는 Cog"""
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _send_log(self, embed: discord.Embed):
        """지정된 채널로 로그 임베드를 전송하는 헬퍼 함수"""
        if not CHAT_LOG_CH:
            return
        await self.bot.wait_until_ready()
        channel = self.bot.get_channel(CHAT_LOG_CH)

        if isinstance(channel, discord.TextChannel):
            if channel.permissions_for(channel.guild.me).send_messages:
                try:
                    await channel.send(embed=embed)
                except Exception as e:
                    print(f"[ERROR] Failed to send message log: {e}")
            else:
                print(f"[ERROR] No 'Send Messages' permission in channel #{channel.name} ({CHAT_LOG_CH}).")
        else:
            print(f"[ERROR] Channel with ID {CHAT_LOG_CH} not found or is not a text channel.")

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        # 봇의 메시지가 삭제된 경우 무시
        if message.author.bot:
            return

        embed = discord.Embed(
            description=f"🗑️ **{message.author.mention}** 님이 {message.channel.mention}에서 메시지를 삭제했습니다.",
            color=discord.Color.red(),
            timestamp=discord.utils.utcnow()
        )

        # 삭제된 메시지 내용 (최대 1024자 제한 안전장치)
        content = message.content or "내용 없음 (사진/파일/스티커 등)"
        if len(content) > 1024:
            content = content[:1020] + "..."

        embed.add_field(name="삭제된 내용", value=content, inline=False)

        # 첨부파일이 있었을 경우 파일 URL 기록
        if message.attachments:
            attachments = "\n".join([att.url for att in message.attachments])
            if len(attachments) > 1024:
                attachments = attachments[:1020] + "..."
            embed.add_field(name="첨부파일", value=attachments, inline=False)

        embed.set_footer(text=f"User ID: {message.author.id}")
        await self._send_log(embed)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        # 봇의 메시지가 수정된 경우 무시
        if before.author.bot:
            return

        # 디스코드는 임베드가 생성되거나 링크 미리보기가 뜰 때도 edit 이벤트를 발생시킵니다.
        # 따라서 메시지 내용(content)이 실제로 변경되었을 때만 처리합니다.
        if before.content == after.content:
            return

        embed = discord.Embed(
            description=f"✏️ **{before.author.mention}** 님이 {before.channel.mention}에서 [메시지를 수정]({after.jump_url})했습니다.",
            color=discord.Color.orange(),
            timestamp=discord.utils.utcnow()
        )

        before_content = before.content or "내용 없음"
        after_content = after.content or "내용 없음"

        # 수정 전/후 내용 (최대 1024자 제한 안전장치)
        if len(before_content) > 1024:
            before_content = before_content[:1020] + "..."
        if len(after_content) > 1024:
            after_content = after_content[:1020] + "..."

        embed.add_field(name="수정 전", value=before_content, inline=False)
        embed.add_field(name="수정 후", value=after_content, inline=False)
        embed.set_footer(text=f"User ID: {before.author.id}")

        await self._send_log(embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(MessageLoggerCog(bot))
