import discord
import copy
from discord.ext import commands
from src.config import Config
from datetime import datetime, timezone


class ClearConfirmView(discord.ui.View):
    def __init__(self, author: discord.Member, cog, guild_id: int):
        super().__init__(timeout=30)
        self.author = author
        self.cog = cog
        self.guild_id = guild_id
        self.message = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("can't use this fam", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except:
                pass

    @discord.ui.button(label="Yes, clear all", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Remove from database
        async with self.cog.bot.db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "DELETE FROM command_aliases WHERE guild_id = %s",
                    (self.guild_id,)
                )

        # Clear cache
        self.cog.cache[self.guild_id] = {}

        embed = discord.Embed(
            description=f"{Config.EMOJIS.SUCCESS} {self.author.mention}: Cleared all aliases",
            color=Config.COLORS.SUCCESS
        )
        await interaction.response.edit_message(embed=embed, view=None)
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            description=f"{Config.EMOJIS.ERROR} {self.author.mention}: Cancelled",
            color=Config.COLORS.ERROR
        )
        await interaction.response.edit_message(embed=embed, view=None)
        self.stop()


class Alias(commands.Cog):
    """Command alias management"""

    def __init__(self, bot):
        self.bot = bot
        self.cache = {}  # guild_id -> {alias: command}
        bot.loop.create_task(self.setup_table())

    async def setup_table(self):
        """Create the aliases table if it doesn't exist"""
        await self.bot.wait_until_ready()
        if not self.bot.db_pool:
            return

        async with self.bot.db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("""
                    CREATE TABLE IF NOT EXISTS command_aliases (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        guild_id BIGINT NOT NULL,
                        alias_name VARCHAR(100) NOT NULL,
                        command_name VARCHAR(100) NOT NULL,
                        UNIQUE KEY unique_alias (guild_id, alias_name)
                    )
                """)

        await self.load_cache()

    async def load_cache(self):
        """Load all aliases into cache"""
        if not self.bot.db_pool:
            return

        async with self.bot.db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT guild_id, alias_name, command_name FROM command_aliases")
                rows = await cur.fetchall()

                for guild_id, alias_name, command_name in rows:
                    if guild_id not in self.cache:
                        self.cache[guild_id] = {}
                    self.cache[guild_id][alias_name] = command_name

    def resolve_alias(self, guild_id: int, alias: str) -> str | None:
        """Get the real command for an alias"""
        if guild_id not in self.cache:
            return None
        return self.cache[guild_id].get(alias.lower())

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Listen for alias usage"""
        if message.author.bot or not message.guild:
            return

        prefixes = await self.bot.get_prefix(message)
        if isinstance(prefixes, str):
            prefixes = [prefixes]

        used_prefix = next((p for p in prefixes if message.content.startswith(p)), None)
        if not used_prefix:
            return

        tokens = message.content[len(used_prefix):].split(maxsplit=1)
        if not tokens:
            return

        alias = tokens[0].lower()
        real = self.resolve_alias(message.guild.id, alias)

        if real:
            rest = tokens[1] if len(tokens) > 1 else ""
            new_content = f"{used_prefix}{real} {rest}".strip()

            fake = copy.copy(message)
            fake.content = new_content

            ctx = await self.bot.get_context(fake)
            await self.bot.invoke(ctx)

    @commands.group(name="alias", invoke_without_command=True)
    @commands.cooldown(1, 4, commands.BucketType.user)
    @commands.has_permissions(manage_guild=True)
    async def alias(self, ctx):
        """Manage command aliases"""
        await ctx.send_help(ctx.command)

    @alias.command(name="add", aliases=["create"])
    @commands.has_permissions(manage_guild=True)
    async def alias_add(self, ctx, command: str = None, alias: str = None):
        """Add an alias for a command"""
        if not command or not alias:
            return await ctx.send_help(ctx.command)

        command, alias = command.lower(), alias.lower()

        # Validate command exists
        if not self.bot.get_command(command):
            return await ctx.warn(f"Command **{command}** not found")

        # Check if alias conflicts with existing command
        if self.bot.get_command(alias):
            return await ctx.deny(f"**{alias}** is already a command")

        # Check if alias already exists
        if self.resolve_alias(ctx.guild.id, alias):
            return await ctx.deny(f"Alias **{alias}** already exists")

        # Add to database
        async with self.bot.db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("""
                    INSERT INTO command_aliases (guild_id, alias_name, command_name)
                    VALUES (%s, %s, %s)
                """, (ctx.guild.id, alias, command))

        # Update cache
        if ctx.guild.id not in self.cache:
            self.cache[ctx.guild.id] = {}
        self.cache[ctx.guild.id][alias] = command

        await ctx.approve(f"Added alias **{alias}** → **{command}**")

    @alias.command(name="remove", aliases=["delete", "del"])
    @commands.has_permissions(manage_guild=True)
    async def alias_remove(self, ctx, alias: str = None):
        """Remove an alias"""
        if not alias:
            return await ctx.send_help(ctx.command)

        alias = alias.lower()

        # Check if alias exists
        if not self.resolve_alias(ctx.guild.id, alias):
            return await ctx.warn(f"Alias **{alias}** not found")

        # Remove from database
        async with self.bot.db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("""
                    DELETE FROM command_aliases
                    WHERE guild_id = %s AND alias_name = %s
                """, (ctx.guild.id, alias))

        # Update cache
        if ctx.guild.id in self.cache and alias in self.cache[ctx.guild.id]:
            del self.cache[ctx.guild.id][alias]

        await ctx.approve(f"Removed alias **{alias}**")

    @alias.command(name="list", aliases=["all", "view"])
    async def alias_list(self, ctx):
        """View all aliases"""
        if ctx.guild.id not in self.cache or not self.cache[ctx.guild.id]:
            return await ctx.warn("No aliases configured")

        aliases = self.cache[ctx.guild.id]
        lines = [f"`{a}` → `{c}`" for a, c in aliases.items()]

        embed = discord.Embed(
            description="\n".join(lines),
            color=Config.COLORS.DEFAULT,
            timestamp=datetime.now(timezone.utc)
        )
        embed.set_author(name="Configured Aliases", icon_url=self.bot.user.display_avatar.url)
        embed.set_footer(text=f"{len(aliases)} aliases")

        await ctx.send(embed=embed)

    @alias.command(name="clear")
    @commands.has_permissions(manage_guild=True)
    async def alias_clear(self, ctx):
        """Clear all aliases"""
        if ctx.guild.id not in self.cache or not self.cache[ctx.guild.id]:
            return await ctx.warn("No aliases to clear")

        alias_count = len(self.cache[ctx.guild.id])

        embed = discord.Embed(
            description=f"Are you sure you want to clear **{alias_count}** aliases?\nThis action cannot be undone.",
            color=Config.COLORS.WARNING
        )
        embed.set_author(name="Clear All Aliases", icon_url=ctx.author.display_avatar.url)

        view = ClearConfirmView(ctx.author, self, ctx.guild.id)
        view.message = await ctx.send(embed=embed, view=view)


async def setup(bot):
    await bot.add_cog(Alias(bot))
