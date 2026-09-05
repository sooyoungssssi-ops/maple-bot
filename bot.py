import asyncio
import os
import re
import aiohttp
from bs4 import BeautifulSoup
from aiohttp import web
import discord
from discord import app_commands
from discord.ext import commands, tasks

# ==================== [ 0. 웹 서버 ] ====================
async def handle(request):
    return web.Response(text="Maple Planet Bot is Running 24/7!")

async def start_web_server():
    app = web.Application()
    app.router.add_get('/', handle)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()

# ==================== [ 기본 설정 ] ====================
intents = discord.Intents.default()
intents.members = True
intents.message_content = True

class MaplePlanetBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        asyncio.create_task(start_web_server())

bot = MaplePlanetBot()

NOTICE_CHANNEL_ID = 1545622885610029167
UPDATE_CHANNEL_ID = 1545725589556559924
TEST_COMMAND_CHANNEL_ID = 1545712535377027123
INVITE_LINK = "https://discord.gg/qWATqFHGzU"

NOTICE_URL = "https://mapleplanet.co.kr/board/notice"
UPDATE_URL = "https://mapleplanet.co.kr/board/update"

ROLE_CONFIG = {
    "운영진": {"pw": "1540", "role_name": "! 👑 운영진", "prefix": "! 👑 "},
    "길드원": {"pw": "5050", "role_name": "- 🔵 길드원", "prefix": "- 🔵 "},
    "손님": {"pw": "777", "role_name": "- 🟡 손님", "prefix": "- 🟡 "},
    "부주": {"pw": "5050", "role_name": "* 🥨 부주", "prefix": "* 🥨 "}
}

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'ko-KR,ko;q=0.9'
}

last_notice_title = None
last_update_title = None

# ==================== [ 안전한 크롤링 함수 (에러 방지) ] ====================
async def fetch_board_data(session, url, keyword):
    try:
        # 타임아웃을 15초로 넉넉하게 잡고 통신 시도
        async with session.get(url, headers=HEADERS, timeout=15, ssl=False) as response:
            status = response.status
            if status != 200:
                return None, None, None, status
            
            html = await response.text()
            soup = BeautifulSoup(html, 'html.parser')
            
            # 1단계: <a> 태그 탐색
            for a in soup.find_all('a'):
                text = a.get_text(strip=True)
                if keyword in text:
                    href = a.get('href', '')
                    link = href if href.startswith('http') else f"https://mapleplanet.co.kr{href}"
                    return text, link, html, status
                    
            # 2단계: 주변 태그 탐색
            for tag in soup.find_all(['div', 'span', 'td']):
                text = tag.get_text(strip=True)
                if keyword in text and len(text) < 60:
                    parent_a = tag.find_parent('a')
                    if parent_a:
                        href = parent_a.get('href', '')
                        link = href if href.startswith('http') else f"https://mapleplanet.co.kr{href}"
                        return text, link, html, status

            return None, None, html, status
            
    except asyncio.TimeoutError:
        print(f"통신 시간 초과 (Timeout): {url}")
        return None, None, None, "TIMEOUT"
    except Exception as e:
        print(f"크롤링 중 예외 발생 ({url}): {e}")
        return None, None, None, "ERROR"

def extract_maintenance_time(html):
    if not html: return None
    soup = BeautifulSoup(html, 'html.parser')
    text = soup.get_text(separator='\n')
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    extracted = []
    for line in lines:
        if re.search(r'(무중단 패치 일시|마이그레이션 일시|점검 일시)', line):
            clean_line = line.replace('•', '').replace('*', '').strip()
            extracted.append(f"- {clean_line}")
    return "\n".join(extracted) if extracted else None

@tasks.loop(minutes=3)
async def check_maple_planet_news():
    global last_notice_title, last_update_title
    async with aiohttp.ClientSession() as session:
        title, link, html, _ = await fetch_board_data(session, NOTICE_URL, "점검 안내")
        if title and title != last_notice_title:
            channel = bot.get_channel(NOTICE_CHANNEL_ID)
            if channel:
                time_info = extract_maintenance_time(html)
                msg = f"@everyone 📢 **[플래닛 점검안내]**\n{time_info}\n🔗 {link}" if time_info else f"@everyone 📢 **[플래닛 점검안내]**\n**제목:** {title}\n🔗 {link}"
                await channel.send(msg)
            last_notice_title = title

        title_up, link_up, _, _ = await fetch_board_data(session, UPDATE_URL, "패치노트")
        if title_up and title_up != last_update_title:
            channel = bot.get_channel(UPDATE_CHANNEL_ID)
            if channel:
                await channel.send(f"@everyone 🛠️ **[플래닛 패치노트안내]**\n{title_up}({link_up})")
            last_update_title = title_up

# ==================== [ 커맨드 테스트 로직 ] ====================
async def run_notice_test():
    async with aiohttp.ClientSession() as session:
        title, link, html, status = await fetch_board_data(session, NOTICE_URL, "점검 안내")
        if not title:
            return False, f"❌ [실패] 통신 상태 코드: {status} (사이트 접근이 거부되었거나 응답이 없습니다)"
        
        channel = bot.get_channel(NOTICE_CHANNEL_ID)
        if channel:
            time_info = extract_maintenance_time(html)
            msg = f"@everyone 📢 **[플래닛 점검안내]**\n{time_info}\n🔗 {link}" if time_info else f"@everyone 📢 **[플래닛 점검안내]**\n**제목:** {title}\n🔗 {link}"
            await channel.send(msg)
            return True, "✅ '점검 안내' 테스트 발송 성공!"
        return False, "❌ 채널을 찾을 수 없습니다."

async def run_update_test():
    async with aiohttp.ClientSession() as session:
        title, link, html, status = await fetch_board_data(session, UPDATE_URL, "패치노트")
        if not title:
            return False, f"❌ [실패] 통신 상태 코드: {status} (사이트 접근이 거부되었거나 응답이 없습니다)"
        
        channel = bot.get_channel(UPDATE_CHANNEL_ID)
        if channel:
            await channel.send(f"@everyone 🛠️ **[플래닛 패치노트안내]**\n{title}({link})")
            return True, "✅ '패치노트' 테스트 발송 성공!"
        return False, "❌ 채널을 찾을 수 없습니다."

# ==================== [ 슬래시 & 일반 커맨드 ] ====================
@bot.tree.command(name="공지테스트")
async def test_notice_slash(interaction: discord.Interaction):
    if interaction.channel_id != TEST_COMMAND_CHANNEL_ID:
        return await interaction.response.send_message("❌ 테스트 채널 전용입니다.", ephemeral=True)
    await interaction.response.defer(ephemeral=True)
    _, msg = await run_notice_test()
    await interaction.followup.send(msg, ephemeral=True)

@bot.tree.command(name="패치노트테스트")
async def test_update_slash(interaction: discord.Interaction):
    if interaction.channel_id != TEST_COMMAND_CHANNEL_ID:
        return await interaction.response.send_message("❌ 테스트 채널 전용입니다.", ephemeral=True)
    await interaction.response.defer(ephemeral=True)
    _, msg = await run_update_test()
    await interaction.followup.send(msg, ephemeral=True)

@bot.command(name="공지테스트")
async def test_notice_cmd(ctx):
    if ctx.channel.id != TEST_COMMAND_CHANNEL_ID: return
    _, msg = await run_notice_test()
    await ctx.send(msg)

@bot.command(name="패치노트테스트")
async def test_update_cmd(ctx):
    if ctx.channel.id != TEST_COMMAND_CHANNEL_ID: return
    _, msg = await run_update_test()
    await ctx.send(msg)

# ==================== [ 가입 진행 Modal & View ] ====================
class RegisterModal(discord.ui.Modal, title="무과금 봇 가입 진행"):
    nickname = discord.ui.TextInput(label="1. 사용하실 닉네임", required=True, max_length=15)
    role_choice = discord.ui.TextInput(label="2. 역할 (운영진 / 길드원 / 손님 / 부주)", required=True)
    job_or_main = discord.ui.TextInput(label="3. 직업 (부주는 본주 캐릭터명 작성)", required=False, max_length=15)
    password = discord.ui.TextInput(label="4. 비밀번호 입력", required=True, style=discord.TextStyle.short)

    async def on_submit(self, interaction: discord.Interaction):
        user_nick = self.nickname.value.strip()
        user_role = self.role_choice.value.strip()
        user_job = self.job_or_main.value.strip()
        user_pw = self.password.value.strip()

        if user_role not in ROLE_CONFIG:
            return await interaction.response.send_message("❌ 역할을 잘못 입력하셨습니다.", ephemeral=True)
        config = ROLE_CONFIG[user_role]
        if user_pw != config["pw"]:
            return await interaction.response.send_message("❌ 비밀번호가 올바르지 않습니다.", ephemeral=True)
        if user_role == "부주" and not user_job:
            return await interaction.response.send_message("❌ 부주 역할은 본주 캐릭터명을 입력해야 합니다.", ephemeral=True)

        if user_role == "부주": formatted_nick = f"{config['prefix']}{user_nick}({user_job}부주)"
        else: formatted_nick = f"{config['prefix']}{user_nick}({user_job})" if user_job else f"{config['prefix']}{user_nick}"
        
        formatted_nick = formatted_nick[:32]
        member = interaction.user
        target_role = discord.utils.get(interaction.guild.roles, name=config["role_name"])

        try:
            await member.edit(nick=formatted_nick)
            if target_role: await member.add_roles(target_role)
            await interaction.response.send_message(f"✅ 가입 완료! 프로필: **{formatted_nick}**", ephemeral=True)
            await asyncio.sleep(3)
            await interaction.channel.delete()
        except discord.Forbidden:
            await interaction.response.send_message("⚠️ 권한 오류: 봇 역할을 위로 올려주세요.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"오류: {e}", ephemeral=True)

class RegisterView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    @discord.ui.button(label="가입진행", style=discord.ButtonStyle.success, emoji="💡", custom_id="register_btn")
    async def register_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(RegisterModal())

async def start_join_timer(member: discord.Member, channel: discord.TextChannel):
    await asyncio.sleep(3600)
    try:
        current_member = await member.guild.fetch_member(member.id)
    except discord.NotFound:
        return
    has_registered = any(role.name in [cfg["role_name"] for cfg in ROLE_CONFIG.values()] for role in current_member.roles)
    if has_registered: return

    try: check_channel = await member.guild.fetch_channel(channel.id)
    except discord.NotFound: check_channel = None

    if check_channel:
        try:
            embed = discord.Embed(description="📝 가입 시간 60분 초과로 자동 추방되었습니다.\n다시 가입해주세요.", color=discord.Color.light_grey())
            await current_member.send(embed=embed)
            await current_member.send(content=INVITE_LINK)
            await check_channel.delete()
            await current_member.kick(reason="가입 시간 초과")
        except Exception:
            pass

# ==================== [ 이벤트 처리 ] ====================
@bot.event
async def on_ready():
    print(f"구동 완료: {bot.user.name}")
    for guild in bot.guilds:
        try:
            bot.tree.copy_global_to(guild=guild)
            await bot.tree.sync(guild=guild)
        except Exception: pass
    if not check_maple_planet_news.is_running():
        check_maple_planet_news.start()

@bot.event
async def on_member_join(member: discord.Member):
    guild = member.guild
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(read_messages=False),
        member: discord.PermissionOverwrite(read_messages=True, send_messages=True),
        guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True)
    }
    entry_channel = await guild.create_text_channel(name="🌱┃가입하기", overwrites=overwrites)
    embed = discord.Embed(
        title="📋 가입안내",
        description=f"🐱 **{member.display_name}**님 환영합니다!\n\n💡 아래 가입진행 버튼을 눌러주세요.",
        color=discord.Color.from_rgb(46, 204, 113)
    )
    await entry_channel.send(content=member.mention, embed=embed, view=RegisterView())
    asyncio.create_task(start_join_timer(member, entry_channel))

@bot.event
async def on_member_remove(member: discord.Member):
    for channel in member.guild.text_channels:
        if channel.name == "🌱┃가입하기" and member in channel.overwrites:
            try: await channel.delete()
            except Exception: pass
            break

if __name__ == "__main__":
    bot.run(os.environ.get("DISCORD_TOKEN"))