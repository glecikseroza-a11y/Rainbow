import os
import discord
from discord.ext import commands, tasks
import colorsys
import libsql_client

# --- КОНФІГУРАЦІЯ ЗМІННИХ СЕРЕДОВИЩА ---
TOKEN = os.getenv("DISCORD_TOKEN")
TURSO_URL = os.getenv("TURSO_DATABASE_URL")
TURSO_AUTH_TOKEN = os.getenv("TURSO_AUTH_TOKEN")

# Додаткова варіація: інтервал зміни кольорів у секундах (за замовчуванням 20)
# Можна змінити на Railway через змінну INTERVAL
INTERVAL = int(os.getenv("INTERVAL", 20))

intents = discord.Intents.default()
intents.message_content = True

# --- ІНІЦІАЛІЗАЦІЯ ХМАРНОЇ БАЗИ TURSO ---
def get_db_client():
    return libsql_client.create_client_sync(
        url=TURSO_URL,
        auth_token=TURSO_AUTH_TOKEN
    )

def init_db():
    client = get_db_client()
    try:
        client.execute("""
            CREATE TABLE IF NOT EXISTS role_presets (
                role_id INTEGER PRIMARY KEY,
                preset TEXT DEFAULT 'rainbow',
                hue REAL DEFAULT 0.0
            )
        """)
    finally:
        client.close()

init_db()

# --- ФУНКЦІЇ ГЕНЕРАЦІЇ КОЛЬОРІВ ЗА ШАБЛОНАМИ ---
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
        if not self.color_loop.is_running():
            self.color_loop.start()

    @commands.Cog.listener()
    async def on_ready(self):
        print(f'Бот залогінився як {self.user} (ID: {self.user.id})')
        print(f'Інтервал зміни кольорів: {INTERVAL} сек.')
        print('Підключено до хмарної бази Turso. Все готово!')

    # --- ФОНОВА ЗАДАЧА ЗМІНИ КОЛЬОРІВ ---
    @tasks.loop(seconds=INTERVAL)
    async def color_loop(self):
        client = get_db_client()
        try:
            result = client.execute("SELECT role_id, preset, hue FROM role_presets")
            rows = result.rows
        except Exception as e:
            print(f"Помилка читання з бази Turso: {e}")
            client.close()
            return

        for row in rows:
            role_id, preset, hue = row[0], row[1], row[2]
            
            # Шукаємо роль серед серверів бота
            role = None
            guild = None
            for g in self.guilds:
                r = g.get_role(role_id)
                if r:
                    role = r
                    guild = g
                    break

            if not guild or not role:
                continue

            if not guild.me.top_role > role:
                continue

            color = get_preset_color(preset, hue)

            try:
                await role.edit(color=color)
            except (discord.Forbidden, discord.HTTPException):
                continue

            # Збільшуємо hue для плавного переливу
            new_hue = (hue + 0.02) % 1.0
            try:
                client.execute(
                    "UPDATE role_presets SET hue = ? WHERE role_id = ?",
                    [new_hue, role_id]
                )
            except Exception:
                pass

        client.close()

bot = RainbowBot()

# --- КОМАНДИ ---

@bot.command(name="setcolor")
@commands.has_permissions(administrator=True)
async def set_color_preset(ctx, role: discord.Role, preset: str):
    valid_presets = ['rainbow', 'pastel', 'dark', 'neon', 'green', 'red', 'blue', 'yellow']
    preset = preset.lower()

    if preset not in valid_presets:
        await ctx.send(f"❌ Невідомий шаблон! Доступні варіанти: `{', '.join(valid_presets)}`")
        return

    client = get_db_client()
    try:
        client.execute("""
            INSERT INTO role_presets (role_id, preset, hue) 
            VALUES (?, ?, 0.0)
            ON CONFLICT(role_id) DO UPDATE SET preset = ?
        """, [role.id, preset, preset])
    except Exception as e:
        await ctx.send(f"❌ Помилка бази даних: {e}")
        client.close()
        return
    client.close()

    await ctx.send(f"✅ Успішно! Роль {role.mention} тепер переливається за шаблоном **{preset}**.")

@bot.command(name="removerole")
@commands.has_permissions(administrator=True)
async def remove_role(ctx, role: discord.Role):
    client = get_db_client()
    try:
        client.execute("DELETE FROM role_presets WHERE role_id = ?", [role.id])
    except Exception as e:
        await ctx.send(f"❌ Помилка: {e}")
        client.close()
        return
    client.close()

    await ctx.send(f"🗑️ Роль {role.mention} видалена з бази кольорів.")

@bot.command(name="presets")
async def list_presets(ctx):
    embed = discord.Embed(
        title="🎨 Доступні шаблони кольорів",
        description="Використовуй команду `!setcolor @Роль <шаблон>`",
        color=discord.Color.blurple()
    )
    embed.add_field(name="🌈 rainbow", value="Класична яскрава веселка", inline=False)
    embed.add_field(name="🌸 pastel", value="М'які пастельні кольори", inline=False)
    embed.add_field(name="🌑 dark", value="Глибокі приглушені темні відтінки", inline=False)
    embed.add_field(name="⚡ neon", value="Яскраві кислотні кольори", inline=False)
    embed.add_field(name="🟢 green", value="Зелені та смарагдові тони", inline=False)
    embed.add_field(name="🔴 red", value="Червоні та рожеві тони", inline=False)
    embed.add_field(name="🔵 blue", value="Сині та фіолетові тони", inline=False)
    embed.add_field(name="🟡 yellow", value="Жовті та помаранчеві тони", inline=False)
    
    await ctx.send(embed=embed)

if __name__ == "__main__":
    if not TOKEN:
        print("Помилка: Не знайдено DISCORD_TOKEN!")
        exit(1)
    if not TURSO_URL or not TURSO_AUTH_TOKEN:
        print("Помилка: Не знайдено змінні середовища Turso!")
        exit(1)
        
    bot.run(TOKEN)
