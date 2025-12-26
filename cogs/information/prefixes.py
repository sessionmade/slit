import discord
import json
import asyncio
from discord.ext import commands
from src.config import Config


class Prefixes(commands.Cog):
    """Manage per-guild and per-user prefixes for the bot."""

    def __init__(self, bot):
        self.bot = bot
        self.path = "src/prefixes.json"
        bot.loop.create_task(self._ensure_loaded())

    async def _ensure_loaded(self):
        await self.bot.wait_until_ready()
        if not hasattr(self.bot, 'prefixes'):
            self.bot.prefixes = {"guilds": {}, "users": {}}

        loop = asyncio.get_event_loop()

        def _read():
            try:
                with open(self.path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except FileNotFoundError:
                return {}
            except Exception:
                return {}

        data = await loop.run_in_executor(None, _read)
        if isinstance(data, dict):
            # Merge loaded values into bot.prefixes
            self.bot.prefixes.setdefault('guilds', {})
            self.bot.prefixes.setdefault('users', {})
            if 'guilds' in data and isinstance(data['guilds'], dict):
                self.bot.prefixes['guilds'].update(data['guilds'])
            if 'users' in data and isinstance(data['users'], dict):
                self.bot.prefixes['users'].update(data['users'])

    async def _save(self):
        loop = asyncio.get_event_loop()

        def _write(d):
            with open(self.path, 'w', encoding='utf-8') as f:
                json.dump(d, f, ensure_ascii=False, indent=2)

        await loop.run_in_executor(None, _write, self.bot.prefixes)

    @commands.group(name='prefix', invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def prefix(self, ctx):
        """Show or manage guild prefix"""
        guild_p = self.bot.prefixes.get('guilds', {}).get(str(ctx.guild.id)) or Config.PREFIX
        await ctx.approve(f"Guild prefix is: **{guild_p}**")

    @prefix.command(name='set')
    @commands.has_permissions(manage_guild=True)
    async def prefix_set(self, ctx, new: str = None):
        if not new:
            return await ctx.send_help(ctx.command)
        self.bot.prefixes.setdefault('guilds', {})[str(ctx.guild.id)] = new
        await self._save()
        await ctx.approve(f"Set guild prefix to **{new}**")

    @prefix.command(name='reset')
    @commands.has_permissions(manage_guild=True)
    async def prefix_reset(self, ctx):
        g = self.bot.prefixes.get('guilds', {})
        if str(ctx.guild.id) in g:
            del g[str(ctx.guild.id)]
            await self._save()
            await ctx.approve("Reset guild prefix to default")
        else:
            await ctx.warn("No custom prefix set")

    @commands.group(name='selfprefix', invoke_without_command=True)
    async def selfprefix(self, ctx):
        """Show or manage your personal selfprefix (applies across guilds)."""
        up = self.bot.prefixes.get('users', {}).get(str(ctx.author.id))
        if not up:
            return await ctx.warn("You have no selfprefix set")
        await ctx.approve(f"Your selfprefix is **{up}**")

    @selfprefix.command(name='set')
    async def selfprefix_set(self, ctx, new: str = None):
        if not new:
            return await ctx.send_help(ctx.command)
        self.bot.prefixes.setdefault('users', {})[str(ctx.author.id)] = new
        await self._save()
        await ctx.approve(f"Set your selfprefix to **{new}**")

    @selfprefix.command(name='reset')
    async def selfprefix_reset(self, ctx):
        u = self.bot.prefixes.get('users', {})
        if str(ctx.author.id) in u:
            del u[str(ctx.author.id)]
            await self._save()
            await ctx.approve("Removed your selfprefix")
        else:
            await ctx.warn("You have no selfprefix set")


async def setup(bot):
    await bot.add_cog(Prefixes(bot))
