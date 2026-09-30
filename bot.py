import os
import discord
from discord import app_commands
from discord.ext import commands, tasks
import colorsys
import libsql

# ============================================================
# КОНФІГУРАЦІЯ БОТА
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
# TURSO
# ============================================================

def get_db_connection():
    url = TURSO_URL

    if url.startswith("libsql://"):
        url = url.replace("libsql://", "https://", 1)

    elif url.startswith("wss://"):
        url = url.replace("wss://", "https://", 1)

    return libsql.connect(
        database=url,
        auth_token=TURSO_AUTH_TOKEN
    )


def init_db():
    """
    Створює таблицю role_presets.

    Discord ID зберігаємо як TEXT, а не INTEGER,
    щоб уникнути проблем з великими Discord Snowflake ID.
    """

    conn = get_db_connection()
    cursor = conn.cursor()

    try:

        # ----------------------------------------------------
        # Перевіряємо, чи існує таблиця
        # ----------------------------------------------------

        cursor.execute("""
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
              AND name = 'role_presets'
        """)

        table_exists = cursor.fetchone()

        # ----------------------------------------------------
        # Якщо таблиці немає
        # ----------------------------------------------------

        if not table_exists:

            print("🗄️ Таблиці role_presets немає.")
            print("🆕 Створюю нову таблицю з role_id TEXT...")

            cursor.execute("""
                CREATE TABLE role_presets (
                    role_id TEXT PRIMARY KEY,
                    preset TEXT DEFAULT 'rainbow',
                    hue REAL DEFAULT 0.0
                )
            """)

            conn.commit()

            print("✅ Таблицю role_presets створено.")

            return

        # ----------------------------------------------------
        # Перевіряємо тип role_id
        # ----------------------------------------------------

        cursor.execute("""
            PRAGMA table_info(role_presets)
        """)

        columns = cursor.fetchall()

        role_id_type = None

        for column in columns:

            if column[1] == "role_id":

                role_id_type = str(
                    column[2]
                ).upper()

                break

        print(
            f"🗄️ role_presets знайдена. "
            f"Тип role_id: {role_id_type}"
        )

        # ----------------------------------------------------
        # Якщо вже TEXT
        # ----------------------------------------------------

        if role_id_type == "TEXT":

            print("✅ role_id вже має тип TEXT.")

            return

        # ----------------------------------------------------
        # Міграція INTEGER → TEXT
        # ----------------------------------------------------

        print()
        print("⚠️ Виявлено старий тип role_id INTEGER.")
        print("🔄 Виконую міграцію INTEGER → TEXT...")

        cursor.execute("""
            ALTER TABLE role_presets
            RENAME TO role_presets_old
        """)

        cursor.execute("""
            CREATE TABLE role_presets (
                role_id TEXT PRIMARY KEY,
                preset TEXT DEFAULT 'rainbow',
                hue REAL DEFAULT 0.0
            )
        """)

        cursor.execute("""
            INSERT INTO role_presets
                (role_id, preset, hue)
            SELECT
                CAST(role_id AS TEXT),
                preset,
                hue
            FROM role_presets_old
        """)

        cursor.execute("""
            DROP TABLE role_presets_old
        """)

        conn.commit()

        print("✅ Міграція завершена.")
        print("✅ role_id тепер TEXT.")
        print()

    except Exception as e:

        conn.rollback()

        print(
            f"❌ Помилка init_db(): {e}"
        )

        raise

    finally:

        conn.close()


# Ініціалізація БД
init_db()


# ============================================================
# КОЛЬОРИ
# ============================================================

def get_preset_color(
    preset: str,
    hue: float
) -> discord.Color:

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

        green_hue = (
            0.25 + (hue * 0.2) % 0.2
        )

        rgb = colorsys.hsv_to_rgb(
            green_hue,
            0.9,
            0.9
        )

    elif preset == "red":

        red_hue = (
            0.9 + hue * 0.15
        ) % 1.0

        rgb = colorsys.hsv_to_rgb(
            red_hue,
            0.9,
            0.9
        )

    elif preset == "blue":

        blue_hue = (
            0.55 + (hue * 0.25) % 0.25
        )

        rgb = colorsys.hsv_to_rgb(
            blue_hue,
            0.9,
            0.9
        )

    elif preset == "yellow":

        yellow_hue = (
            0.08 + (hue * 0.1) % 0.1
        )

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

    # ========================================================
    # SETUP
    # ========================================================

    async def setup_hook(self):

        print("🔄 setup_hook запущено...")

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
                f"з Guild ID: {ALLOWED_GUILD_ID}"
            )

        else:

            await self.tree.sync()

            print(
                "✅ Глобальні slash-команди синхронізовано"
            )

        if not self.color_loop.is_running():

            self.color_loop.start()

            print(
                f"🎨 Color loop запущено "
                f"(кожні {INTERVAL} секунд)"
            )

    # ========================================================
    # READY
    # ========================================================

    @commands.Cog.listener()
    async def on_ready(self):

        print()
        print("=" * 65)

        print(
            f"🤖 Бот: {self.user}"
        )

        print(
            f"🆔 Bot ID: {self.user.id}"
        )

        print(
            f"🏠 GUILD_ID з ENV: {ALLOWED_GUILD_ID}"
        )

        print(
            f"👑 OWNER_ID: {OWNER_ID}"
        )

        print(
            f"⏱ INTERVAL: {INTERVAL} сек."
        )

        print("=" * 65)
        print()

    # ========================================================
    # COLOR LOOP
    # ========================================================

    @tasks.loop(seconds=INTERVAL)
    async def color_loop(self):

        await self.wait_until_ready()

        print()
        print("🎨 --- ЗМІНА КОЛЬОРІВ ---")

        # ----------------------------------------------------
        # SERVER
        # ----------------------------------------------------

        guild = self.get_guild(
            ALLOWED_GUILD_ID
        )

        if not guild:

            print(
                f"❌ Сервер НЕ знайдений.\n"
                f"   GUILD_ID: {ALLOWED_GUILD_ID}"
            )

            return

        print(
            f"🏠 Сервер: {guild.name}"
        )

        print(
            f"🆔 Guild ID: {guild.id}"
        )

        # ----------------------------------------------------
        # TURSO
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
                f"❌ Помилка читання Turso: {e}"
            )

            if conn:

                conn.close()

            return

        if not rows:

            print(
                "ℹ️ У базі немає ролей для переливу."
            )

            conn.close()

            return

        print(
            f"📋 У базі знайдено ролей: {len(rows)}"
        )

        # ----------------------------------------------------
        # ROLES
        # ----------------------------------------------------

        for row in rows:

            role_id_text = str(row[0])

            try:

                role_id = int(
                    role_id_text
                )

            except ValueError:

                print(
                    f"❌ Некоректний Role ID у БД: "
                    f"{role_id_text}"
                )

                continue

            preset = str(row[1])
            hue = float(row[2])

            print()
            print(
                f"🔎 Роль:\n"
                f"   ID: {role_id_text}\n"
                f"   Preset: {preset}\n"
                f"   Hue: {round(hue, 3)}"
            )

            # ------------------------------------------------
            # DISCORD API
            # ------------------------------------------------

            try:

                role = await guild.fetch_role(
                    role_id
                )

            except discord.NotFound:

                print(
                    f"❌ Discord API каже: "
                    f"роль {role_id_text} НЕ ЗНАЙДЕНА."
                )

                print(
                    "🗑️ Видаляю старий ID з Turso..."
                )

                try:

                    cursor.execute(
                        """
                        DELETE FROM role_presets
                        WHERE role_id = ?
                        """,
                        (
                            role_id_text,
                        )
                    )

                    conn.commit()

                    print(
                        f"✅ Старий ID {role_id_text} "
                        f"видалено з Turso."
                    )

                except Exception as e:

                    print(
                        f"❌ Не вдалося видалити "
                        f"старий ID: {e}"
                    )

                continue

            except discord.Forbidden:

                print(
                    f"❌ Discord API: "
                    f"бот не має доступу до ролі "
                    f"{role_id_text}."
                )

                continue

            except discord.HTTPException as e:

                print(
                    f"❌ Discord API HTTP error "
                    f"для ролі {role_id_text}: {e}"
                )

                continue

            except Exception as e:

                print(
                    f"❌ Невідома помилка "
                    f"для ролі {role_id_text}: {e}"
                )

                continue

            # ------------------------------------------------
            # ROLE FOUND
            # ------------------------------------------------

            print(
                f"✅ РОЛЬ ЗНАЙДЕНА:\n"
                f"   Назва: {role.name}\n"
                f"   ID: {role.id}\n"
                f"   Position: {role.position}\n"
                f"   Managed: {role.managed}"
            )

            # ------------------------------------------------
            # BOT MEMBER
            # ------------------------------------------------

            bot_member = guild.me

            if not bot_member:

                try:

                    bot_member = await guild.fetch_member(
                        self.user.id
                    )

                except Exception as e:

                    print(
                        f"❌ Не вдалося отримати "
                        f"Member бота: {e}"
                    )

                    continue

            # ------------------------------------------------
            # MANAGED ROLE
            # ------------------------------------------------

            if role.managed:

                print(
                    f"❌ Роль '{role.name}' "
                    f"є Managed Role і не може "
                    f"бути змінена ботом."
                )

                continue

            # ------------------------------------------------
            # HIERARCHY
            # ------------------------------------------------

            print(
                f"📊 Ієрархія:\n"
                f"   Роль бота: "
                f"'{bot_member.top_role.name}' "
                f"(position {bot_member.top_role.position})\n"
                f"   Цільова роль: "
                f"'{role.name}' "
                f"(position {role.position})"
            )

            if not bot_member.top_role > role:

                print(
                    f"❌ Бот НЕ МОЖЕ керувати "
                    f"роллю '{role.name}'.\n"
                    f"   Роль бота повинна бути "
                    f"вище за неї."
                )

                continue

            # ------------------------------------------------
            # COLOR
            # ------------------------------------------------

            color = get_preset_color(
                preset,
                hue
            )

            # ------------------------------------------------
            # EDIT ROLE
            # ------------------------------------------------

            try:

                await role.edit(
                    color=color,
                    reason="Rainbow role color update"
                )

                print(
                    f"✅ КОЛІР ЗМІНЕНО:\n"
                    f"   Роль: {role.name}\n"
                    f"   ID: {role.id}\n"
                    f"   Color: {color}\n"
                    f"   Preset: {preset}"
                )

            except discord.Forbidden:

                print(
                    "❌ FORBIDDEN:\n"
                    "   Бот бачить роль, "
                    "але Discord забороняє її змінювати."
                )

                continue

            except discord.HTTPException as e:

                print(
                    f"❌ HTTP помилка "
                    f"при зміні '{role.name}': {e}"
                )

                continue

            # ------------------------------------------------
            # NEW HUE
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
                        role_id_text
                    )
                )

                conn.commit()

                print(
                    f"🌈 Новий Hue: "
                    f"{round(new_hue, 3)}"
                )

            except Exception as e:

                print(
                    f"❌ Не вдалося оновити hue "
                    f"для {role_id_text}: {e}"
                )

        # ----------------------------------------------------
        # CLOSE DB
        # ----------------------------------------------------

        if conn:

            conn.close()

        print(
            f"⏳ Наступна зміна через "
            f"{INTERVAL} секунд."
        )

        print(
            "🎨 --- ЗМІНУ ЗАВЕРШЕНО ---"
        )

        print()


# ============================================================
# BOT INSTANCE
# ============================================================

bot = RainbowBot()


# ============================================================
# PRESETS
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

    print()
    print("📝 --- /setcolor ---")

    print(
        f"👤 User:\n"
        f"   Name: {interaction.user}\n"
        f"   ID: {interaction.user.id}"
    )

    print(
        f"🏠 Guild:\n"
        f"   Name: "
        f"{interaction.guild.name if interaction.guild else 'None'}\n"
        f"   ID: {interaction.guild_id}"
    )

    print(
        f"🎭 Role:\n"
        f"   Name: {role.name}\n"
        f"   ID: {role.id}\n"
        f"   Type: {type(role.id)}\n"
        f"   String: {str(role.id)}"
    )

    print(
        f"🎨 Preset: {preset.value}"
    )

    # --------------------------------------------------------
    # OWNER
    # --------------------------------------------------------

    if OWNER_ID and interaction.user.id != OWNER_ID:

        await interaction.response.send_message(
            "❌ У тебе немає прав на використання цієї команди!",
            ephemeral=True
        )

        return

    # --------------------------------------------------------
    # SERVER
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
    # BOT / HIERARCHY
    # --------------------------------------------------------

    if interaction.guild:

        bot_member = interaction.guild.me

        if not bot_member:

            try:

                bot_member = await interaction.guild.fetch_member(
                    bot.user.id
                )

            except Exception:

                bot_member = None

        if bot_member:

            if role.managed:

                await interaction.response.send_message(
                    "❌ Цю роль не можна змінювати, "
                    "оскільки вона керується інтеграцією Discord.",
                    ephemeral=True
                )

                return

            if not bot_member.top_role > role:

                await interaction.response.send_message(
                    f"❌ Бот не може керувати роллю {role.mention}.\n\n"
                    f"Роль бота **{bot_member.top_role.name}** "
                    f"повинна знаходитися вище за цю роль "
                    f"в налаштуваннях сервера.",
                    ephemeral=True
                )

                return

    # --------------------------------------------------------
    # ROLE ID AS TEXT
    # --------------------------------------------------------

    target_role_id = str(role.id)
    preset_value = str(preset.value)

    print()
    print("💾 --- ПІДГОТОВКА ЗАПИСУ В TURSO ---")

    print(
        f"   target_role_id = {target_role_id}"
    )

    print(
        f"   type = {type(target_role_id)}"
    )

    print(
        f"   preset = {preset_value}"
    )

    # --------------------------------------------------------
    # SAVE
    # --------------------------------------------------------

    conn = None

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
                preset = excluded.preset,
                hue = 0.0
            """,
            (
                target_role_id,
                preset_value
            )
        )

        conn.commit()

        print(
            "✅ SQL INSERT/UPDATE виконано."
        )

        # ----------------------------------------------------
        # READ BACK
        # ----------------------------------------------------

        cursor.execute(
            """
            SELECT role_id, typeof(role_id), preset, hue
            FROM role_presets
            WHERE role_id = ?
            """,
            (
                target_role_id,
            )
        )

        saved_row = cursor.fetchone()

        print()
        print("🔍 --- ПЕРЕВІРКА TURSO ПІСЛЯ ЗАПИСУ ---")

        print(
            f"   Передано role_id: {target_role_id}"
        )

        print(
            f"   Отримано з БД: {saved_row}"
        )

        if saved_row:

            saved_role_id = str(
                saved_row[0]
            )

            saved_type = saved_row[1]

            print(
                f"   Збережений role_id: "
                f"{saved_role_id}"
            )

            print(
                f"   Тип role_id у БД: "
                f"{saved_type}"
            )

            print(
                f"   Збережений preset: "
                f"{saved_row[2]}"
            )

            print(
                f"   Збережений hue: "
                f"{saved_row[3]}"
            )

            if saved_role_id != target_role_id:

                print(
                    "🚨 КРИТИЧНА ПОМИЛКА!"
                )

                print(
                    "🚨 ID ЗМІНИВСЯ ПІД ЧАС ЗАПИСУ!"
                )

                print(
                    f"🚨 Передано: "
                    f"{target_role_id}"
                )

                print(
                    f"🚨 Отримано: "
                    f"{saved_role_id}"
                )

            else:

                print(
                    "✅ ID У TURSO ПОВНІСТЮ СПІВПАДАЄ."
                )

        else:

            print(
                "🚨 ПОМИЛКА: після запису "
                "рядок НЕ ЗНАЙДЕНО!"
            )

        print(
            "🔍 --- КІНЕЦЬ ПЕРЕВІРКИ TURSO ---"
        )

    except Exception as e:

        print(
            f"❌ Turso error: {e}"
        )

        if conn:

            conn.close()

        await interaction.response.send_message(
            f"❌ Помилка бази даних:\n```{e}```",
            ephemeral=True
        )

        return

    finally:

        if conn:

            conn.close()

    # --------------------------------------------------------
    # RESPONSE
    # --------------------------------------------------------

    await interaction.response.send_message(
        f"✅ Успішно!\n\n"
        f"Роль {role.mention} тепер переливається "
        f"за шаблоном **{preset.name}**.\n\n"
        f"🆔 Role ID: `{target_role_id}`"
    )

    print()
    print("📝 --- /setcolor завершено ---")
    print()


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
    # OWNER
    # --------------------------------------------------------

    if OWNER_ID and interaction.user.id != OWNER_ID:

        await interaction.response.send_message(
            "❌ У тебе немає прав на використання цієї команди!",
            ephemeral=True
        )

        return

    # --------------------------------------------------------
    # SERVER
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
    # DELETE
    # --------------------------------------------------------

    role_id_text = str(role.id)

    conn = None

    try:

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            DELETE FROM role_presets
            WHERE role_id = ?
            """,
            (
                role_id_text,
            )
        )

        conn.commit()

        deleted = cursor.rowcount

    except Exception as e:

        if conn:

            conn.close()

        await interaction.response.send_message(
            f"❌ Помилка:\n```{e}```",
            ephemeral=True
        )

        return

    finally:

        if conn:

            conn.close()

    # --------------------------------------------------------
    # RESPONSE
    # --------------------------------------------------------

    if deleted:

        await interaction.response.send_message(
            f"🗑️ Роль {role.mention} "
            f"(ID: `{role_id_text}`) "
            f"видалена із системи переливу."
        )

    else:

        await interaction.response.send_message(
            f"ℹ️ Роль {role.mention} "
            f"(ID: `{role_id_text}`) "
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

    if (
        ALLOWED_GUILD_ID
        and interaction.guild_id != ALLOWED_GUILD_ID
    ):

        await interaction.response.send_message(
            "❌ Ця команда недоступна на цьому сервері.",
            ephemeral=True
        )

        return

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
        f"❌ Slash command error: {error}"
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
            "❌ Не знайдено DISCORD_TOKEN!"
        )

        exit(1)

    if not TURSO_URL:

        print(
            "❌ Не знайдено TURSO_DATABASE_URL!"
        )

        exit(1)

    if not TURSO_AUTH_TOKEN:

        print(
            "❌ Не знайдено TURSO_AUTH_TOKEN!"
        )

        exit(1)

    print(
        "🚀 Запуск Rainbow Bot..."
    )

    bot.run(TOKEN)
