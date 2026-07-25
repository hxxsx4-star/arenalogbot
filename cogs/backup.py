"""매일 자정(KST) 데이터 백업을 디스코드 채널로 전송.

디스크 절약 설계:
  · 백업 파일을 서버에 남기지 않는다. 임시 파일로 만들어 업로드 후 즉시 삭제.
    (보관은 디스코드 채널이 담당 → VM 디스크 사용량 0)
  · 다시 받을 수 있는 캐시(티어 아이콘, 챔피언 목록, __pycache__)는 제외.
  · tar.gz 최대 압축으로 전송 용량 최소화.
  · 예전 backup.sh 가 남긴 로컬 백업 폴더가 있으면 오래된 것부터 정리.
"""
import os
import shutil
import tarfile
import tempfile
import datetime

import discord
from discord.ext import commands, tasks
from discord import app_commands

BACKUP_CH = 1530505019684552714          # 백업 파일 전송 채널
KST = datetime.timezone(datetime.timedelta(hours=9))
BACKUP_TIME = datetime.time(hour=0, minute=0, tzinfo=KST)   # 매일 자정(KST)

SHARED_DIR = os.environ.get("ARENA_SHARED_DIR", "/home/hxxsx4/shared_data")
ARENA_ROOT = os.environ.get("ARENA_ROOT", os.path.expanduser("~/arena"))

# 재다운로드 가능하거나 불필요한 항목은 백업에서 제외 (용량 절약)
EXCLUDE_NAMES = {"tier_icons", "champions.json", "__pycache__", "backups", "venv"}
EXCLUDE_SUFFIX = (".lock", ".tmp", ".pyc", "-wal", "-shm")

# 로컬에 남아있는 예전 백업을 이 개수만 유지 (0 = 전부 삭제)
LOCAL_BACKUP_KEEP = 0


def _human(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.1f}{unit}" if unit != "B" else f"{n}B"
        n /= 1024
    return f"{n:.1f}GB"


def _skip(path: str) -> bool:
    base = os.path.basename(path)
    return base in EXCLUDE_NAMES or base.endswith(EXCLUDE_SUFFIX)


def _collect() -> list:
    """백업 대상 경로 목록."""
    targets = []
    # 공유 데이터 (포인트/레벨/닉네임 등 — 가장 중요)
    p = os.path.join(SHARED_DIR, "stats.json")
    if os.path.isfile(p):
        targets.append(p)
    # 사이트 데이터 (경기 기록/소환사/일정/내기/인증)
    p = os.path.join(SHARED_DIR, "arena_site")
    if os.path.isdir(p):
        targets.append(p)
    # 저장된 경매
    p = os.path.join(SHARED_DIR, "auctions")
    if os.path.isdir(p):
        targets.append(p)
    # 봇 DB (펫/예측 등)
    for repo in ("arenapetbot", "arenamatchbot", "arenamainbot"):
        for db in ("legends.db", "predictions.db"):
            p = os.path.join(ARENA_ROOT, repo, db)
            if os.path.isfile(p):
                targets.append(p)
    return targets


def _make_archive(tmp_path: str) -> tuple:
    """대상들을 tar.gz 로 묶고 (파일수, 원본크기) 반환."""
    count = total = 0

    def _filter(info: tarfile.TarInfo):
        nonlocal count, total
        if _skip(info.name):
            return None
        if info.isfile():
            count += 1
            total += info.size
        return info

    with tarfile.open(tmp_path, "w:gz", compresslevel=9) as tar:
        for path in _collect():
            if _skip(path):
                continue
            tar.add(path, arcname=os.path.relpath(path, os.path.dirname(SHARED_DIR)),
                    filter=_filter)
    return count, total


def _cleanup_local_backups() -> int:
    """예전 backup.sh 가 남긴 로컬 백업 정리 (디스크 회수). 삭제 바이트 반환."""
    bdir = os.path.join(SHARED_DIR, "backups")
    if not os.path.isdir(bdir):
        return 0
    try:
        files = sorted(
            (os.path.join(bdir, f) for f in os.listdir(bdir) if f.endswith(".tar.gz")),
            key=os.path.getmtime, reverse=True)
    except OSError:
        return 0
    freed = 0
    for f in files[LOCAL_BACKUP_KEEP:]:
        try:
            freed += os.path.getsize(f)
            os.remove(f)
        except OSError:
            pass
    return freed


class BackupCog(commands.Cog):
    """매일 자정 백업 파일을 지정 채널로 전송."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.daily_backup.start()

    def cog_unload(self):
        self.daily_backup.cancel()

    @tasks.loop(time=BACKUP_TIME)
    async def daily_backup(self):
        await self.run_backup()

    @daily_backup.before_loop
    async def _before(self):
        await self.bot.wait_until_ready()

    async def run_backup(self, manual_by: str = None) -> str:
        """백업 생성 → 채널 업로드 → 임시 파일 즉시 삭제. 결과 요약 문자열 반환."""
        channel = self.bot.get_channel(BACKUP_CH)
        if channel is None:
            msg = f"[백업] 채널({BACKUP_CH})을 찾을 수 없습니다."
            print(msg)
            return msg

        freed = _cleanup_local_backups()
        stamp = datetime.datetime.now(KST).strftime("%Y%m%d-%H%M")
        tmp_path = None
        try:
            fd, tmp_path = tempfile.mkstemp(prefix=f"arena-{stamp}-", suffix=".tar.gz")
            os.close(fd)
            count, raw = _make_archive(tmp_path)
            size = os.path.getsize(tmp_path)

            if count == 0:
                await channel.send("⚠️ 백업할 데이터를 찾지 못했습니다. (경로 설정 확인 필요)")
                return "백업 대상 없음"

            limit = getattr(channel.guild, "filesize_limit", 8 * 1024 * 1024)
            usage = shutil.disk_usage("/")
            desc = (f"파일 **{count}개** · 원본 {_human(raw)} → 압축 **{_human(size)}**\n"
                    f"디스크: {_human(usage.used)} / {_human(usage.total)} "
                    f"(여유 {_human(usage.free)})")
            if freed:
                desc += f"\n🧹 오래된 로컬 백업 {_human(freed)} 정리"

            embed = discord.Embed(
                title="💾 자동 백업" + (f" (수동 실행: {manual_by})" if manual_by else ""),
                description=desc,
                color=discord.Color.green(),
                timestamp=discord.utils.utcnow())
            embed.set_footer(text="서버에는 백업 파일을 남기지 않습니다 (디스크 절약)")

            if size > limit:
                embed.color = discord.Color.orange()
                embed.add_field(
                    name="⚠️ 업로드 실패",
                    value=(f"압축 파일이 채널 업로드 한도({_human(limit)})를 초과했습니다.\n"
                           "서버 부스트로 한도를 올리거나 백업 대상을 줄여주세요."),
                    inline=False)
                await channel.send(embed=embed)
                return f"용량 초과 ({_human(size)} > {_human(limit)})"

            await channel.send(
                embed=embed,
                file=discord.File(tmp_path, filename=f"arena-backup-{stamp}.tar.gz"))
            return f"백업 완료 ({_human(size)})"
        except Exception as e:
            print(f"[백업] 실패: {e}")
            try:
                await channel.send(f"❌ 백업 중 오류가 발생했습니다: `{e}`")
            except Exception:
                pass
            return f"실패: {e}"
        finally:
            # 업로드 성공/실패와 무관하게 임시 파일 즉시 삭제 (디스크 절약)
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass

    @app_commands.command(name="백업", description="[관리자] 지금 즉시 백업을 생성해 백업 채널로 보냅니다.")
    @app_commands.default_permissions(manage_guild=True)
    async def manual_backup(self, interaction: discord.Interaction):
        if not (interaction.user.guild_permissions.administrator
                or interaction.user.guild_permissions.manage_guild):
            return await interaction.response.send_message(
                "❌ 관리자만 사용할 수 있습니다.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        result = await self.run_backup(manual_by=interaction.user.display_name)
        await interaction.followup.send(f"💾 {result}", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(BackupCog(bot))
