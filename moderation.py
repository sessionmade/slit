import discord
from discord.ext import commands
from src.config import Config


class Moderation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="ban")
    @commands.has_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    async def ban(self, ctx, member: discord.Member, *, reason: str = "No reason provided"):
        """Ban a member from the server"""
        
        # Can't ban yourself
        if member == ctx.author:
            return await ctx.send("You can't ban yourself.")
        
        # Can't ban the bot
        if member == ctx.guild.me:
            return await ctx.send("I can't ban myself.")
        
        # Role hierarchy check
        if member.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
            return await ctx.send("You can't ban someone with a higher or equal role.")
        
        if member.top_role >= ctx.guild.me.top_role:
            return await ctx.send("I can't ban someone with a higher or equal role than me.")

        # Try to DM the user before banning
        try:
            dm_embed = discord.Embed(
                title="You have been banned",
                description=f"You were banned from **{ctx.guild.name}**",
                color=discord.Color.red()
            )
            dm_embed.add_field(name="Reason", value=reason, inline=False)
            dm_embed.add_field(name="Moderator", value=str(ctx.author), inline=False)
            await member.send(embed=dm_embed)
        except:
            pass  # DMs might be closed

        await member.ban(reason=f"{ctx.author}: {reason}")

        embed = discord.Embed(
            title="Member Banned",
            description=f"**{member}** has been banned.",
            color=discord.Color.red()
        )
        embed.add_field(name="Reason", value=reason, inline=False)
        embed.add_field(name="Moderator", value=ctx.author.mention, inline=False)
        
        await ctx.send(embed=embed)

    @ban.error
    async def ban_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("You don't have permission to ban members.")
        elif isinstance(error, commands.BotMissingPermissions):
            await ctx.send("I don't have permission to ban members.")
        elif isinstance(error, commands.MemberNotFound):
            await ctx.send("Member not found.")
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(f"Usage: `{Config.PREFIX}ban <member> [reason]`")


async def setup(bot):
    await bot.add_cog(Moderation(bot))
