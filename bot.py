import os
import discord
from discord import app_commands
from discord.ext import commands, tasks
import colorsys
import libsql

# ============================================================
# КОНФІГУРАЦІЯ
# ============================================================

TOKEN = os.getenv("DISCORD_TOKEN")

TURSO_URL = os.getenv("TURSO_DATABASE_URL")
TURSO_AUTH_TOKEN = os.getenv("TURSO_AUTH_TOKEN")

INTERVAL = int(os.getenv("INTERVAL", 20))

ALLOWED_GUILD_ID = int(os.getenv("GUILD_ID", 0))
OWNER_ID = int(os.getenv("OWNER_ID", 0))


# ============================================================
# DISCORD INTENTS
# ============================================================

intents = discord.Intents.all()


# ============================================================
# TURSO DATABASE
# ============================================================

def get_db_connection():
    url = TURSO_URL

    if url.startswith("libsql://"):
        url = url.replace("libsql://", "https://")

    elif url.startswith("wss://"):
        url = url.replace("wss://", "https://")

    return libsql.connect(
        database=url,
        auth_token=TURSO_AUTH_TOKEN
    )


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


# ============================================================
# ГЕНЕРАЦІЯ КОЛЬОРІВ
# ============================================================

def get_preset_color(preset: str, hue: float) -> discord.Color:

    if preset == "pastel":
        rgb = colorsys.hsv_to_rgb(
            hue,
            0.4,
            1.0
        )

    elif preset == "dark":
        rgb = colorsys.hsv_to_rgb(
            hue,
            1.0,
            0.4
        )

    elif preset == "neon":
        rgb = colorsys.hsv_to_rgb(
            hue,
            1.0,
            1.0
        )

    elif preset == "green":
        green_hue = 0.25 + (hue * 0.2) % 0.2

        rgb = colorsys.hsv_to_rgb(
            green_hue,
            0.9,
            0.9
        )

    elif preset == "red":
        red_hue = (0.9 + hue * 0.15) % 1.0

        rgb = colorsys.hsv_to_rgb(
            red_hue,
            0.9,
            0.9
        )

    elif preset == "blue":
        blue_hue = 0.55 + (hue * 0.25) % 0.25

        rgb = colorsys.hsv_to_rgb(
            blue_hue,
            0.9,
            0.9
        )

    elif preset == "yellow":
        yellow_hue = 0.08 + (hue * 0.1) % 0.1

        rgb = colorsys.hsv_to_rgb(
            yellow_hue,
            0.9,
            0.9
        )

    else:
        rgb = colorsys.hsv_to_rgb(
            hue,
            1.0,
            1.0
        )

    return discord.Color.from_rgb(
        int(rgb[0] * 255),
        int(rgb[1] * 255),
        int(rgb[2] * 255)
    )


# ============================================================
# BOT
# ============================================================

class RainbowBot(commands.Bot):

    def __init__(self):
        super().__init__(
            command_prefix="!",
            intents=intents
        )

    # --------------------------------------------------------
    # STARTUP
    # --------------------------------------------------------

    async def setup_hook(self):

        print("🔄 Запуск setup_hook...")

        if ALLOWED_GUILD_ID:

            guild = discord.Object(
                id=ALLOWED_GUILD_ID
            )

            self.tree.copy_global_to(
                guild=guild
            )

            await self.tree.sync(
                guild=guild
            )

            print(
                f"✅ Slash-команди синхронізовано "
                f"з сервером {ALLOWED_GUILD_ID}"
            )

        else:

            await self.tree.sync()

            print(
                "✅ Глобальні slash-команди синхронізовано"
            )

        if not self.color_loop.is_running():

            self.color_loop.start()

            print(
                f"🎨 Color loop запущено. "
                f"Інтервал: {INTERVAL} сек."
            )

    # --------------------------------------------------------
    # READY
    # --------------------------------------------------------

    @commands.Cog.listener()
    async def on_ready(self):

        print()
        print("=" * 60)

        print(
            f"🤖 Бот залогінився як "
            f"{self.user} "
            f"(ID: {self.user.id})"
        )

        print(
            f"⏱ Інтервал зміни кольорів: "
            f"{INTERVAL} сек."
        )

        if ALLOWED_GUILD_ID:

            print(
                f"🔒 Дозволений сервер ID: "
                f"{ALLOWED_GUILD_ID}"
            )

        if OWNER_ID:

            print(
                f"👑 Owner ID: "
                f"{OWNER_ID}"
            )

        print(
            "💾 Turso: підключення через HTTPS"
        )

        print(
            "⚡ Slash-команди активовані"
        )

        print("=" * 60)
        print()

    # --------------------------------------------------------
    # ОСНОВНИЙ COLOR LOOP
    # --------------------------------------------------------

    @tasks.loop(seconds=INTERVAL)
    async def color_loop(self):

        await self.wait_until_ready()

        # ----------------------------------------------------
        # Отримуємо сервер
        # ----------------------------------------------------

        guild = self.get_guild(
            ALLOWED_GUILD_ID
        )

        if not guild:

            print(
                "⚠️ Сервер не знайдений у кеші Discord."
            )

            return

        # ----------------------------------------------------
        # ВАЖЛИВО:
        # Отримуємо СВІЖИЙ список ролей через API.
        #
        # Не використовуємо guild.get_role(),
        # бо він залежить від кешу.
        # ----------------------------------------------------

        try:

            roles = await guild.fetch_roles()

        except discord.Forbidden:

            print(
                "❌ Бот не має доступу до отримання ролей."
            )

            return

        except discord.HTTPException as e:

            print(
                f"⚠️ Помилка Discord API при отриманні ролей: "
                f"{e}"
            )

            return

        # ----------------------------------------------------
        # Читаємо базу
        # ----------------------------------------------------

        conn = None

        try:

            conn = get_db_connection()

            cursor = conn.cursor()

            cursor.execute("""
                SELECT role_id, preset, hue
                FROM role_presets
            """)

            rows = cursor.fetchall()

        except Exception as e:

            print(
                f"❌ Помилка читання з Turso: {e}"
            )

            if conn:
                conn.close()

            return

        if not rows:

            conn.close()

            return

        # ----------------------------------------------------
        # Обробляємо кожну роль
        # ----------------------------------------------------

        for row in rows:

            role_id = int(row[0])
            preset = row[1]
            hue = float(row[2])

            # ------------------------------------------------
            # Шукаємо роль у СВІЖОМУ списку Discord
            # ------------------------------------------------

            role = discord.utils.get(
                roles,
                id=role_id
            )

            if not role:

                print(
                    f"⚠️ Роль ID {role_id} "
                    f"реально не знайдена на сервері."
                )

                continue

            # ------------------------------------------------
            # Отримуємо Member бота
            # ------------------------------------------------

            bot_member = guild.me

            if not bot_member:

                try:

                    bot_member = await guild.fetch_member(
                        self.user.id
                    )

                except Exception as e:

                    print(
                        f"⚠️ Не вдалося отримати Member бота: {e}"
                    )

                    continue

            # ------------------------------------------------
            # Перевірка ієрархії ролей
            # ------------------------------------------------

            if not bot_member.top_role > role:

                print(
                    f"❌ ПОМИЛКА ІЄРАРХІЇ: "
                    f"роль бота "
                    f"'{bot_member.top_role.name}' "
                    f"(ID: {bot_member.top_role.id}) "
                    f"не вище ролі "
                    f"'{role.name}' "
                    f"(ID: {role.id})"
                )

                continue

            # ------------------------------------------------
            # Рахуємо колір
            # ------------------------------------------------

            color = get_preset_color(
                preset,
                hue
            )

            # ------------------------------------------------
            # Змінюємо колір
            # ------------------------------------------------

            try:

                await role.edit(
                    color=color,
                    reason="Rainbow role color update"
                )

                print(
                    f"✅ Роль '{role.name}' "
                    f"(ID: {role.id}) "
                    f"→ {color} "
                    f"| preset={preset} "
                    f"| hue={round(hue, 3)}"
                )

            except discord.Forbidden:

                print(
                    f"❌ FORBIDDEN: "
                    f"бот не може змінити роль "
                    f"'{role.name}'. "
                    f"Перевір Manage Roles та ієрархію."
                )

                continue

            except discord.HTTPException as e:

                print(
                    f"❌ HTTP помилка при зміні "
                    f"ролі '{role.name}': {e}"
                )

                continue

            # ------------------------------------------------
            # Наступний hue
            # ------------------------------------------------

            new_hue = (
                hue + 0.02
            ) % 1.0

            try:

                cursor.execute(
                    """
                    UPDATE role_presets
                    SET hue = ?
                    WHERE role_id = ?
                    """,
                    (
                        new_hue,
                        role_id
                    )
                )

                conn.commit()

            except Exception as e:

                print(
                    f"❌ Помилка оновлення hue "
                    f"для ролі {role_id}: {e}"
                )

        # ----------------------------------------------------
        # Закриваємо базу
        # ----------------------------------------------------

        conn.close()


# ============================================================
# СТВОРЮЄМО БОТА
# ============================================================

bot = RainbowBot()


# ============================================================
# PRESET CHOICES
# ============================================================

PRESET_CHOICES = [

    app_commands.Choice(
        name="🌈 Rainbow (Класична веселка)",
        value="rainbow"
    ),

    app_commands.Choice(
        name="🌸 Pastel (М'які пастельні)",
        value="pastel"
    ),

    app_commands.Choice(
        name="🌑 Dark (Темні приглушені)",
        value="dark"
    ),

    app_commands.Choice(
        name="⚡ Neon (Яскраві кислотні)",
        value="neon"
    ),

    app_commands.Choice(
        name="🟢 Green (Зелені / Смарагдові)",
        value="green"
    ),

    app_commands.Choice(
        name="🔴 Red (Червоні / Рожеві)",
        value="red"
    ),

    app_commands.Choice(
        name="🔵 Blue (Сині / Фіолетові)",
        value="blue"
    ),

    app_commands.Choice(
        name="🟡 Yellow (Жовті / Помаранчеві)",
        value="yellow"
    ),
]


# ============================================================
# /SETCOLOR
# ============================================================

@bot.tree.command(
    name="setcolor",
    description="Встановити райдужний перелив для ролі"
)
@app_commands.choices(
    preset=PRESET_CHOICES
)
@app_commands.describe(
    role="Обери роль зі списку",
    preset="Обери стиль переливу зі списку"
)
async def slash_set_color(
    interaction: discord.Interaction,
    role: discord.Role,
    preset: app_commands.Choice[str]
):

    # --------------------------------------------------------
    # OWNER CHECK
    # --------------------------------------------------------

    if OWNER_ID and interaction.user.id != OWNER_ID:

        await interaction.response.send_message(
            "❌ У тебе немає прав на використання цієї команди!",
            ephemeral=True
        )

        return

    # --------------------------------------------------------
    # SERVER CHECK
    # --------------------------------------------------------

    if (
        ALLOWED_GUILD_ID
        and interaction.guild_id != ALLOWED_GUILD_ID
    ):

        await interaction.response.send_message(
            "❌ Ця команда недоступна на цьому сервері.",
            ephemeral=True
        )

        return

    # --------------------------------------------------------
    # Discord вже передав нормальний Role object.
    # Ніяких get_role() тут не потрібно.
    # --------------------------------------------------------

    target_role_id = role.id

    preset_value = preset.value

    # --------------------------------------------------------
    # Перевіряємо ієрархію одразу
    # --------------------------------------------------------

    if interaction.guild:

        bot_member = interaction.guild.me

        if bot_member:

            if not bot_member.top_role > role:

                await interaction.response.send_message(
                    f"❌ Бот не може керувати роллю {role.mention}.\n\n"
                    f"Підніми роль бота **вище** за цю роль "
                    f"у Server Settings → Roles.",
                    ephemeral=True
                )

                return

    # --------------------------------------------------------
    # Запис у базу
    # --------------------------------------------------------

    try:

        conn = get_db_connection()

        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO role_presets
                (role_id, preset, hue)
            VALUES
                (?, ?, 0.0)
            ON CONFLICT(role_id)
            DO UPDATE SET
                preset = ?,
                hue = 0.0
            """,
            (
                target_role_id,
                preset_value,
                preset_value
            )
        )

        conn.commit()
        conn.close()

    except Exception as e:

        await interaction.response.send_message(
            f"❌ Помилка бази даних:\n```{e}```",
            ephemeral=True
        )

        return

    # --------------------------------------------------------
    # Відповідь
    # --------------------------------------------------------

    await interaction.response.send_message(
        f"✅ Успішно!\n\n"
        f"Роль {role.mention} тепер переливається "
        f"за шаблоном **{preset.name}**.\n\n"
        f"🆔 ID ролі: `{role.id}`"
    )


# ============================================================
# /REMOVEROLE
# ============================================================

@bot.tree.command(
    name="removerole",
    description="Видалити роль із системи переливу кольорів"
)
@app_commands.describe(
    role="Обери роль, яку потрібно прибрати"
)
async def slash_remove_role(
    interaction: discord.Interaction,
    role: discord.Role
):

    # --------------------------------------------------------
    # OWNER CHECK
    # --------------------------------------------------------

    if OWNER_ID and interaction.user.id != OWNER_ID:

        await interaction.response.send_message(
            "❌ У тебе немає прав на використання цієї команди!",
            ephemeral=True
        )

        return

    # --------------------------------------------------------
    # SERVER CHECK
    # --------------------------------------------------------

    if (
        ALLOWED_GUILD_ID
        and interaction.guild_id != ALLOWED_GUILD_ID
    ):

        await interaction.response.send_message(
            "❌ Ця команда недоступна на цьому сервері.",
            ephemeral=True
        )

        return

    # --------------------------------------------------------
    # Видаляємо роль з БД
    # --------------------------------------------------------

    try:

        conn = get_db_connection()

        cursor = conn.cursor()

        cursor.execute(
            """
            DELETE FROM role_presets
            WHERE role_id = ?
            """,
            (
                role.id,
            )
        )

        conn.commit()

        deleted = cursor.rowcount

        conn.close()

    except Exception as e:

        await interaction.response.send_message(
            f"❌ Помилка бази даних:\n```{e}```",
            ephemeral=True
        )

        return

    # --------------------------------------------------------
    # Відповідь
    # --------------------------------------------------------

    if deleted:

        await interaction.response.send_message(
            f"🗑️ Роль {role.mention} "
            f"(ID: `{role.id}`) "
            f"видалена з системи переливу."
        )

    else:

        await interaction.response.send_message(
            f"ℹ️ Роль {role.mention} "
            f"(ID: `{role.id}`) "
            f"не була знайдена в базі."
        )


# ============================================================
# /PRESETS
# ============================================================

@bot.tree.command(
    name="presets",
    description="Показати інформаційну панель усіх доступних шаблонів кольорів"
)
async def slash_presets(
    interaction: discord.Interaction
):

    # --------------------------------------------------------
    # SERVER CHECK
    # --------------------------------------------------------

    if (
        ALLOWED_GUILD_ID
        and interaction.guild_id != ALLOWED_GUILD_ID
    ):

        return

    # --------------------------------------------------------
    # EMBED
    # --------------------------------------------------------

    embed = discord.Embed(
        title="🎨 Інформаційна панель шаблонів кольорів",
        description=(
            "Коли ти вводиш команду `/setcolor`, "
            "вибирай потрібну роль через випадаючий список "
            "у Discord:"
        ),
        color=discord.Color.from_rgb(
            114,
            137,
            218
        )
    )

    embed.add_field(
        name="🌈 Rainbow",
        value="Класична яскрава повноспектральна веселка",
        inline=False
    )

    embed.add_field(
        name="🌸 Pastel",
        value="Ніжні та м'які пастельні відтінки",
        inline=False
    )

    embed.add_field(
        name="🌑 Dark",
        value="Глибокі, приглушені та темні тони",
        inline=False
    )

    embed.add_field(
        name="⚡ Neon",
        value="Яскраві неонові кольори",
        inline=False
    )

    embed.add_field(
        name="🟢 Green",
        value="Діапазон від смарагдового до яскраво-зеленого",
        inline=False
    )

    embed.add_field(
        name="🔴 Red",
        value="Червоні, бордові та рожеві переливи",
        inline=False
    )

    embed.add_field(
        name="🔵 Blue",
        value="Глибокий синій, ультрамарин та фіолетовий",
        inline=False
    )

    embed.add_field(
        name="🟡 Yellow",
        value="Теплі жовті та насичені помаранчеві відтінки",
        inline=False
    )

    embed.set_footer(
        text="Використовуй /setcolor з вибором ролі та стилю!"
    )

    await interaction.response.send_message(
        embed=embed
    )


# ============================================================
# ERROR HANDLER
# ============================================================

@bot.tree.error
async def on_app_command_error(
    interaction: discord.Interaction,
    error: app_commands.AppCommandError
):

    print(
        f"❌ Помилка slash-команди: {error}"
    )

    if interaction.response.is_done():

        await interaction.followup.send(
            f"❌ Сталася помилка: `{error}`",
            ephemeral=True
        )

    else:

        await interaction.response.send_message(
            f"❌ Сталася помилка: `{error}`",
            ephemeral=True
        )


# ============================================================
# ЗАПУСК
# ============================================================

if __name__ == "__main__":

    if not TOKEN:

        print(
            "❌ Помилка: не знайдено DISCORD_TOKEN!"
        )

        exit(1)

    if not TURSO_URL or not TURSO_AUTH_TOKEN:

        print(
            "❌ Помилка: не знайдено "
            "TURSO_DATABASE_URL або TURSO_AUTH_TOKEN!"
        )

        exit(1)

    print("🚀 Запуск Rainbow Bot...")

    bot.run(TOKEN)
