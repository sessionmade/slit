import discord
import json
import asyncio
from discord.ext import commands
from src.config import Config


class AutoResponder(commands.Cog):
	"""Guild-specific autoresponses: add/remove/list simple text triggers."""

	def __init__(self, bot):
		self.bot = bot
		self.path = "src/autoresponses.json"
		self.data: dict = {}
		bot.loop.create_task(self._load())

	async def _load(self):
		await self.bot.wait_until_ready()
		loop = asyncio.get_event_loop()

		def _read():
			try:
				with open(self.path, "r", encoding="utf-8") as f:
					return json.load(f)
			except FileNotFoundError:
				return {}
			except Exception:
				return {}

		self.data = await loop.run_in_executor(None, _read)

	async def _save(self):
		loop = asyncio.get_event_loop()

		def _write(d):
			with open(self.path, "w", encoding="utf-8") as f:
				json.dump(d, f, ensure_ascii=False, indent=2)

		await loop.run_in_executor(None, _write, self.data)

	def _get_guild(self, guild_id: int) -> dict:
		key = str(guild_id)
		if key not in self.data:
			self.data[key] = {}
		return self.data[key]

	@commands.Cog.listener()
	async def on_message(self, message: discord.Message):
		if message.author.bot or not message.guild:
			return

		guild_map = self._get_guild(message.guild.id)
		if not guild_map:
			return

		content = message.content.strip().lower()
		if not content:
			return

		response = guild_map.get(content)
		if response:
			try:
				resp = response.replace("{author}", message.author.mention)
				await message.channel.send(resp)
			except Exception:
				pass

	@commands.group(name="autoresponder", aliases=["at"], invoke_without_command=True)
	@commands.has_permissions(manage_guild=True)
	async def autoresponder(self, ctx):
		"""Manage autoresponses"""
		await ctx.send_help(ctx.command)

	@autoresponder.command(name="add")
	@commands.has_permissions(manage_guild=True)
	async def autoresponder_add(self, ctx, trigger: str = None, *, response: str = None):
		"""Add an autoresponse. Use quotes for multi-word triggers and responses.

		Example: ;autoresponder add "hello bot" "Hello {author}!"
		"""
		if not trigger or not response:
			return await ctx.send_help(ctx.command)

		trigger_key = trigger.strip().lower()
		guild_map = self._get_guild(ctx.guild.id)

		if trigger_key in guild_map:
			return await ctx.deny("That trigger already exists")

		guild_map[trigger_key] = response
		await self._save()
		await ctx.approve(f"Added autoresponse for **{trigger}**")

	@autoresponder.command(name="remove", aliases=["delete", "del"])
	@commands.has_permissions(manage_guild=True)
	async def autoresponder_remove(self, ctx, *, trigger: str = None):
		"""Remove an autoresponse by trigger"""
		if not trigger:
			return await ctx.send_help(ctx.command)

		trigger_key = trigger.strip().lower()
		guild_map = self._get_guild(ctx.guild.id)

		if trigger_key not in guild_map:
			return await ctx.warn("Trigger not found")

		del guild_map[trigger_key]
		await self._save()
		await ctx.approve(f"Removed autoresponse for **{trigger}**")

	@autoresponder.command(name="list", aliases=["all", "view"])
	async def autoresponder_list(self, ctx):
		"""List configured autoresponses for this guild"""
		guild_map = self._get_guild(ctx.guild.id)
		if not guild_map:
			return await ctx.warn("No autoresponses configured")

		lines = [f"**{t}** → {r}" for t, r in guild_map.items()]
		embed = discord.Embed(description="\n".join(lines), color=Config.COLORS.DEFAULT)
		embed.set_author(name="Autoresponses", icon_url=self.bot.user.display_avatar.url)
		await ctx.send(embed=embed)

	@autoresponder.command(name="clear")
	@commands.has_permissions(manage_guild=True)
	async def autoresponder_clear(self, ctx):
		"""Clear all autoresponses for this guild"""
		guild_map = self._get_guild(ctx.guild.id)
		if not guild_map:
			return await ctx.warn("No autoresponses to clear")

		guild_map.clear()
		await self._save()
		await ctx.approve("Cleared all autoresponses")


async def setup(bot):
    await bot.add_cog(AutoResponder(bot))