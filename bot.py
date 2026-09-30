import os
import discord
from discord import app_commands
from discord.ext import commands, tasks
import colorsys
import libsql

# --- КОНФІГУРАЦІЯ ЗМІННИХ СЕРЕДОВИЩА ---
TOKEN = os.getenv("DISCORD_TOKEN")
TURSO_URL = os.getenv("TURSO_DATABASE_URL")
TURSO_AUTH_TOKEN = os.getenv("TURSO_AUTH_TOKEN")
INTERVAL = int(os.getenv("INTERVAL", 20))

ALLOWED_GUILD_ID = int(os.getenv("GUILD_ID", 0))
OWNER_ID = int(os.getenv("OWNER_ID", 0))

intents = discord.Intents.all()

# --- ІНІЦІАЛІЗАЦІЯ ХМАРНОЇ БАЗИ ---
def get_db_connection():
    url = TURSO_URL
    if url.startswith("libsql://"):
        url = url.replace("libsql://", "https://")
    elif url.startswith("wss://"):
        url = url.replace("wss://", "https://")

    return libsql.connect(database=url, auth_token=TURSO_AUTH_TOKEN)

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS role_presets (
            role_id INTEGER PRIMARY KEY,
            preset TEXT DEFAULT 'rainbow',
            hue REAL DEFAULT 0.0
        )
    """)
    conn.commit()
    conn.close()

init_db()

# --- ФУНКЦІЇ ГЕНЕРАЦІЇ КОЛЬОРІВ ---
def get_preset_color(preset: str, hue: float) -> discord.Color:
    if preset == 'pastel':
        rgb = colorsys.hsv_to_rgb(hue, 0.4, 1.0)
    elif preset == 'dark':
        rgb = colorsys.hsv_to_rgb(hue, 1.0, 0.4)
    elif preset == 'neon':
        rgb = colorsys.hsv_to_rgb(hue, 1.0, 1.0)
    elif preset == 'green':
        green_hue = 0.25 + (hue * 0.2) % 0.2
        rgb = colorsys.hsv_to_rgb(green_hue, 0.9, 0.9)
    elif preset == 'red':
        red_hue = (0.9 + hue * 0.15) % 1.0
        rgb = colorsys.hsv_to_rgb(red_hue, 0.9, 0.9)
    elif preset == 'blue':
        blue_hue = 0.55 + (hue * 0.25) % 0.25
        rgb = colorsys.hsv_to_rgb(blue_hue, 0.9, 0.9)
    elif preset == 'yellow':
        yellow_hue = 0.08 + (hue * 0.1) % 0.1
        rgb = colorsys.hsv_to_rgb(yellow_hue, 0.9, 0.9)
    else:
        rgb = colorsys.hsv_to_rgb(hue, 1.0, 1.0)

    return discord.Color.from_rgb(
        int(rgb[0] * 255),
        int(rgb[1] * 255),
        int(rgb[2] * 255)
    )

class RainbowBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        if ALLOWED_GUILD_ID:
            guild = discord.Object(id=ALLOWED_GUILD_ID)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
        else:
            await self.tree.sync()
            
        if not self.color_loop.is_running():
            self.color_loop.start()

    @commands.Cog.listener()
    async def on_ready(self):
        print(f'Бот залогінився як {self.user} (ID: {self.user.id})')
        print(f'Інтервал зміни кольорів: {INTERVAL} сек.')
        if ALLOWED_GUILD_ID:
            print(f'🔒 Бот прив\'язаний виключно до сервера ID: {ALLOWED_GUILD_ID}')
        if OWNER_ID:
            print(f'👑 Власник команд (Owner ID): {OWNER_ID}')
        print('Підключено до Turso через HTTPS. Slash-команди активовано!')

    # --- ФОНОВА ЗАДАЧА ЗМІНИ КОЛЬОРІВ ---
    @tasks.loop(seconds=INTERVAL)
    async def color_loop(self):
        await self.wait_until_ready()

        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT role_id, preset, hue FROM role_presets")
            rows = cursor.fetchall()
        except Exception as e:
            print(f"❌ Помилка читання з бази Turso: {e}")
            return

        if not rows:
            return

        guild = self.get_guild(ALLOWED_GUILD_ID)
        if not guild:
            print(f"⚠️ Сервер з ID {ALLOWED_GUILD_ID} не знайдено серед кешу бота!")
            return

        for row in rows:
            role_id, preset, hue = row[0], row[1], row[2]
            
            try:
                role = guild.get_role(role_id)
                if not role:
                    role = await guild.fetch_role(role_id)
            except discord.NotFound:
                print(f"⚠️ Роль ID {role_id} не знайдена на сервері (можливо, її видалили).")
                continue
            except Exception as e:
                print(f"⚠️ Помилка отримання ролі ID {role_id}: {e}")
                continue

            if not guild.me.top_role > role:
                print(f"❌ ПОМИЛКА ІЄРАРХІЇ: Роль бота ({guild.me.top_role.name}) нижче або на рівні з цільовою роллю ({role.name})!")
                continue

            color = get_preset_color(preset, hue)

            try:
                await role.edit(color=color)
                print(f"✅ Успішно змінено колір ролі {role.name} на {color} (preset: {preset}, hue: {round(hue, 2)})")
            except discord.Forbidden:
                print(f"❌ ПОМИЛКА ДОСТУПУ (Forbidden): Бот не має прав 'Manage Roles' або роль вище його власної для ролі {role.name}.")
                continue
            except discord.HTTPException as e:
                print(f"❌ HTTP Помилка при зміні ролі {role.name}: {e}")
                continue

            new_hue = (hue + 0.02) % 1.0
            try:
                cursor.execute(
                    "UPDATE role_presets SET hue = ? WHERE role_id = ?",
                    (new_hue, role_id)
                )
                conn.commit()
            except Exception as e:
                print(f"Помилка оновлення hue в базі: {e}")

        conn.close()

bot = RainbowBot()

PRESET_CHOICES = [
    app_commands.Choice(name="🌈 Rainbow (Класична веселка)", value="rainbow"),
    app_commands.Choice(name="🌸 Pastel (М'які пастельні)", value="pastel"),
    app_commands.Choice(name="🌑 Dark (Темні приглушені)", value="dark"),
    app_commands.Choice(name="⚡ Neon (Яскраві кислотні)", value="neon"),
    app_commands.Choice(name="🟢 Green (Зелені / Смарагдові)", value="green"),
    app_commands.Choice(name="🔴 Red (Червоні / Рожеві)", value="red"),
    app_commands.Choice(name="🔵 Blue (Сині / Фіолетові)", value="blue"),
    app_commands.Choice(name="🟡 Yellow (Жовті / Помаранчеві)", value="yellow"),
]

# --- SLASH-КОМАНДИ ---

@bot.tree.command(name="setcolor", description="Встановити райдужний перелив для ролі")
@app_commands.choices(preset=PRESET_CHOICES)
@app_commands.describe(role="Обери роль зі списку", preset="Обери стиль переливу зі списку")
async def slash_set_color(interaction: discord.Interaction, role: discord.Role, preset: app_commands.Choice[str]):
    if OWNER_ID and interaction.user.id != OWNER_ID:
        await interaction.response.send_message("❌ У тебе немає прав на використання цієї команди!", ephemeral=True)
        return

    if ALLOWED_GUILD_ID and interaction.guild_id != ALLOWED_GUILD_ID:
        return

    # Залізобетонна перестраховка: якщо раптом Discord передав ID сервера замість ролі
    target_role_id = role.id
    if target_role_id == interaction.guild_id:
        # Шукаємо реальну роль за такою ж назвою або беремо першу кастомну роль із сервера, щоб не записувати ID сервера
        found_real_role = discord.utils.get(interaction.guild.roles, name=role.name)
        if found_real_role and found_real_role.id != interaction.guild_id:
            target_role_id = found_real_role.id
            role = found_real_role
        else:
            await interaction.response.send_message("❌ Помилка: Не вдалося розпізнати роль. Спробуй обрати іншу роль.", ephemeral=True)
            return

    preset_value = preset.value

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO role_presets (role_id, preset, hue) 
            VALUES (?, ?, 0.0)
            ON CONFLICT(role_id) DO UPDATE SET preset = ?
        """, (target_role_id, preset_value, preset_value))
        conn.commit()
        conn.close()
    except Exception as e:
        await interaction.response.send_message(f"❌ Помилка бази даних: {e}", ephemeral=True)
        return

    await interaction.response.send_message(f"✅ Успішно! Роль {role.mention} тепер переливається за шаблоном **{preset.name}**.")

@bot.tree.command(name="removerole", description="Видалити роль із системи переливу кольорів")
@app_commands.describe(role="Обери роль, яку потрібно прибрати")
async def slash_remove_role(interaction: discord.Interaction, role: discord.Role):
    if OWNER_ID and interaction.user.id != OWNER_ID:
        await interaction.response.send_message("❌ У тебе немає прав на використання цієї команди!", ephemeral=True)
        return

    if ALLOWED_GUILD_ID and interaction.guild_id != ALLOWED_GUILD_ID:
        return

    target_role_id = role.id
    if target_role_id == interaction.guild_id:
        await interaction.response.send_message("❌ Помилка: Обрана некоректна роль.", ephemeral=True)
        return

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM role_presets WHERE role_id = ?", (target_role_id,))
        conn.commit()
        conn.close()
    except Exception as e:
        await interaction.response.send_message(f"❌ Помилка: {e}", ephemeral=True)
        return

    await interaction.response.send_message(f"🗑️ Роль {role.mention} видалена з бази кольорів.")

@bot.tree.command(name="presets", description="Показати інформаційну панель усіх доступних шаблонів кольорів")
async def slash_presets(interaction: discord.Interaction):
    if ALLOWED_GUILD_ID and interaction.guild_id != ALLOWED_GUILD_ID:
        return

    embed = discord.Embed(
        title="🎨 Інформаційна панель шаблонів кольорів",
        description="Коли ти вводиш команду `/setcolor`, вибирай потрібну роль через випадаючий список у Discord:",
        color=discord.Color.from_rgb(114, 137, 218)
    )
    embed.add_field(name="🌈 Rainbow", value="Класична яскрава повноспектральна веселка", inline=False)
    embed.add_field(name="🌸 Pastel", value="Ніжні та м'які пастельні відтінки", inline=False)
    embed.add_field(name="🌑 Dark", value="Глибокі, приглушені та темні тони", inline=False)
    embed.add_field(name="⚡ Neon", value="Кислотні, максимальні випалюючі очі кольори", inline=False)
    embed.add_field(name="🟢 Green", value="Діапазон від смарагдового до яскраво-зеленого", inline=False)
    embed.add_field(name="🔴 Red", value="Червоні, бордові та рожеві переливи", inline=False)
    embed.add_field(name="🔵 Blue", value="Глибокий синій, ультрамарин та фіолетовий", inline=False)
    embed.add_field(name="🟡 Yellow", value="Теплі жовті та насичені помаранчеві відтінки", inline=False)
    
    embed.set_footer(text="Використовуй /setcolor з вибором ролі та стилю!")
    
    await interaction.response.send_message(embed=embed)

if __name__ == "__main__":
    if not TOKEN:
        print("Помилка: Не знайдено DISCORD_TOKEN!")
        exit(1)
    if not TURSO_URL or not TURSO_AUTH_TOKEN:
        print("Помилка: Не знайдено змінні середовища Turso!")
        exit(1)
        
    bot.run(TOKEN)
