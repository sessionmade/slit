import discord
from discord.ext import commands
from discord.utils import utcnow
from datetime import timedelta
import re

class Moderation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ==================== ROLE COMMANDS ====================

    @commands.group(name="role", invoke_without_command=True)
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def role(self, ctx, member: discord.Member = None, *, role: discord.Role = None):
        """Add or remove a role from a member"""
        if not member:
            return await ctx.send_help(ctx.command)
        
        if not role:
            return await ctx.deny("You must specify a role.")
        
        # Role hierarchy checks
        if role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
            return await ctx.deny("You cannot manage a role higher or equal to your top role.")
        
        if role >= ctx.guild.me.top_role:
            return await ctx.deny(f"I cannot manage {role.mention}, it's higher than my top role.")
        
        if role in member.roles:
            await member.remove_roles(role, reason=f"Removed by {ctx.author}")
            await ctx.approve(f"Removed {role.mention} from **{member.display_name}**")
        else:
            await member.add_roles(role, reason=f"Added by {ctx.author}")
            await ctx.approve(f"Added {role.mention} to **{member.display_name}**")

    @role.command(name="create")
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def role_create(self, ctx, name: str = None, color: discord.Color = None, hoist: bool = False, mentionable: bool = False):
        """Create a new role"""
        if not name:
            return await ctx.send_help(ctx.command)
        
        role = await ctx.guild.create_role(
            name=name,
            colour=color or discord.Color.default(),
            hoist=hoist,
            mentionable=mentionable,
            reason=f"Created by {ctx.author}"
        )
        await ctx.approve(f"Created role {role.mention}")

    @role.command(name="delete")
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def role_delete(self, ctx, *, role: discord.Role = None):
        """Delete a role"""
        if not role:
            return await ctx.send_help(ctx.command)
        
        if role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
            return await ctx.deny("You cannot delete a role higher or equal to your top role.")
        
        if role >= ctx.guild.me.top_role:
            return await ctx.deny("I cannot delete a role higher than my top role.")
        
        role_name = role.name
        await role.delete(reason=f"Deleted by {ctx.author}")
        await ctx.approve(f"Deleted role **{role_name}**")

    @role.command(name="edit", aliases=["rename"])
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def role_edit(self, ctx, role: discord.Role = None, *, new_name: str = None):
        """Rename a role"""
        if not role or not new_name:
            return await ctx.deny("Please specify a role and a new name.")
        
        if role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
            return await ctx.deny("You cannot edit a role higher or equal to your top role.")
        
        if role >= ctx.guild.me.top_role:
            return await ctx.deny("I cannot edit a role higher than my top role.")
        
        old_name = role.name
        await role.edit(name=new_name, reason=f"Edited by {ctx.author}")
        await ctx.approve(f"Renamed **{old_name}** to **{new_name}**")

    @role.command(name="color", aliases=["colour"])
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def role_color(self, ctx, role: discord.Role = None, *, color: discord.Color = None):
        """Change a role's color"""
        if not role or not color:
            return await ctx.deny("Please specify a role and a color.")
        
        if role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
            return await ctx.deny("You cannot edit a role higher or equal to your top role.")
        
        if role >= ctx.guild.me.top_role:
            return await ctx.deny("I cannot edit a role higher than my top role.")
        
        await role.edit(color=color, reason=f"Color changed by {ctx.author}")
        await ctx.approve(f"Changed {role.mention} color to **{color}**")

    @role.command(name="mentionable")
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def role_mentionable(self, ctx, *, role: discord.Role = None):
        """Toggle whether a role is mentionable"""
        if not role:
            return await ctx.deny("Please specify a role.")
        
        if role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
            return await ctx.deny("You cannot manage a role higher or equal to your top role.")
        
        if role >= ctx.guild.me.top_role:
            return await ctx.deny("I cannot manage a role higher than my top role.")
        
        new_state = not role.mentionable
        await role.edit(mentionable=new_state, reason=f"Toggled by {ctx.author}")
        state_text = "mentionable" if new_state else "not mentionable"
        await ctx.approve(f"{role.mention} is now **{state_text}**")

    @role.command(name="hoist")
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def role_hoist(self, ctx, *, role: discord.Role = None):
        """Toggle whether a role is displayed separately"""
        if not role:
            return await ctx.deny("Please specify a role.")
        
        if role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
            return await ctx.deny("You cannot manage a role higher or equal to your top role.")
        
        if role >= ctx.guild.me.top_role:
            return await ctx.deny("I cannot manage a role higher than my top role.")
        
        new_state = not role.hoist
        await role.edit(hoist=new_state, reason=f"Toggled by {ctx.author}")
        state_text = "hoisted" if new_state else "not hoisted"
        await ctx.approve(f"{role.mention} is now **{state_text}**")

    @role.group(name="has", invoke_without_command=True)
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def role_has(self, ctx, has_role: discord.Role = None, assign_role: discord.Role = None):
        """Add a role to all members with a specific role"""
        if not has_role or not assign_role:
            return await ctx.deny("Please specify both roles.")
        
        if assign_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
            return await ctx.deny("You cannot assign a role higher or equal to your top role.")
        
        if assign_role >= ctx.guild.me.top_role:
            return await ctx.deny("I cannot assign a role higher than my top role.")
        
        members = [m for m in ctx.guild.members if has_role in m.roles and assign_role not in m.roles]
        if not members:
            return await ctx.deny(f"No members with {has_role.mention} need {assign_role.mention}.")
        
        count = 0
        for member in members:
            try:
                await member.add_roles(assign_role, reason=f"Role has by {ctx.author}")
                count += 1
            except:
                pass
        
        await ctx.approve(f"Added {assign_role.mention} to **{count}** members with {has_role.mention}")

    @role_has.command(name="remove")
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def role_has_remove(self, ctx, has_role: discord.Role = None, remove_role: discord.Role = None):
        """Remove a role from all members with a specific role"""
        if not has_role or not remove_role:
            return await ctx.deny("Please specify both roles.")
        
        if remove_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
            return await ctx.deny("You cannot remove a role higher or equal to your top role.")
        
        if remove_role >= ctx.guild.me.top_role:
            return await ctx.deny("I cannot remove a role higher than my top role.")
        
        members = [m for m in ctx.guild.members if has_role in m.roles and remove_role in m.roles]
        if not members:
            return await ctx.deny(f"No members have both {has_role.mention} and {remove_role.mention}.")
        
        count = 0
        for member in members:
            try:
                await member.remove_roles(remove_role, reason=f"Role has remove by {ctx.author}")
                count += 1
            except:
                pass
        
        await ctx.approve(f"Removed {remove_role.mention} from **{count}** members with {has_role.mention}")

    @role.command(name="bots")
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def role_bots(self, ctx, *, role: discord.Role = None):
        """Add a role to all bots"""
        if not role:
            return await ctx.deny("Please specify a role.")
        
        if role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
            return await ctx.deny("You cannot assign a role higher or equal to your top role.")
        
        if role >= ctx.guild.me.top_role:
            return await ctx.deny("I cannot assign a role higher than my top role.")
        
        bots = [m for m in ctx.guild.members if m.bot and role not in m.roles]
        if not bots:
            return await ctx.deny("No bots need this role.")
        
        count = 0
        for bot in bots:
            try:
                await bot.add_roles(role, reason=f"Role bots by {ctx.author}")
                count += 1
            except:
                pass
        
        await ctx.approve(f"Added {role.mention} to **{count}** bots")

    @role.command(name="humans")
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def role_humans(self, ctx, *, role: discord.Role = None):
        """Add a role to all humans"""
        if not role:
            return await ctx.deny("Please specify a role.")
        
        if role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
            return await ctx.deny("You cannot assign a role higher or equal to your top role.")
        
        if role >= ctx.guild.me.top_role:
            return await ctx.deny("I cannot assign a role higher than my top role.")
        
        humans = [m for m in ctx.guild.members if not m.bot and role not in m.roles]
        if not humans:
            return await ctx.deny("No humans need this role.")
        
        count = 0
        for human in humans:
            try:
                await human.add_roles(role, reason=f"Role humans by {ctx.author}")
                count += 1
            except:
                pass
        
        await ctx.approve(f"Added {role.mention} to **{count}** humans")

    @role.command(name="all")
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def role_all(self, ctx, *, role: discord.Role = None):
        """Add a role to all members"""
        if not role:
            return await ctx.deny("Please specify a role.")
        
        if role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
            return await ctx.deny("You cannot assign a role higher or equal to your top role.")
        
        if role >= ctx.guild.me.top_role:
            return await ctx.deny("I cannot assign a role higher than my top role.")
        
        members = [m for m in ctx.guild.members if role not in m.roles]
        if not members:
            return await ctx.deny("All members already have this role.")
        
        count = 0
        for member in members:
            try:
                await member.add_roles(role, reason=f"Role all by {ctx.author}")
                count += 1
            except:
                pass
        
        await ctx.approve(f"Added {role.mention} to **{count}** members")

    @role.command(name="info")
    @commands.has_permissions(manage_roles=True)
    async def role_info(self, ctx, *, role: discord.Role = None):
        """Get information about a role"""
        if not role:
            return await ctx.deny("Please specify a role.")
        
        members_with_role = len([m for m in ctx.guild.members if role in m.roles])
        
        embed = discord.Embed(
            title=role.name,
            color=role.color
        )
        embed.add_field(name="ID", value=role.id, inline=True)
        embed.add_field(name="Color", value=str(role.color), inline=True)
        embed.add_field(name="Members", value=members_with_role, inline=True)
        embed.add_field(name="Mentionable", value="Yes" if role.mentionable else "No", inline=True)
        embed.add_field(name="Hoisted", value="Yes" if role.hoist else "No", inline=True)
        embed.add_field(name="Position", value=role.position, inline=True)
        embed.add_field(name="Created", value=f"<t:{int(role.created_at.timestamp())}:R>", inline=True)
        
        await ctx.send(embed=embed)

    # ==================== MODERATION COMMANDS ====================
    
    def parse_time(self, time_str: str) -> timedelta:
        """Parse time string like '10m', '1h', '2d' into timedelta"""
        time_regex = re.compile(r"(\d+)([smhd])")
        matches = time_regex.findall(time_str.lower())
        
        if not matches:
            return None
        
        total_seconds = 0
        for value, unit in matches:
            value = int(value)
            if unit == 's':
                total_seconds += value
            elif unit == 'm':
                total_seconds += value * 60
            elif unit == 'h':
                total_seconds += value * 3600
            elif unit == 'd':
                total_seconds += value * 86400
        
        return timedelta(seconds=total_seconds)
    
    @commands.command(name="ban")
    @commands.has_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    async def ban(self, ctx, member: discord.Member, *, reason: str = "No reason provided"):
        """Ban a member from the server"""
        
        # Can't ban yourself
        if member == ctx.author:
            return await ctx.deny("You can't ban yourself.")
        
        # Can't ban the bot
        if member == ctx.guild.me:
            return await ctx.deny("I can't ban myself.")
        
        # Role hierarchy check
        if member.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
            return await ctx.deny("You can't ban someone with a higher or equal role.")
        
        if member.top_role >= ctx.guild.me.top_role:
            return await ctx.deny("I can't ban someone with a higher or equal role than me.")
        
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
        await ctx.approve(f"Banned **{member}** for **{reason}**")
    
    @commands.command(name="kick")
    @commands.has_permissions(kick_members=True)
    @commands.bot_has_permissions(kick_members=True)
    async def kick(self, ctx, member: discord.Member, *, reason: str = "No reason provided"):
        """Kick a member from the server"""
        
        # Can't kick yourself
        if member == ctx.author:
            return await ctx.deny("You can't kick yourself.")
        
        # Can't kick the bot
        if member == ctx.guild.me:
            return await ctx.deny("I can't kick myself.")
        
        # Role hierarchy check
        if member.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
            return await ctx.deny("You can't kick someone with a higher or equal role.")
        
        if member.top_role >= ctx.guild.me.top_role:
            return await ctx.deny("I can't kick someone with a higher or equal role than me.")
        
        # Try to DM the user before kicking
        try:
            dm_embed = discord.Embed(
                title="You have been kicked",
                description=f"You were kicked from **{ctx.guild.name}**",
                color=discord.Color.red()
            )
            dm_embed.add_field(name="Reason", value=reason, inline=False)
            dm_embed.add_field(name="Moderator", value=str(ctx.author), inline=False)
            await member.send(embed=dm_embed)
        except:
            pass  # DMs might be closed
        
        await member.kick(reason=f"{ctx.author}: {reason}")
        await ctx.approve(f"Kicked **{member}** for **{reason}**")
    
    @commands.command(name="timeout", aliases=["mute", "to"])
    @commands.has_permissions(moderate_members=True)
    @commands.bot_has_permissions(moderate_members=True)
    async def timeout(self, ctx, member: discord.Member, duration: str, *, reason: str = "No reason provided"):
        """Timeout a member from the server
        
        Duration format: 10s, 5m, 2h, 1d
        """
        
        # Can't timeout yourself
        if member == ctx.author:
            return await ctx.deny("You can't timeout yourself.")
        
        # Can't timeout the bot
        if member == ctx.guild.me:
            return await ctx.deny("I can't timeout myself.")
        
        # Role hierarchy check
        if member.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
            return await ctx.deny("You can't timeout someone with a higher or equal role.")
        
        if member.top_role >= ctx.guild.me.top_role:
            return await ctx.deny("I can't timeout someone with a higher or equal role than me.")
        
        # Parse duration
        time_delta = self.parse_time(duration)
        if not time_delta:
            return await ctx.deny("Invalid duration format. Use formats like: **10s**, **5m**, **2h**, **1d**")
        
        # Discord max timeout is 28 days
        if time_delta > timedelta(days=28):
            return await ctx.deny("Timeout duration cannot exceed **28 days**.")
        
        # Try to DM the user before timing out
        try:
            dm_embed = discord.Embed(
                title="You have been timed out",
                description=f"You were timed out in **{ctx.guild.name}**",
                color=discord.Color.red()
            )
            dm_embed.add_field(name="Duration", value=duration, inline=False)
            dm_embed.add_field(name="Reason", value=reason, inline=False)
            dm_embed.add_field(name="Moderator", value=str(ctx.author), inline=False)
            await member.send(embed=dm_embed)
        except:
            pass  # DMs might be closed
        
        await member.timeout(time_delta, reason=f"{ctx.author}: {reason}")
        await ctx.approve(f"Timed out **{member}** for **{duration}**")
    
    @commands.command(name="untimeout", aliases=["unmute", "uto"])
    @commands.has_permissions(moderate_members=True)
    @commands.bot_has_permissions(moderate_members=True)
    async def untimeout(self, ctx, member: discord.Member, *, reason: str = "No reason provided"):
        """Remove timeout from a member"""
        
        # Check if member is actually timed out
        if member.timed_out_until is None:
            return await ctx.deny(f"**{member}** is not timed out.")
        
        # Role hierarchy check
        if member.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
            return await ctx.deny("You can't untimeout someone with a higher or equal role.")
        
        if member.top_role >= ctx.guild.me.top_role:
            return await ctx.deny("I can't untimeout someone with a higher or equal role than me.")
        
        # Try to DM the user
        try:
            dm_embed = discord.Embed(
                title="Your timeout has been removed",
                description=f"Your timeout in **{ctx.guild.name}** has been removed",
                color=discord.Color.green()
            )
            dm_embed.add_field(name="Reason", value=reason, inline=False)
            dm_embed.add_field(name="Moderator", value=str(ctx.author), inline=False)
            await member.send(embed=dm_embed)
        except:
            pass  # DMs might be closed
        
        await member.timeout(None, reason=f"{ctx.author}: {reason}")
        await ctx.approve(f"Removed timeout from **{member}**")
    
    @commands.command(name="lock")
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def lock(self, ctx, channel: discord.TextChannel = None, *, reason: str = "No reason provided"):
        """Lock a channel to prevent members from sending messages"""
        channel = channel or ctx.channel
        
        # Check if already locked
        overwrite = channel.overwrites_for(ctx.guild.default_role)
        if overwrite.send_messages is False:
            return await ctx.deny(f"{channel.mention} is already locked.")
        
        overwrite.send_messages = False
        await channel.set_permissions(ctx.guild.default_role, overwrite=overwrite, reason=f"{ctx.author}: {reason}")
        await ctx.approve(f"Locked {channel.mention}")
    
    @commands.command(name="unlock")
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def unlock(self, ctx, channel: discord.TextChannel = None, *, reason: str = "No reason provided"):
        """Unlock a channel to allow members to send messages"""
        channel = channel or ctx.channel
        
        # Check if already unlocked
        overwrite = channel.overwrites_for(ctx.guild.default_role)
        if overwrite.send_messages is not False:
            return await ctx.deny(f"{channel.mention} is not locked.")
        
        overwrite.send_messages = None
        await channel.set_permissions(ctx.guild.default_role, overwrite=overwrite, reason=f"{ctx.author}: {reason}")
        await ctx.approve(f"Unlocked {channel.mention}")
    
    @commands.command(name="slowmode", aliases=["sm"])
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def slowmode(self, ctx, duration: str = None, channel: discord.TextChannel = None):
        """Set slowmode for a channel
        
        Duration format: 0 (off), 5s, 10m, 1h, 6h (max)
        """
        channel = channel or ctx.channel
        
        # If no duration, show current slowmode
        if duration is None:
            current = channel.slowmode_delay
            if current == 0:
                return await ctx.approve(f"Slowmode is **off** in {channel.mention}")
            return await ctx.approve(f"Slowmode is **{current}s** in {channel.mention}")
        
        # Turn off slowmode
        if duration == "0" or duration.lower() == "off":
            await channel.edit(slowmode_delay=0)
            return await ctx.approve(f"Disabled slowmode in {channel.mention}")
        
        # Parse duration
        time_delta = self.parse_time(duration)
        if not time_delta:
            return await ctx.deny("Invalid duration format. Use formats like: **5s**, **10m**, **1h**")
        
        seconds = int(time_delta.total_seconds())
        
        # Discord max slowmode is 6 hours (21600 seconds)
        if seconds > 21600:
            return await ctx.deny("Slowmode cannot exceed **6 hours**.")
        
        await channel.edit(slowmode_delay=seconds)
        await ctx.approve(f"Set slowmode to **{duration}** in {channel.mention}")
    
    @commands.command(name="nuke")
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def nuke(self, ctx, channel: discord.TextChannel = None):
        """Nuke a channel (clone and delete to wipe all messages)"""
        channel = channel or ctx.channel
        
        # Create confirmation embed
        embed = discord.Embed(
            title="Channel Nuke Confirmation",
            description=f"Are you sure you want to nuke {channel.mention}?\nThis will delete **all** messages permanently.",
            color=discord.Color.orange()
        )
        embed.set_footer(text=f"Requested by {ctx.author}", icon_url=ctx.author.display_avatar.url)
        
        # Create buttons
        view = NukeConfirmView(ctx.author, channel)
        view.message = await ctx.send(embed=embed, view=view)
    
    @commands.command(name="nickname", aliases=["nick"])
    @commands.has_permissions(manage_nicknames=True)
    @commands.bot_has_permissions(manage_nicknames=True)
    async def nickname(self, ctx, member: discord.Member, *, nickname: str = None):
        """Change a member's nickname"""
        
        # Role hierarchy check
        if member.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
            return await ctx.deny("You can't change the nickname of someone with a higher or equal role.")
        
        if member.top_role >= ctx.guild.me.top_role:
            return await ctx.deny("I can't change the nickname of someone with a higher or equal role than me.")
        
        old_nick = member.display_name
        await member.edit(nick=nickname)
        
        if nickname:
            await ctx.approve(f"Changed **{member}**'s nickname from **{old_nick}** to **{nickname}**")
        else:
            await ctx.approve(f"Reset **{member}**'s nickname")

    @commands.command(name="unban")
    @commands.has_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    async def unban(self, ctx, user: str, *, reason: str = "No reason provided"):
        """Unban a user by ID or mention"""
        
        # Extract user ID from mention or raw ID
        user_id = user.strip("<@!>")
        try:
            user_id = int(user_id)
        except ValueError:
            return await ctx.deny("Please provide a valid user ID or mention.")

        # Check if user is actually banned
        try:
            ban_entry = await ctx.guild.fetch_ban(discord.Object(id=user_id))
        except discord.NotFound:
            return await ctx.deny("That user is not banned.")
        except discord.Forbidden:
            return await ctx.deny("I don't have permission to view bans.")

        # Unban the user
        await ctx.guild.unban(ban_entry.user, reason=f"{ctx.author}: {reason}")
        await ctx.approve(f"Unbanned **{ban_entry.user}** for **{reason}**")

    @commands.command(name="softban")
    @commands.has_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    async def softban(self, ctx, member: discord.Member, *, reason: str = "No reason provided"):
        """Softban a member - bans and unbans to delete their last 7 days of messages"""
        
        # Can't softban yourself
        if member == ctx.author:
            return await ctx.deny("You can't softban yourself.")
        
        # Can't softban the bot
        if member == ctx.guild.me:
            return await ctx.deny("I can't softban myself.")
        
        # Role hierarchy check
        if member.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
            return await ctx.deny("You can't softban someone with a higher or equal role.")
        
        if member.top_role >= ctx.guild.me.top_role:
            return await ctx.deny("I can't softban someone with a higher or equal role than me.")

        # Try to DM the user before softbanning
        try:
            dm_embed = discord.Embed(
                title="You have been softbanned",
                description=f"You were softbanned from **{ctx.guild.name}**\nYou can rejoin, but your messages from the last 7 days have been deleted.",
                color=discord.Color.orange()
            )
            dm_embed.add_field(name="Reason", value=reason, inline=False)
            dm_embed.add_field(name="Moderator", value=str(ctx.author), inline=False)
            await member.send(embed=dm_embed)
        except:
            pass  # DMs might be closed

        # Ban with 7 days message deletion, then immediately unban
        await member.ban(reason=f"Softban by {ctx.author}: {reason}", delete_message_days=7)
        await ctx.guild.unban(member, reason=f"Softban by {ctx.author}: {reason}")
        await ctx.approve(f"Softbanned **{member}** for **{reason}**")

    @commands.group(name="purge", aliases=["clear", "prune"], invoke_without_command=True)
    @commands.has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True)
    async def purge(self, ctx, amount: int = None):
        """Delete a specified amount of messages"""
        if not amount:
            return await ctx.deny("Please specify the number of messages to delete.")
        
        if amount < 1 or amount > 1000:
            return await ctx.deny("Amount must be between **1** and **1000**.")
        
        await ctx.message.delete()
        deleted = await ctx.channel.purge(limit=amount)
        msg = await ctx.approve(f"Deleted **{len(deleted)}** messages")
        await msg.delete(delay=3)

    @purge.command(name="user")
    @commands.has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True)
    async def purge_user(self, ctx, member: discord.Member, amount: int = 100):
        """Delete messages from a specific user"""
        if amount < 1 or amount > 1000:
            return await ctx.deny("Amount must be between **1** and **1000**.")
        
        await ctx.message.delete()
        deleted = await ctx.channel.purge(limit=amount, check=lambda m: m.author == member)
        msg = await ctx.approve(f"Deleted **{len(deleted)}** messages from **{member}**")
        await msg.delete(delay=3)

    @purge.command(name="bots")
    @commands.has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True)
    async def purge_bots(self, ctx, amount: int = 100):
        """Delete messages from bots"""
        if amount < 1 or amount > 1000:
            return await ctx.deny("Amount must be between **1** and **1000**.")
        
        await ctx.message.delete()
        deleted = await ctx.channel.purge(limit=amount, check=lambda m: m.author.bot)
        msg = await ctx.approve(f"Deleted **{len(deleted)}** bot messages")
        await msg.delete(delay=3)

    @purge.command(name="contains")
    @commands.has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True)
    async def purge_contains(self, ctx, *, text: str):
        """Delete messages containing specific text"""
        await ctx.message.delete()
        deleted = await ctx.channel.purge(limit=100, check=lambda m: text.lower() in m.content.lower())
        msg = await ctx.approve(f"Deleted **{len(deleted)}** messages containing **{text}**")
        await msg.delete(delay=3)

    @purge.command(name="embeds")
    @commands.has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True)
    async def purge_embeds(self, ctx, amount: int = 100):
        """Delete messages with embeds"""
        if amount < 1 or amount > 1000:
            return await ctx.deny("Amount must be between **1** and **1000**.")
        
        await ctx.message.delete()
        deleted = await ctx.channel.purge(limit=amount, check=lambda m: len(m.embeds) > 0)
        msg = await ctx.approve(f"Deleted **{len(deleted)}** messages with embeds")
        await msg.delete(delay=3)

    @purge.command(name="files", aliases=["attachments"])
    @commands.has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True)
    async def purge_files(self, ctx, amount: int = 100):
        """Delete messages with attachments"""
        if amount < 1 or amount > 1000:
            return await ctx.deny("Amount must be between **1** and **1000**.")
        
        await ctx.message.delete()
        deleted = await ctx.channel.purge(limit=amount, check=lambda m: len(m.attachments) > 0)
        msg = await ctx.approve(f"Deleted **{len(deleted)}** messages with attachments")
        await msg.delete(delay=3)

    @commands.command(name="warn")
    @commands.has_permissions(moderate_members=True)
    async def warn(self, ctx, member: discord.Member, *, reason: str = "No reason provided"):
        """Warn a member"""
        if member == ctx.author:
            return await ctx.deny("You can't warn yourself.")
        if member == ctx.guild.me:
            return await ctx.deny("I can't warn myself.")
        if member.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
            return await ctx.deny("You can't warn someone with a higher or equal role.")

        # Store warning in database
        async with self.bot.db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("""
                    CREATE TABLE IF NOT EXISTS warnings (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        guild_id BIGINT,
                        user_id BIGINT,
                        moderator_id BIGINT,
                        reason VARCHAR(500),
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                await cur.execute(
                    "INSERT INTO warnings (guild_id, user_id, moderator_id, reason) VALUES (%s, %s, %s, %s)",
                    (ctx.guild.id, member.id, ctx.author.id, reason)
                )
                await cur.execute(
                    "SELECT COUNT(*) FROM warnings WHERE guild_id = %s AND user_id = %s",
                    (ctx.guild.id, member.id)
                )
                count = (await cur.fetchone())[0]

        try:
            dm_embed = discord.Embed(
                title="You have been warned",
                description=f"You were warned in **{ctx.guild.name}**",
                color=discord.Color.orange()
            )
            dm_embed.add_field(name="Reason", value=reason, inline=False)
            dm_embed.add_field(name="Moderator", value=str(ctx.author), inline=False)
            dm_embed.add_field(name="Total Warnings", value=str(count), inline=False)
            await member.send(embed=dm_embed)
        except:
            pass

        await ctx.approve(f"Warned **{member}** for **{reason}** (Warning #{count})")

    @commands.command(name="warnings", aliases=["warns"])
    @commands.has_permissions(moderate_members=True)
    async def warnings(self, ctx, member: discord.Member = None):
        """View warnings for a member"""
        member = member or ctx.author
        
        async with self.bot.db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("""
                    CREATE TABLE IF NOT EXISTS warnings (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        guild_id BIGINT,
                        user_id BIGINT,
                        moderator_id BIGINT,
                        reason VARCHAR(500),
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                await cur.execute(
                    "SELECT id, moderator_id, reason, timestamp FROM warnings WHERE guild_id = %s AND user_id = %s ORDER BY timestamp DESC",
                    (ctx.guild.id, member.id)
                )
                warns = await cur.fetchall()

        if not warns:
            return await ctx.deny(f"**{member}** has no warnings.")

        embed = discord.Embed(
            title=f"Warnings for {member}",
            color=discord.Color.orange()
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        
        for warn_id, mod_id, reason, timestamp in warns[:10]:
            mod = ctx.guild.get_member(mod_id) or f"Unknown ({mod_id})"
            embed.add_field(
                name=f"Warning #{warn_id}",
                value=f"**Reason:** {reason}\n**Moderator:** {mod}\n**Date:** <t:{int(timestamp.timestamp())}:R>",
                inline=False
            )
        
        embed.set_footer(text=f"Total: {len(warns)} warning(s)")
        await ctx.send(embed=embed)

    @commands.command(name="clearwarnings", aliases=["clearwarns", "resetwarns"])
    @commands.has_permissions(administrator=True)
    async def clearwarnings(self, ctx, member: discord.Member):
        """Clear all warnings for a member"""
        async with self.bot.db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "DELETE FROM warnings WHERE guild_id = %s AND user_id = %s",
                    (ctx.guild.id, member.id)
                )
        await ctx.approve(f"Cleared all warnings for **{member}**")

    @commands.command(name="delwarn", aliases=["removewarn", "deletewarn"])
    @commands.has_permissions(moderate_members=True)
    async def delwarn(self, ctx, warn_id: int):
        """Delete a specific warning by ID"""
        async with self.bot.db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT * FROM warnings WHERE id = %s AND guild_id = %s",
                    (warn_id, ctx.guild.id)
                )
                if not await cur.fetchone():
                    return await ctx.deny(f"Warning **#{warn_id}** not found.")
                await cur.execute("DELETE FROM warnings WHERE id = %s", (warn_id,))
        await ctx.approve(f"Deleted warning **#{warn_id}**")

    @commands.command(name="massban")
    @commands.has_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    async def massban(self, ctx, *, user_ids: str):
        """Ban multiple users by ID"""
        ids = re.findall(r'\d+', user_ids)
        if not ids:
            return await ctx.deny("Please provide valid user IDs.")
        
        banned = 0
        failed = 0
        for user_id in ids:
            try:
                await ctx.guild.ban(discord.Object(id=int(user_id)), reason=f"Massban by {ctx.author}")
                banned += 1
            except:
                failed += 1
        
        await ctx.approve(f"Banned **{banned}** users, **{failed}** failed")

    @commands.command(name="masskick")
    @commands.has_permissions(kick_members=True)
    @commands.bot_has_permissions(kick_members=True)
    async def masskick(self, ctx, *, members: str):
        """Kick multiple members"""
        kicked = 0
        failed = 0
        for mention in ctx.message.mentions:
            try:
                if mention.top_role < ctx.guild.me.top_role and mention.top_role < ctx.author.top_role:
                    await mention.kick(reason=f"Masskick by {ctx.author}")
                    kicked += 1
                else:
                    failed += 1
            except:
                failed += 1
        
        await ctx.approve(f"Kicked **{kicked}** members, **{failed}** failed")

    @commands.command(name="strip", aliases=["removeroles"])
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def strip(self, ctx, member: discord.Member):
        """Remove all roles from a member"""
        if member.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
            return await ctx.deny("You can't strip roles from someone with a higher or equal role.")
        if member.top_role >= ctx.guild.me.top_role:
            return await ctx.deny("I can't strip roles from someone with a higher or equal role than me.")
        
        roles_to_remove = [r for r in member.roles if r != ctx.guild.default_role and r < ctx.guild.me.top_role]
        if not roles_to_remove:
            return await ctx.deny(f"**{member}** has no removable roles.")
        
        await member.remove_roles(*roles_to_remove, reason=f"Stripped by {ctx.author}")
        await ctx.approve(f"Removed **{len(roles_to_remove)}** roles from **{member}**")

    @commands.command(name="jail")
    @commands.has_permissions(moderate_members=True)
    @commands.bot_has_permissions(manage_roles=True, manage_channels=True)
    async def jail(self, ctx, member: discord.Member, *, reason: str = "No reason provided"):
        """Jail a member - removes all roles and restricts to jail channel"""
        if member.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
            return await ctx.deny("You can't jail someone with a higher or equal role.")
        if member.top_role >= ctx.guild.me.top_role:
            return await ctx.deny("I can't jail someone with a higher or equal role than me.")

        # Get or create jail role
        jail_role = discord.utils.get(ctx.guild.roles, name="Jailed")
        if not jail_role:
            jail_role = await ctx.guild.create_role(name="Jailed", reason="Jail system setup")
            for channel in ctx.guild.channels:
                await channel.set_permissions(jail_role, view_channel=False, send_messages=False)

        # Store member's roles
        async with self.bot.db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("""
                    CREATE TABLE IF NOT EXISTS jailed_users (
                        guild_id BIGINT,
                        user_id BIGINT,
                        roles TEXT,
                        PRIMARY KEY (guild_id, user_id)
                    )
                """)
                role_ids = ",".join([str(r.id) for r in member.roles if r != ctx.guild.default_role])
                await cur.execute(
                    "INSERT INTO jailed_users (guild_id, user_id, roles) VALUES (%s, %s, %s) ON DUPLICATE KEY UPDATE roles = %s",
                    (ctx.guild.id, member.id, role_ids, role_ids)
                )

        # Remove roles and add jail role
        roles_to_remove = [r for r in member.roles if r != ctx.guild.default_role and r < ctx.guild.me.top_role]
        await member.remove_roles(*roles_to_remove, reason=f"Jailed by {ctx.author}")
        await member.add_roles(jail_role, reason=f"Jailed by {ctx.author}")
        await ctx.approve(f"Jailed **{member}** for **{reason}**")

    @commands.command(name="unjail")
    @commands.has_permissions(moderate_members=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def unjail(self, ctx, member: discord.Member):
        """Unjail a member - restores their roles"""
        jail_role = discord.utils.get(ctx.guild.roles, name="Jailed")
        if not jail_role or jail_role not in member.roles:
            return await ctx.deny(f"**{member}** is not jailed.")

        async with self.bot.db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT roles FROM jailed_users WHERE guild_id = %s AND user_id = %s",
                    (ctx.guild.id, member.id)
                )
                result = await cur.fetchone()
                if result and result[0]:
                    role_ids = [int(r) for r in result[0].split(",") if r]
                    roles = [ctx.guild.get_role(r) for r in role_ids if ctx.guild.get_role(r)]
                    await member.add_roles(*roles, reason=f"Unjailed by {ctx.author}")
                await cur.execute(
                    "DELETE FROM jailed_users WHERE guild_id = %s AND user_id = %s",
                    (ctx.guild.id, member.id)
                )

        await member.remove_roles(jail_role, reason=f"Unjailed by {ctx.author}")
        await ctx.approve(f"Unjailed **{member}**")

    @commands.command(name="hide")
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def hide(self, ctx, channel: discord.TextChannel = None):
        """Hide a channel from everyone"""
        channel = channel or ctx.channel
        await channel.set_permissions(ctx.guild.default_role, view_channel=False)
        await ctx.approve(f"Hidden {channel.mention}")

    @commands.command(name="unhide", aliases=["show"])
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def unhide(self, ctx, channel: discord.TextChannel = None):
        """Unhide a channel"""
        channel = channel or ctx.channel
        await channel.set_permissions(ctx.guild.default_role, view_channel=None)
        await ctx.approve(f"Unhidden {channel.mention}")


class NukeConfirmView(discord.ui.View):
    def __init__(self, author: discord.Member, channel: discord.TextChannel):
        super().__init__(timeout=30)
        self.author = author
        self.channel = channel
        self.message = None
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user != self.author:
            await interaction.response.send_message("This is not your confirmation.", ephemeral=True)
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
    
    @discord.ui.button(label="Approve", style=discord.ButtonStyle.green)
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        
        # Clone the channel
        new_channel = await self.channel.clone(reason=f"Channel nuked by {self.author}")
        await new_channel.move(after=self.channel)
        await self.channel.delete(reason=f"Channel nuked by {self.author}")
        
        await new_channel.send("first")
        self.stop()
    
    @discord.ui.button(label="Deny", style=discord.ButtonStyle.red)
    async def deny(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.message.delete()
        self.stop()


async def setup(bot):
    await bot.add_cog(Moderation(bot))
