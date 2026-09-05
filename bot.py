import asyncio
import os
import re
import aiohttp
from aiohttp import web
import discord
from discord import app_commands
from discord.ext import commands, tasks

# ==================== [ 0. Render 무료 가동용 웹 서버 ] ====================
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
    print(f"웹 서버가 정상 시작되었습니다. (Port: {port})")

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

# ==================== [ 설정 값 ] ====================
NOTICE_CHANNEL_ID = 1545622885610029167   # 점검 안내 공지 채널 ID
UPDATE_CHANNEL_ID = 1545725589556559924   # 패치노트 알림 채널 ID
TEST_COMMAND_CHANNEL_ID = 1545712535377027123  # 테스트 명령어 전용 채널 ID

INVITE_LINK = "https://discord.gg/qWATqFHGzU"

# HTML 크롤링 대신 직접 내부 API 호출 (JSON 파싱)
NOTICE_API_URL = "https://mapleplanet.co.kr/api/board/notice"
UPDATE_API_URL = "https://mapleplanet.co.kr/api/board/update"

ROLE_CONFIG = {
    "운영진": {"pw": "1540", "role_name": "! 👑 운영진", "prefix": "! 👑 "},
    "길드원": {"pw": "5050", "role_name": "- 🔵 길드원", "prefix": "- 🔵 "},
    "손님": {"pw": "777", "role_name": "- 🟡 손님", "prefix": "- 🟡 "},
    "부주": {"pw": "5050", "role_name": "* 🥨 부주", "prefix": "* 🥨 "}
}

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/plain, */*'
}

last_notice_id = None
last_update_id = None

# ==================== [ 게시판 API 파싱 로직 ] ====================
async def fetch_latest_post_from_api(session, api_url, target_keyword):
    """
    내부 API에서 목록을 받아 target_keyword가 포함된 최신 글 추출
    """
    try:
        async with session.get(api_url, headers=HEADERS, timeout=10) as response:
            if response.status == 200:
                data = await response.json()
                
                # API 데이터 구조(list 혹은 dict 내 list) 자동 대응
                posts = data if isinstance(data, list) else data.get('list', data.get('posts', data.get('data', [])))

                for post in posts:
                    title = post.get('title', '').strip()
                    post_id = post.get('id', post.get('seq', post.get('boardId', '')))
                    
                    # 키워드 검색 (예: "점검 안내" 또는 "패치노트")
                    if target_keyword in title:
                        board_type = "notice" if "notice" in api_url else "update"
                        link = f"https://mapleplanet.co.kr/board/{board_type}/{post_id}" if post_id else f"https://mapleplanet.co.kr/board/{board_type}"
                        
                        # 본문 내용 추출 (점검 일시 파싱용)
                        content = post.get('content', post.get('body', ''))
                        return post_id, title, link, content

    except Exception as e:
        print(f"API 크롤링 오류 ({api_url}): {e}")
    
    return None, None, None, None

def extract_maintenance_time(text):
    """본문에서 '일시' 문구 추출"""
    if not text:
        return None
    
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    extracted = []
    
    for line in lines:
        if re.search(r'(무중단 패치 일시|마이그레이션 일시|점검 일시)', line):
            clean_line = line.replace('•', '').replace('*', '').strip()
            extracted.append(f"- {clean_line}")
            
    return "\n".join(extracted) if extracted else None

@tasks.loop(minutes=3)
async def check_maple_planet_news():
    global last_notice_id, last_update_id
    async with aiohttp.ClientSession() as session:
        # 1. 점검 안내 공지 자동 모니터링
        post_id, title, link, content = await fetch_latest_post_from_api(session, NOTICE_API_URL, "점검 안내")
        if post_id and last_notice_id and post_id != last_notice_id:
            channel = bot.get_channel(NOTICE_CHANNEL_ID)
            if channel:
                time_info = extract_maintenance_time(content)
                if time_info:
                    message = f"@everyone 📢 **[플래닛 점검안내]**\n{time_info}\n🔗 {link}"
                else:
                    message = f"@everyone 📢 **[플래닛 점검안내]**\n**제목:** {title}\n🔗 {link}"
                await channel.send(message)
        if post_id:
            last_notice_id = post_id

        # 2. 패치노트 자동 모니터링 ("패치노트" 들어간 모든 글 감지)
        post_id_up, title_up, link_up, _ = await fetch_latest_post_from_api(session, UPDATE_API_URL, "패치노트")
        if post_id_up and last_update_id and post_id_up != last_update_id:
            channel = bot.get_channel(UPDATE_CHANNEL_ID)
            if channel:
                message = f"@everyone 🛠️ **[플래닛 패치노트안내]**\n{title_up}({link_up})"
                await channel.send(message)
        if post_id_up:
            last_update_id = post_id_up

# ==================== [ 공통 테스트 함수 ] ====================
async def run_notice_test():
    async with aiohttp.ClientSession() as session:
        post_id, title, link, content = await fetch_latest_post_from_api(session, NOTICE_API_URL, "점검 안내")
        if not title:
            return False, "❌ '점검 안내' 글을 불러오지 못했습니다."
        
        channel = bot.get_channel(NOTICE_CHANNEL_ID)
        if channel:
            time_info = extract_maintenance_time(content)
            if time_info:
                message = f"@everyone 📢 **[플래닛 점검안내]**\n{time_info}\n🔗 {link}"
            else:
                message = f"@everyone 📢 **[플래닛 점검안내]**\n**제목:** {title}\n🔗 {link}"
            await channel.send(message)
            return True, "✅ 성공적으로 점검 공지 알림을 테스트 발송했습니다."
        return False, "❌ 공지 채널을 찾을 수 없습니다."

async def run_update_test():
    async with aiohttp.ClientSession() as session:
        post_id_up, title_up, link_up, _ = await fetch_latest_post_from_api(session, UPDATE_API_URL, "패치노트")
        if not title_up:
            return False, "❌ '패치노트' 글을 불러오지 못했습니다."

        channel = bot.get_channel(UPDATE_CHANNEL_ID)
        if channel:
            message = f"@everyone 🛠️ **[플래닛 패치노트안내]**\n{title_up}({link_up})"
            await channel.send(message)
            return True, "✅ 성공적으로 패치노트 알림을 테스트 발송했습니다."
        return False, "❌ 패치노트 채널을 찾을 수 없습니다."

# ==================== [ 슬래시 커맨드 ] ====================
@bot.tree.command(name="공지테스트", description="최근 '점검 안내' 공지를 테스트 전송합니다.")
async def test_notice_slash(interaction: discord.Interaction):
    if interaction.channel_id != TEST_COMMAND_CHANNEL_ID:
        await interaction.response.send_message("❌ 이 명령어는 지정된 테스트 채널에서만 사용할 수 있습니다.", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    _, msg = await run_notice_test()
    await interaction.followup.send(msg, ephemeral=True)

@bot.tree.command(name="패치노트테스트", description="최근 '패치노트' 글을 테스트 전송합니다.")
async def test_update_slash(interaction: discord.Interaction):
    if interaction.channel_id != TEST_COMMAND_CHANNEL_ID:
        await interaction.response.send_message("❌ 이 명령어는 지정된 테스트 채널에서만 사용할 수 있습니다.", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    _, msg = await run_update_test()
    await interaction.followup.send(msg, ephemeral=True)

# ==================== [ 일반 텍스트 명령어 (!공지테스트, !패치노트테스트) ] ====================
@bot.command(name="공지테스트")
async def test_notice_cmd(ctx):
    if ctx.channel.id != TEST_COMMAND_CHANNEL_ID:
        return
    _, msg = await run_notice_test()
    await ctx.send(msg)

@bot.command(name="패치노트테스트")
async def test_update_cmd(ctx):
    if ctx.channel.id != TEST_COMMAND_CHANNEL_ID:
        return
    _, msg = await run_update_test()
    await ctx.send(msg)

# ==================== [ 가입 진행 Modal ] ====================
class RegisterModal(discord.ui.Modal, title="무과금 봇 가입 진행"):
    nickname = discord.ui.TextInput(
        label="1. 사용하실 닉네임", 
        placeholder="서버에서 사용할 닉네임을 입력하세요", 
        required=True,
        max_length=15
    )
    role_choice = discord.ui.TextInput(
        label="2. 역할 (운영진 / 길드원 / 손님 / 부주)", 
        placeholder="운영진, 길드원, 손님, 부주 중 하나 입력", 
        required=True
    )
    job_or_main = discord.ui.TextInput(
        label="3. 직업 (부주는 본주 캐릭터명 작성)", 
        placeholder="직업 입력 (부주 선택 시 본주 캐릭터명 입력)", 
        required=False,
        max_length=15
    )
    password = discord.ui.TextInput(
        label="4. 비밀번호 입력", 
        placeholder="선택한 역할의 비밀번호를 입력하세요", 
        required=True,
        style=discord.TextStyle.short
    )

    async def on_submit(self, interaction: discord.Interaction):
        user_nick = self.nickname.value.strip()
        user_role = self.role_choice.value.strip()
        user_job_info = self.job_or_main.value.strip()
        user_pw = self.password.value.strip()

        if user_role not in ROLE_CONFIG:
            await interaction.response.send_message(
                "❌ **역할을 잘못 입력하셨습니다.** ('운영진', '길드원', '손님', '부주' 중 입력)", 
                ephemeral=True
            )
            return

        config = ROLE_CONFIG[user_role]

        if user_pw != config["pw"]:
            await interaction.response.send_message(
                f"❌ **[{user_role}] 비밀번호가 올바르지 않습니다.** 다시 시도해주세요.", 
                ephemeral=True
            )
            return

        if user_role == "부주":
            if not user_job_info:
                await interaction.response.send_message(
                    "❌ **'부주' 역할을 선택하신 경우 3번 항목에 본주 캐릭터명을 입력하셔야 합니다.**", 
                    ephemeral=True
                )
                return
            formatted_nick = f"{config['prefix']}{user_nick}({user_job_info}부주)"
        else:
            if user_job_info:
                formatted_nick = f"{config['prefix']}{user_nick}({user_job_info})"
            else:
                formatted_nick = f"{config['prefix']}{user_nick}"

        if len(formatted_nick) > 32:
            formatted_nick = formatted_nick[:32]

        guild = interaction.guild
        member = interaction.user
        target_role = discord.utils.get(guild.roles, name=config["role_name"])

        try:
            await member.edit(nick=formatted_nick)
            if target_role:
                await member.add_roles(target_role)

            await interaction.response.send_message(
                f"✅ **가입 절차가 완료되었습니다!**\n설정된 프로필: **{formatted_nick}**\n잠시 후 해당 채널이 삭제됩니다.", 
                ephemeral=True
            )

            await asyncio.sleep(3)
            await interaction.channel.delete()

        except discord.Forbidden:
            await interaction.response.send_message(
                "⚠️ **권한 오류**: 봇의 역할 순위가 부여할 역할보다 낮습니다. 서버 설정에서 봇 역할을 가장 위로 올려주세요.", 
                ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(f"오류가 발생했습니다: {e}", ephemeral=True)

class RegisterView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="가입진행", style=discord.ButtonStyle.success, emoji="💡", custom_id="register_btn")
    async def register_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(RegisterModal())

# ==================== [ 60분 미입력 추방 로직 ] ====================
async def start_join_timer(member: discord.Member, channel: discord.TextChannel):
    await asyncio.sleep(3600)
    
    guild = member.guild
    
    try:
        current_member = await guild.fetch_member(member.id)
    except discord.NotFound:
        return

    target_role_names = [cfg["role_name"] for cfg in ROLE_CONFIG.values()]
    has_registered_role = any(role.name in target_role_names for role in current_member.roles)

    if has_registered_role:
        return

    try:
        check_channel = await guild.fetch_channel(channel.id)
    except discord.NotFound:
        check_channel = None

    if check_channel:
        try:
            dm_embed = discord.Embed(
                description=(
                    "📝 가입절차 사용 시간이 60분을 초과하여\n"
                    "- 서버에서 자동으로 나가졌습니다.\n"
                    "- 다시 가입을 진행 해주시길 바랍니다.\n"
                    "🌱┃가입하기 채널에서 '💡 가입진행' 버튼 클릭 해주세요."
                ),
                color=discord.Color.light_grey()
            )
            await current_member.send(embed=dm_embed)
            await current_member.send(content=INVITE_LINK)
        except Exception as e:
            print(f"DM 전송 실패: {e}")

        try:
            await check_channel.delete()
            await current_member.kick(reason="가입 시간 60분 초과 자동 추방")
        except Exception as e:
            print(f"추방 처리 중 오류: {e}")

# ==================== [ 이벤트 처리 ] ====================
@bot.event
async def on_ready():
    print(f"무과금 봇이 구동되었습니다: {bot.user.name}")
    
    for guild in bot.guilds:
        try:
            bot.tree.copy_global_to(guild=guild)
            await bot.tree.sync(guild=guild)
            print(f"[{guild.name}] 서버에 명령어 동기화 완료")
        except Exception as e:
            print(f"[{guild.name}] 서버 명령어 동기화 실패: {e}")

    if not check_maple_planet_news.is_running():
        check_maple_planet_news.start()

@bot.event
async def on_member_join(member: discord.Member):
    guild = member.guild
    
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(read_messages=False),
        member: discord.PermissionOverwrite(
            read_messages=True, 
            send_messages=True, 
            read_message_history=True
        ),
        guild.me: discord.PermissionOverwrite(
            read_messages=True, 
            send_messages=True, 
            manage_channels=True, 
            read_message_history=True
        )
    }

    entry_channel = await guild.create_text_channel(
        name="🌱┃가입하기", 
        overwrites=overwrites
    )

    embed = discord.Embed(
        title=f"📋 가입안내 - {bot.user.name}",
        description=(
            f"🐱 **{member.display_name}**님 전용 가입 안내\n\n"
            f"🎉 **서버에 오신 것을 환영합니다!**\n\n"
            f"{member.mention} 님, 안녕하세요!\n\n"
            f"📝 **가입 방법**\n"
            f"```\n💡  가입진행 버튼 클릭!\n```\n\n"
            f"• ✅ 안녕하세요. 가입진행 안내글 입니다.\n"
            f"• ✅ 가입버튼을 눌러 주세요.\n"
            f"• ✅ 버튼을 누르면 입력창(닉네임/역할/직업/비밀번호)이 나옵니다.\n"
            f"• ✅ 정보를 올바르게 입력하면 다음 단계가 진행됩니다.\n"
            f"• ✅ 가입절차가 완료되면 모든 메뉴가 보입니다."
        ),
        color=discord.Color.from_rgb(46, 204, 113)
    )
    embed.set_footer(text="가입 문의 : 가입문제시 간부진 에게 DM · 문의 해주세요.")

    await entry_channel.send(content=f"{member.mention}", embed=embed, view=RegisterView())
    asyncio.create_task(start_join_timer(member, entry_channel))

@bot.event
async def on_member_remove(member: discord.Member):
    guild = member.guild
    for channel in guild.text_channels:
        if channel.name == "🌱┃가입하기":
            if member in channel.overwrites:
                try:
                    await channel.delete()
                except Exception:
                    pass
                break

# ==================== [ 실행 ] ====================
if __name__ == "__main__":
    token = os.environ.get("DISCORD_TOKEN")
    if not token:
        raise ValueError("Render의 Environment 항목에 DISCORD_TOKEN을 설정해야 합니다.")
    bot.run(token)