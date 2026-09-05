import asyncio
import os
import discord
from discord.ext import commands, tasks
import aiohttp
from bs4 import BeautifulSoup
from aiohttp import web

# ==================== [ 0. Render 무료 가동용 웹 서버 ] ====================
async def handle(request):
    # UptimeRobot이 5분마다 신호를 보내 서버가 잠드는 것을 방지합니다.
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

# 웹 서버 연동을 위해 Custom Bot 클래스로 정의
class MaplePlanetBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        # 봇 가동 시 백그라운드 웹 서버 함께 구동
        asyncio.create_task(start_web_server())

bot = MaplePlanetBot()

# ==================== [ 설정 값 ] ====================
TOKEN = "MTU0NTYzMjMwMDg5NTgzNDI0Mw.Gzq9mb.4CnpkSHumKJ6QA1zLDELlPzOVApHyVy8vepCts"
NOTICE_CHANNEL_ID = 1545622885610029167
INVITE_LINK = "https://discord.gg/qWATqFHGzU"

NOTICE_URL = "https://mapleplanet.co.kr/board/notice"
UPDATE_URL = "https://mapleplanet.co.kr/board/update"

ROLE_CONFIG = {
    "운영진": {"pw": "1540", "role_name": "! 👑 운영진", "prefix": "! 👑 "},
    "길드원": {"pw": "5050", "role_name": "- 🔵 길드원", "prefix": "- 🔵 "},
    "손님": {"pw": "777", "role_name": "- 🟡 손님", "prefix": "- 🟡 "},
    "부주": {"pw": "5050", "role_name": "* 🥨 부주", "prefix": "* 🥨 "}
}

last_notice_title = ""
last_update_title = ""

# ==================== [ 공지 / 패치노트 크롤링 ] ====================
async def fetch_latest_post(session, url):
    try:
        async with session.get(url, timeout=10) as response:
            if response.status == 200:
                html = await response.text()
                soup = BeautifulSoup(html, 'html.parser')
                latest_post = soup.select_one('tr.notice a, .board-list a, .title a')
                if latest_post:
                    title = latest_post.text.strip()
                    href = latest_post.get('href')
                    link = href if href.startswith('http') else f"https://mapleplanet.co.kr{href}"
                    return title, link
    except Exception as e:
        print(f"크롤링 오작동 ({url}): {e}")
    return None, None

@tasks.loop(minutes=3)
async def check_maple_planet_news():
    global last_notice_title, last_update_title
    async with aiohttp.ClientSession() as session:
        title, link = await fetch_latest_post(session, NOTICE_URL)
        if title and last_notice_title and title != last_notice_title:
            channel = bot.get_channel(NOTICE_CHANNEL_ID)
            if channel:
                await channel.send(f"📢 **[메이플 플래닛 새 공지사항]**\n**제목:** {title}\n🔗 {link}")
        if title:
            last_notice_title = title

        title_up, link_up = await fetch_latest_post(session, UPDATE_URL)
        if title_up and last_update_title and title_up != last_update_title:
            channel = bot.get_channel(NOTICE_CHANNEL_ID)
            if channel:
                await channel.send(f"🛠️ **[메이플 플래닛 새 패치노트]**\n**제목:** {title_up}\n🔗 {link_up}")
        if title_up:
            last_update_title = title_up

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
    
    try:
        check_channel = await member.guild.fetch_channel(channel.id)
    except discord.NotFound:
        return

    if check_channel:
        try:
            dm_embed = discord.Embed(
                description=(
                    "📝 가입절차 사용 시간이 60분을 초과하여\n"
                    "- 서버에서 자동으로 나가졌습니다.\n"
                    "📝 다시 가입을 진행 해주시길 바랍니다.\n"
                    "🌱┃가입하기 채널에서 '💡 가입진행' 버튼 클릭 해주세요."
                ),
                color=discord.Color.light_grey()
            )
            await member.send(embed=dm_embed)
            await member.send(content=INVITE_LINK)
        except Exception as e:
            print(f"DM 전송 실패: {e}")

        try:
            await channel.delete()
            await member.kick(reason="가입 시간 60분 초과 자동 추방")
        except Exception as e:
            print(f"추방 처리 중 오류: {e}")

# ==================== [ 이벤트 처리 ] ====================
@bot.event
async def on_ready():
    print(f"무과금 봇이 구동되었습니다: {bot.user.name}")
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
    bot.run(TOKEN)
