import discord
from discord.ext import commands
from src.config import Config
import time
from typing import Optional
import re
import aiohttp
from io import BytesIO
from PIL import Image
from collections import Counter
import platform
import os
import psutil
import random
import json
from discord.ui import Button, View
from src.tools.paginator import PaginatorView
from datetime import datetime
from discord import Member

try:
    import pytz
except ImportError:
    pytz = None

TIMEZONE_FILE = "src/timezones.json"


def load_timezones():
    if not os.path.exists(TIMEZONE_FILE):
        return {}
    with open(TIMEZONE_FILE, "r") as f:
        return json.load(f)


def save_timezones(data):
    os.makedirs(os.path.dirname(TIMEZONE_FILE), exist_ok=True)
    with open(TIMEZONE_FILE, "w") as f:
        json.dump(data, f, indent=4)


def get_user_timezone(user_id):
    data = load_timezones()
    return data.get(str(user_id))


def set_user_timezone(user_id, tz):
    data = load_timezones()
    data[str(user_id)] = tz
    save_timezones(data)


class Utility(commands.Cog):
    """Useful utility commands"""
    def __init__(self, bot):
        self.bot = bot
        self.snipe_cache = {}  # Format: {channel_id: [(message, deleted_at), ...]}
        self.afk = {}  # {guild_id: {user_id: (reason, since_timestamp)}}
        bot.loop.create_task(self._setup_afk_table())

    async def _setup_afk_table(self):
        await self.bot.wait_until_ready()
        if not getattr(self.bot, 'db_pool', None):
            return

        async with self.bot.db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("""
                    CREATE TABLE IF NOT EXISTS afk_status (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        guild_id BIGINT NOT NULL,
                        user_id BIGINT NOT NULL,
                        reason TEXT,
                        since TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE KEY unique_afk (guild_id, user_id)
                    )
                """)

                # load existing AFK rows into memory
                await cur.execute("SELECT guild_id, user_id, reason, UNIX_TIMESTAMP(since) FROM afk_status")
                rows = await cur.fetchall()
                for gid, uid, reason, since_ts in rows:
                    gid = int(gid)
                    uid = int(uid)
                    if gid not in self.afk:
                        self.afk[gid] = {}
                    self.afk[gid][uid] = (reason or "", int(since_ts) if since_ts else int(datetime.utcnow().timestamp()))

    async def _set_afk_db(self, guild_id: int, user_id: int, reason: str):
        if not getattr(self.bot, 'db_pool', None):
            return
        async with self.bot.db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    INSERT INTO afk_status (guild_id, user_id, reason)
                    VALUES (%s, %s, %s)
                    ON DUPLICATE KEY UPDATE reason = VALUES(reason), since = CURRENT_TIMESTAMP
                    """,
                    (guild_id, user_id, reason)
                )

    async def _remove_afk_db(self, guild_id: int, user_id: int):
        if not getattr(self.bot, 'db_pool', None):
            return
        async with self.bot.db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "DELETE FROM afk_status WHERE guild_id = %s AND user_id = %s",
                    (guild_id, user_id)
                )


    @commands.Cog.listener()
    async def on_message_delete(self, message):
        """Track deleted messages for snipe command"""
        if message.author.bot:
            return
        
        # Store message with deletion timestamp
        if message.channel.id not in self.snipe_cache:
            self.snipe_cache[message.channel.id] = []
        
        # Keep only last 10 messages per channel
        if len(self.snipe_cache[message.channel.id]) >= 10:
            self.snipe_cache[message.channel.id].pop(0)
        
        self.snipe_cache[message.channel.id].append((message, discord.utils.utcnow()))

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Clear AFK when a user speaks and notify about mentioned AFK users."""
        if message.author.bot or not message.guild:
            return
        
        # Ignore if this is a command invocation (don't remove AFK when setting it)
        ctx = await self.bot.get_context(message)
        if ctx.valid and ctx.command:
            return

        gid = message.guild.id
        # If the author was AFK, remove status and send embed
        if gid in self.afk and message.author.id in self.afk[gid]:
            try:
                reason, since_ts = self.afk[gid].get(message.author.id, ("", int(datetime.utcnow().timestamp())))
                # remove from cache then DB
                try:
                    del self.afk[gid][message.author.id]
                except KeyError:
                    pass
                await self._remove_afk_db(gid, message.author.id)

                since_field = f"<t:{since_ts}:R>" if since_ts else "Unknown"
                embed = discord.Embed(
                    title="Welcome back!",
                    description=f"{message.author.mention} I removed your AFK status.",
                    color=Config.COLORS.SUCCESS
                )
                embed.add_field(name="Reason", value=reason or "No reason provided", inline=False)
                embed.add_field(name="AFK Since", value=since_field, inline=True)

                try:
                    await message.channel.send(embed=embed)
                except Exception:
                    pass
            except Exception:
                pass

        # Notify if any mentioned users are AFK (send a single embed summarizing)
        mentioned_afk = []
        for m in message.mentions:
            if gid in self.afk and m.id in self.afk[gid]:
                reason, since_ts = self.afk[gid][m.id]
                time_str = f"<t:{since_ts}:R>" if since_ts else "Unknown"
                mentioned_afk.append((m, reason or "No reason provided", time_str))

        if mentioned_afk:
            desc_lines = []
            for m, reason, since in mentioned_afk:
                desc_lines.append(f"**{m.display_name}** ({m.mention}) — {reason} — {since}")

            embed = discord.Embed(
                title="AFK Notice",
                description="\n".join(desc_lines),
                color=Config.COLORS.DEFAULT
            )
            try:
                await message.channel.send(embed=embed)
            except Exception:
                pass
                
    @commands.command(name="ping")
    async def ping(self, ctx):
        """Check the bot's latency"""
        # Get websocket latency
        ws_latency = round(self.bot.latency * 1000)
        
        # Create initial embed
        embed = discord.Embed(
            description=f"-# > Ping `{ws_latency}ms`",
            color=Config.COLORS.DEFAULT
        )
        
        # Send message and measure response time
        start = time.perf_counter()
        message = await ctx.send(embed=embed)
        end = time.perf_counter()
        
        # Calculate API latency
        api_latency = round((end - start) * 1000)
        
        # Update embed with API latency
        embed.description = f"-# > Ping `{ws_latency}ms` (edit: `{api_latency}ms`)"
        await message.edit(embed=embed)

    @commands.command(aliases=["sp"], name="spotify", help="send what you or another person is listening to on Spotify", usage="member")
    async def spotify(self, ctx, user: discord.Member = None):
        try:
            if user == None:
                user = ctx.author
                pass
            if user.activities:
                for activity in user.activities:
                    if str(activity).lower() == "spotify":
                        embed = discord.Embed(color=Config.COLORS.DEFAULT)
                        embed.add_field(
                            name="**Song**", value=f"**[{activity.title}](https://open.spotify.com/track/{activity.track_id})**", inline=True)
                        embed.add_field(
                            name="**Artist**", value=f"**[{activity.artist}](https://open.spotify.com/track/{activity.track_id})**", inline=True)
                        embed.set_thumbnail(url=activity.album_cover_url)
                        embed.set_author(
                            name=user.name, icon_url=user.display_avatar.url)
                        embed.set_footer(
                            text=f"Album: {activity.album}", icon_url=activity.album_cover_url)
                        button1 = discord.ui.Button(emoji="<:spotify:1452790687958433925>", label="Listen on Spotify", style=discord.ButtonStyle.url, url=f"https://open.spotify.com/track/{activity.track_id}")
                        view = discord.ui.View()
                        view.add_item(button1)
                        await ctx.reply(embed=embed, view=view, mention_author=False)
                        return
            embed = discord.Embed(
                description=f"{ctx.message.author.mention}: **{user}** is not listening to Spotify", colour=0x313338)
            await ctx.reply(embed=embed, mention_author=False)
            return
        except Exception as e:
            print(e)

    @commands.command(help="shows the number of invites an user has", usage="<user>")
    async def invites(self, ctx: commands.Context, *, member: Member=None):
      if member is None: 
        member = ctx.author 
      invites = await ctx.guild.invites()
      await ctx.neutral(f"{member} has **{sum(invite.uses for invite in invites if invite.inviter.id == member.id)}** invites")
    
    @commands.command(name="invite")
    async def invite(self, ctx):
        """Get the bot's invite link"""
        invite_url = discord.utils.oauth_url(
            self.bot.user.id,
            permissions=discord.Permissions(administrator=True)
        )

        embed = discord.Embed(
            title="",
            description="Click the button below to add me to your server!",
            color=Config.COLORS.DEFAULT
        )

        view = discord.ui.View()
        view.add_item(discord.ui.Button(
            label="Invite",
            url=invite_url,
            style=discord.ButtonStyle.link
        ))
        
        await ctx.send(embed=embed, view=view)

    @commands.command(name="donate")
    async def donate(self, ctx):
        """Donate to keep the slit bot online"""
        embed = discord.Embed(title="slit donate", description=" -# soon we will have the payments, keep an eye on us", color=Config.COLORS.DEFAULT)
        await ctx.send(embed=embed)

    @commands.command(name='avatar', aliases=['av', 'pfp'], extras={'example': 'avatar @user'})
    async def avatar(self, ctx, user: Optional[discord.User] = None):
        """Get a user's avatar"""
        user = user or ctx.author
        
        embed = discord.Embed(
            title=f"{user.name}'s avatar",
            color=Config.COLORS.DEFAULT
        )
        embed.set_image(url=user.display_avatar.url)
        
        await ctx.send(embed=embed)
    
    @commands.command(name='banner', extras={'example': 'banner @user'})
    async def banner(self, ctx, user: Optional[discord.User] = None):
        """Get a user's banner"""
        user = user or ctx.author
        user = await self.bot.fetch_user(user.id)
        
        if not user.banner:
            embed = discord.Embed(
                description=f"{Config.EMOJIS.ERROR} **{user.name}** doesn't have a banner",
                color=Config.COLORS.ERROR
            )
            return await ctx.send(embed=embed)
        
        embed = discord.Embed(
            title=f"{user.name}'s banner",
            color=Config.COLORS.DEFAULT
        )
        embed.set_image(url=user.banner.url)
        
        await ctx.send(embed=embed)

    @commands.command(name='firstmessage', aliases=['firstmsg'], extras={'example': 'firstmessage #general'})
    async def firstmessage(self, ctx, channel: Optional[discord.TextChannel] = None):
        """Get the first message in a channel"""
        channel = channel or ctx.channel
        
        try:
            # Get the first message in the channel
            first_message = None
            async for message in channel.history(limit=1, oldest_first=True):
                first_message = message
                break
            
            if not first_message:
                embed = discord.Embed(
                    description=f"{Config.EMOJIS.ERROR} Could not find any messages in {channel.mention}",
                    color=Config.COLORS.ERROR
                )
                return await ctx.send(embed=embed)
            
            # Create embed
            embed = discord.Embed(
                title=f"First Message in: #{channel.name}",
                description=f"**[Message Link]({first_message.jump_url})** by: {first_message.author.mention}",
                color=Config.COLORS.DEFAULT
            )
            
            # Add image if the message has attachments
            if first_message.attachments:
                embed.set_image(url=first_message.attachments[0].url)
            
            # Create button view
            view = discord.ui.View()
            button = discord.ui.Button(
                label="Jump to Message",
                style=discord.ButtonStyle.link,
                url=first_message.jump_url
            )
            view.add_item(button)
            
            await ctx.send(embed=embed, view=view)
            
        except discord.Forbidden:
            embed = discord.Embed(
                description=f"{Config.EMOJIS.ERROR} I don't have permission to read message history in {channel.mention}",
                color=Config.COLORS.ERROR
            )
            await ctx.send(embed=embed)
        except Exception as e:
            embed = discord.Embed(
                description=f"{Config.EMOJIS.ERROR} An error occurred: {str(e)}",
                color=Config.COLORS.ERROR
            )
            await ctx.send(embed=embed)
    
    @commands.command(name='calculate', aliases=['calc', 'math'], extras={'example': 'calc 2 + 2'})
    async def calculate(self, ctx, *, expression: str = None):
        """Calculate a math expression"""
        if not expression:
            return await ctx.send_help(ctx.command)
        
        # Clean the expression
        expression = expression.replace('x', '*').replace('×', '*').replace('÷', '/')
        
        # Security check - only allow safe characters
        if not re.match(r'^[0-9+\-*/().\s%**]+$', expression):
            embed = discord.Embed(
                description=f"{Config.EMOJIS.ERROR} Invalid expression. Only numbers and basic operators (+, -, *, /, %, **, parentheses) are allowed",
                color=Config.COLORS.ERROR
            )
            return await ctx.send(embed=embed)
        
        try:
            # Evaluate the expression
            result = eval(expression, {"__builtins__": {}}, {})
            
            embed = discord.Embed(
                title="Calculator",
                color=Config.COLORS.DEFAULT
            )
            embed.add_field(name="Expression", value=f"```{expression}```", inline=False)
            embed.add_field(name="Result", value=f"```{result}```", inline=False)
            
            await ctx.send(embed=embed)
            
        except ZeroDivisionError:
            embed = discord.Embed(
                description=f"{Config.EMOJIS.ERROR} Cannot divide by zero",
                color=Config.COLORS.ERROR
            )
            await ctx.send(embed=embed)
        except Exception as e:
            embed = discord.Embed(
                description=f"{Config.EMOJIS.ERROR} Invalid expression or calculation error",
                color=Config.COLORS.ERROR
            )
            await ctx.send(embed=embed)

    @commands.command(name='inviteinfo', aliases=['ii', 'invite-info'], extras={'example': 'inviteinfo discord.gg/flare'})
    async def inviteinfo(self, ctx, invite_code: str = None):
        """Get information about a Discord invite"""
        if not invite_code:
            return await ctx.send_help(ctx.command)
        
        # Clean the invite code
        invite_code = invite_code.replace('discord.gg/', '').replace('https://', '').replace('http://', '')
        
        try:
            # Fetch the invite
            invite = await self.bot.fetch_invite(invite_code, with_counts=True)
            
            # Create embed
            embed = discord.Embed(
                title=f"Invite Info: {invite_code}",
                color=Config.COLORS.DEFAULT
            )
            
            # Set server icon as thumbnail
            if invite.guild and invite.guild.icon:
                embed.set_thumbnail(url=invite.guild.icon.url)
            
            # Set server banner as image
            if invite.guild and invite.guild.banner:
                embed.set_image(url=invite.guild.banner.url)
            
            # Server info field
            channel_name = invite.channel.name if invite.channel else "Unknown"
            member_count = f"{invite.approximate_member_count:,}" if invite.approximate_member_count else "Unknown"
            
            server_info = f"Channel: {channel_name}\nMembers: {member_count}"
            embed.add_field(name="Server:", value=server_info, inline=True)
            
            # Inviter info field
            if invite.inviter:
                inviter_info = f"Inviter: {invite.inviter.mention} ({invite.inviter.id})"
            else:
                inviter_info = "Inviter: N/A"
            
            # Check if it's a vanity invite
            if invite.guild:
                try:
                    vanity = await invite.guild.vanity_invite()
                    if vanity and vanity.code == invite_code:
                        inviter_info += f"\nServer Vanity: {invite_code}"
                except:
                    pass
            
            embed.add_field(name="Inviter:", value=inviter_info, inline=True)
            
            # Create button view
            view = discord.ui.View()
            button = discord.ui.Button(
                label="Join Server",
                style=discord.ButtonStyle.link,
                url=f"https://discord.gg/{invite_code}"
            )
            view.add_item(button)
            
            await ctx.send(embed=embed, view=view)
            
        except discord.NotFound:
            embed = discord.Embed(
                description=f"{Config.EMOJIS.ERROR} Invalid or expired invite code",
                color=Config.COLORS.ERROR
            )
            await ctx.send(embed=embed)
        except discord.Forbidden:
            embed = discord.Embed(
                description=f"{Config.EMOJIS.ERROR} I don't have permission to fetch this invite",
                color=Config.COLORS.ERROR
            )
            await ctx.send(embed=embed)
        except Exception as e:
            embed = discord.Embed(
                description=f"{Config.EMOJIS.ERROR} An error occurred: {str(e)}",
                color=Config.COLORS.ERROR
            )
            await ctx.send(embed=embed)

    @commands.command(name='say', extras={'example': 'say Hello everyone!'})
    @commands.has_permissions(administrator=True)
    async def say(self, ctx, *, message: str):
        """Send a message as the bot"""
        await ctx.message.delete()
        await ctx.send(message)

    @commands.command(name='serverinfo', aliases=['si', 'server'], extras={'example': 'serverinfo'})
    async def serverinfo(self, ctx):
        """Get information about the server"""
        guild = ctx.guild
        
        # Count channel types
        text_channels = len(guild.text_channels)
        voice_channels = len(guild.voice_channels)
        total_channels = text_channels + voice_channels
        
        # Get creation timestamp
        created_timestamp = int(guild.created_at.timestamp())
        
        # Create embed
        embed = discord.Embed(
            description=f">>> -# Owner: {guild.owner.mention} ({guild.owner.id})\n-# Created: <t:{created_timestamp}:D>",
            color=Config.COLORS.DEFAULT
        )
        
        # Set author with server name and icon
        embed.set_author(
            name=guild.name,
            icon_url=guild.icon.url if guild.icon else None
        )
        
        # Set image to server banner
        if guild.banner:
            embed.set_image(url=guild.banner.url)
        
        # Server field
        server_info = f">>> -# Members: **{guild.member_count:,}**\n-# Channels: **{total_channels}**\n-# Boosts: **{guild.premium_subscription_count}**"
        embed.add_field(name="Server:", value=server_info, inline=True)
        
        # Stats field
        emoji_limit = guild.emoji_limit
        role_limit = 250
        stats_info = f">>> -# Emojis: **{len(guild.emojis)}/{emoji_limit}**\n-# Roles: **{len(guild.roles)}/{role_limit}**"
        embed.add_field(name="Stats:", value=stats_info, inline=True)
        
        await ctx.send(embed=embed)

    @commands.command(name='dominantcolor', aliases=['dc', 'domcolor'], extras={'example': 'dominantcolor [attach image]'})
    async def dominantcolor(self, ctx, url: Optional[str] = None):
        """Get the dominant color of an image"""
        image_url = None
        
        # Check for attachments first
        if ctx.message.attachments:
            image_url = ctx.message.attachments[0].url
        elif url:
            image_url = url
        else:
            embed = discord.Embed(
                description=f"{Config.EMOJIS.ERROR} Please provide an image URL or attach an image",
                color=Config.COLORS.ERROR
            )
            return await ctx.send(embed=embed)
        
        try:
            # Download the image
            async with aiohttp.ClientSession() as session:
                async with session.get(image_url) as resp:
                    if resp.status != 200:
                        embed = discord.Embed(
                            description=f"{Config.EMOJIS.ERROR} Could not download the image",
                            color=Config.COLORS.ERROR
                        )
                        return await ctx.send(embed=embed)
                    
                    image_data = await resp.read()
            
            # Open image with PIL
            image = Image.open(BytesIO(image_data))
            
            # Convert to RGB if necessary
            if image.mode != 'RGB':
                image = image.convert('RGB')
            
            # Resize for faster processing
            image = image.resize((150, 150))
            
            # Get all pixels
            pixels = list(image.getdata())
            
            # Count color occurrences
            color_counter = Counter(pixels)
            
            # Get the most common color
            dominant_color = color_counter.most_common(1)[0][0]
            
            # Convert to hex
            hex_color = '#{:02x}{:02x}{:02x}'.format(dominant_color[0], dominant_color[1], dominant_color[2])
            
            # Convert hex to int for Discord color
            color_int = int(hex_color[1:], 16)
            
            # Create embed
            embed = discord.Embed(
                title="Dominant Color",
                color=color_int
            )
            
            embed.add_field(
                name="Color Info",
                value=f"**Hex:** `{hex_color.upper()}`\n**RGB:** `{dominant_color[0]}, {dominant_color[1]}, {dominant_color[2]}`",
                inline=False
            )
            
            embed.set_thumbnail(url=image_url)
            
            await ctx.send(embed=embed)
            
        except Exception as e:
            embed = discord.Embed(
                description=f"{Config.EMOJIS.ERROR} An error occurred while processing the image: {str(e)}",
                color=Config.COLORS.ERROR
            )
            await ctx.send(embed=embed)

    @commands.command(name='botinfo', aliases=['bi', 'about'], extras={'example': 'botinfo'})
    async def botinfo(self, ctx):
        """Get information about the bot"""
        bot = self.bot
        
        # Get system info
        os_name = platform.system()
        ram_gb = round(psutil.virtual_memory().total / (1024 ** 3))
        
        # Count bot stats
        total_lines = 0
        total_files = 0
        total_imports = 0
        
        # Walk through both src and cogs directories
        directories_to_scan = ['src', 'cogs']
        
        for directory in directories_to_scan:
            # Check if directory exists before scanning
            if not os.path.exists(directory):
                continue
                
            for root, dirs, files in os.walk(directory):
                for file in files:
                    if file.endswith('.py'):
                        total_files += 1
                        file_path = os.path.join(root, file)
                        try:
                            with open(file_path, 'r', encoding='utf-8') as f:
                                lines = f.readlines()
                                total_lines += len(lines)
                                # Count imports
                                for line in lines:
                                    if line.strip().startswith(('import ', 'from ')):
                                        total_imports += 1
                        except Exception:
                            pass
        
        # Get bot stats
        total_users = sum(g.member_count for g in bot.guilds)
        total_servers = len(bot.guilds)
        total_channels = sum(len(g.channels) for g in bot.guilds)
        
        # Count commands and cogs
        total_commands = len([cmd for cmd in bot.walk_commands()])
        total_cogs = len(bot.cogs)
        
        # Get bot start time (uptime)
        if hasattr(bot, 'uptime'):
            start_timestamp = int(bot.uptime.timestamp())
        else:
            start_timestamp = int(datetime.utcnow().timestamp())
        
        # Page 1 Embed
        embed1 = discord.Embed(
                description=f"-# **{bot.user.name}** is maintained and developed by **[the slit team](https://discord.gg/9H6NqBszzR)**",
            color=Config.COLORS.DEFAULT
        )
        embed1.set_thumbnail(url=bot.user.display_avatar.url)
        
        # System field
        system_info = f"-# OS: **{os_name}**\n-# RAM: **{ram_gb}GB**\n-# Library: **Python**"
        embed1.add_field(name="System:", value=system_info, inline=True)
        
        # Bot field (Page 1)
        bot_info_p1 = f"-# Lines: **{total_lines:,}**\n-# Files: **{total_files}**\n-# Imports: **{total_imports}**"
        embed1.add_field(name="Bot:", value=bot_info_p1, inline=True)
        
        embed1.set_footer(text="Page: 1/2")
        
        # Page 2 Embed
        embed2 = discord.Embed(
            description=f"-# **{bot.user.name}** is maintained and developed by **[the slit team](https://discord.gg/9H6NqBszzR)**",
            color=Config.COLORS.DEFAULT
        )
        embed2.set_thumbnail(url=bot.user.display_avatar.url)
        
        # Servers field
        servers_info = f"-# Users: **{total_users:,}**\n-# Servers: **{total_servers}**\n-# Channels: **{total_channels}**"
        embed2.add_field(name="Servers:", value=servers_info, inline=True)
        
        # Bot field (Page 2)
        bot_info_p2 = f"-# Started: <t:{start_timestamp}:R>\n-# Commands: **{total_commands}**\n-# Cogs: **{total_cogs}**"
        embed2.add_field(name="Bot:", value=bot_info_p2, inline=True)
        
        embed2.set_footer(text="Page: 2/2")
        
        # Create paginator view with both embeds
        embeds = [embed1, embed2]
        view = PaginatorView(embeds=embeds)
        
        await ctx.send(embed=embeds[0], view=view)
    @commands.command(name='snipe', aliases=['s'], extras={'example': 'snipe'})
    async def snipe(self, ctx):
        """View recently deleted messages in this channel"""
        if ctx.channel.id not in self.snipe_cache or not self.snipe_cache[ctx.channel.id]:
            embed = discord.Embed(
                description=f"{Config.EMOJIS.ERROR} No deleted messages found in this channel",
                color=Config.COLORS.ERROR
            )
            return await ctx.send(embed=embed)
        
        # Get all sniped messages for this channel
        sniped_messages = self.snipe_cache[ctx.channel.id]
        
        # Create embeds for each sniped message
        embeds = []
        for idx, (message, deleted_at) in enumerate(reversed(sniped_messages), 1):
            # Calculate time ago
            time_diff = discord.utils.utcnow() - deleted_at
            
            # Format time ago
            if time_diff.total_seconds() < 60:
                time_ago = f"{int(time_diff.total_seconds())} seconds ago"
            elif time_diff.total_seconds() < 3600:
                time_ago = f"{int(time_diff.total_seconds() / 60)} minutes ago"
            elif time_diff.total_seconds() < 86400:
                time_ago = f"{int(time_diff.total_seconds() / 3600)} hours ago"
            else:
                time_ago = f"{int(time_diff.total_seconds() / 86400)} days ago"
            
            # Create embed
            embed = discord.Embed(
                description=message.content if message.content else "*No content*",
                color=Config.COLORS.DEFAULT
            )
            
            # Set author
            embed.set_author(
                name=message.author.name,
                icon_url=message.author.display_avatar.url
            )
            
            # Add image if message had attachments
            if message.attachments:
                embed.set_image(url=message.attachments[0].url)
            
            # Set footer
            embed.set_footer(text=f"Snipe {idx}/{len(sniped_messages)} • Deleted: {time_ago}")
            
            embeds.append(embed)
        
        # If only one message, send without paginator
        if len(embeds) == 1:
            await ctx.send(embed=embeds[0])
        else:
            # Import paginator
            from src.tools.paginator import PaginatorView
            
            # Send with paginator
            view = PaginatorView(embeds)
            await ctx.send(embed=embeds[0], view=view)
    
    @commands.command(name='clearsnipe', aliases=['cs'], extras={'example': 'clearsnipe'})
    @commands.has_permissions(manage_messages=True)
    async def clearsnipe(self, ctx):
        """Clear all sniped messages in this channel"""
        if ctx.channel.id not in self.snipe_cache or not self.snipe_cache[ctx.channel.id]:
            embed = discord.Embed(
                description=f"{Config.EMOJIS.ERROR} No sniped messages to clear in this channel",
                color=Config.COLORS.ERROR
            )
            return await ctx.send(embed=embed)
        
        # Get count before clearing
        count = len(self.snipe_cache[ctx.channel.id])
        
        # Clear the snipe cache for this channel
        self.snipe_cache[ctx.channel.id] = []
        
        embed = discord.Embed(
            description=f"{Config.EMOJIS.SUCCESS} Cleared **{count}** sniped message{'s' if count != 1 else ''} from this channel",
            color=Config.COLORS.SUCCESS
        )
        await ctx.send(embed=embed)

    @commands.command(name='afk')
    async def afk(self, ctx, *, reason: str = None):
        """Set your AFK status. Use `afk off` to remove."""
        if not ctx.guild:
            return await ctx.deny("AFK can only be set in a server")

        gid = ctx.guild.id
        uid = ctx.author.id

        # Remove AFK if user passed off/clear/remove
        if reason and reason.lower() in ("off", "remove", "clear"):
            if gid in self.afk and uid in self.afk[gid]:
                try:
                    del self.afk[gid][uid]
                except KeyError:
                    pass
                await self._remove_afk_db(gid, uid)
                return await ctx.approve("AFK removed")
            return await ctx.warn("You are not AFK")

        # Set AFK
        reason_text = reason or "AFK"
        ts = int(datetime.utcnow().timestamp())
        if gid not in self.afk:
            self.afk[gid] = {}
        self.afk[gid][uid] = (reason_text, ts)
        await self._set_afk_db(gid, uid, reason_text)
        await ctx.approve(f"I set you AFK with the message **{reason_text}**")

    @commands.command(name='poll', extras={'example': 'poll "Do you like pizza?" "Yes" "No" "Maybe"'})
    async def poll(self, ctx, question: str, *options: str):
        """Create a poll with up to 10 options"""
        if len(options) < 2:
            embed = discord.Embed(
                description=f"{Config.EMOJIS.ERROR} You need at least 2 options for a poll",
                color=Config.COLORS.ERROR
            )
            return await ctx.send(embed=embed)
        
        if len(options) > 10:
            embed = discord.Embed(
                description=f"{Config.EMOJIS.ERROR} You can only have up to 10 options in a poll",
                color=Config.COLORS.ERROR
            )
            return await ctx.send(embed=embed)
        
        # Number emojis for reactions
        number_emojis = ['1️⃣', '2️⃣', '3️⃣', '4️⃣', '5️⃣', '6️⃣', '7️⃣', '8️⃣', '9️⃣', '🔟']
        
        # Create poll description
        description = []
        for idx, option in enumerate(options):
            description.append(f"{number_emojis[idx]} {option}")
        
        # Create embed
        embed = discord.Embed(
            title=f"📊 {question}",
            description="\n".join(description),
            color=Config.COLORS.DEFAULT
        )
        embed.set_footer(text=f"Poll created by {ctx.author.display_name}")
        
        # Send poll
        poll_message = await ctx.send(embed=embed)
        
        # Add reactions
        for idx in range(len(options)):
            await poll_message.add_reaction(number_emojis[idx])

    @commands.command(name='randomhex', extras={'example': 'randomhex'})
    async def randomhex(self, ctx):
        """Generate a random hex color"""
        # Generate random RGB values
        r = random.randint(0, 255)
        g = random.randint(0, 255)
        b = random.randint(0, 255)
        
        # Convert to hex
        hex_color = '#{:02x}{:02x}{:02x}'.format(r, g, b)
        
        # Convert to Discord color int
        color_int = int(hex_color[1:], 16)
        
        # Create embed
        embed = discord.Embed(
            title="Random Hex Color",
            color=color_int
        )
        
        embed.add_field(
            name="Color Info",
            value=f"**Hex:** `{hex_color.upper()}`\n**RGB:** `{r}, {g}, {b}`",
            inline=False
        )
        
        await ctx.send(embed=embed)

    @commands.command(name='rps', extras={'example': 'rps rock'})
    async def rps(self, ctx, choice: str = None):
        """Play rock paper scissors against the bot"""
        if not choice:
            embed = discord.Embed(
                description=f"{Config.EMOJIS.ERROR} Please choose: `rock`, `paper`, or `scissors`",
                color=Config.COLORS.ERROR
            )
            return await ctx.send(embed=embed)
        
        # Normalize user choice
        choice = choice.lower()
        valid_choices = ['rock', 'paper', 'scissors']
        
        if choice not in valid_choices:
            embed = discord.Embed(
                description=f"{Config.EMOJIS.ERROR} Invalid choice! Choose: `rock`, `paper`, or `scissors`",
                color=Config.COLORS.ERROR
            )
            return await ctx.send(embed=embed)
        
        # Bot makes a choice
        bot_choice = random.choice(valid_choices)
        
        # Determine winner
        if choice == bot_choice:
            result = "It's a tie!"
            result_emoji = "🤝"
        elif (choice == 'rock' and bot_choice == 'scissors') or \
             (choice == 'paper' and bot_choice == 'rock') or \
             (choice == 'scissors' and bot_choice == 'paper'):
            result = "You win!"
            result_emoji = "🎉"
        else:
            result = "You lose!"
            result_emoji = "😢"
        
        # Choice emojis
        choice_emojis = {
            'rock': '🪨',
            'paper': '📄',
            'scissors': '✂️'
        }
        
        # Create embed
        embed = discord.Embed(
            title=f"{result_emoji} {result}",
            color=Config.COLORS.DEFAULT
        )
        
        embed.add_field(
            name="Your Choice",
            value=f"{choice_emojis[choice]} {choice.capitalize()}",
            inline=True
        )
        
        embed.add_field(
            name="Bot's Choice",
            value=f"{choice_emojis[bot_choice]} {bot_choice.capitalize()}",
            inline=True
        )
        
        await ctx.send(embed=embed)

    @commands.command(name='serveravatar', aliases=['sav', 'spfp'], extras={'example': 'serveravatar @user'})
    @commands.guild_only()
    async def serveravatar(self, ctx, member: Optional[discord.Member] = None):
        """Get a user's server-specific avatar"""
        member = member or ctx.author
        
        # Check if member has a server-specific avatar
        if not member.guild_avatar:
            embed = discord.Embed(
                description=f"{Config.EMOJIS.ERROR} **{member.name}** doesn't have a server avatar set",
                color=Config.COLORS.ERROR
            )
            return await ctx.send(embed=embed)
        
        embed = discord.Embed(
            title=f"{member.name}'s server avatar",
            color=Config.COLORS.DEFAULT
        )
        embed.set_image(url=member.guild_avatar.url)
        
        await ctx.send(embed=embed)
    
    @commands.command(name='serverbanner', aliases=['sb'], extras={'example': 'serverbanner @user'})
    @commands.guild_only()
    async def serverbanner(self, ctx, member: Optional[discord.Member] = None):
        """Get a user's server-specific banner"""
        member = member or ctx.author
        
        # Fetch the full member to get banner info
        try:
            member = await ctx.guild.fetch_member(member.id)
        except:
            pass
        
        # Check if member has a server-specific banner
        # Note: Server-specific banners are rare and may not be available in all cases
        if not hasattr(member, 'banner') or not member.banner:
            embed = discord.Embed(
                description=f"{Config.EMOJIS.ERROR} **{member.name}** doesn't have a server banner set",
                color=Config.COLORS.ERROR
            )
            return await ctx.send(embed=embed)
        
        embed = discord.Embed(
            title=f"{member.name}'s server banner",
            color=Config.COLORS.DEFAULT
        )
        embed.set_image(url=member.banner.url)
        
        await ctx.send(embed=embed)

    @commands.command(name='roles', aliases=['serverroles'], extras={'example': 'roles'})
    @commands.guild_only()
    async def roles(self, ctx):
        """View all roles in the server"""
        guild = ctx.guild
        
        # Get all roles except @everyone, sorted by position (highest first)
        roles = sorted([role for role in guild.roles if role.name != "@everyone"], key=lambda r: r.position, reverse=True)
        
        if not roles:
            embed = discord.Embed(
                description=f"{Config.EMOJIS.ERROR} No roles found in this server",
                color=Config.COLORS.ERROR
            )
            return await ctx.send(embed=embed)
        
        # Create embeds with 10 roles per page
        embeds = []
        roles_per_page = 10
        total_pages = (len(roles) + roles_per_page - 1) // roles_per_page
        
        for page in range(total_pages):
            start_idx = page * roles_per_page
            end_idx = min(start_idx + roles_per_page, len(roles))
            page_roles = roles[start_idx:end_idx]
            
            # Build description with role mentions and member counts
            description = ""
            for idx, role in enumerate(page_roles, start=start_idx + 1):
                member_count = len(role.members)
                member_text = "member" if member_count == 1 else "members"
                description += f"`{idx:02d}.` {role.mention} - {member_count} {member_text}\n"
            
            # Create embed
            embed = discord.Embed(
                description=description,
                color=Config.COLORS.DEFAULT
            )
            
            embed.set_author(name=f"Roles in: {guild.name}")
            embed.set_footer(text=f"{len(roles)} roles • page {page + 1}/{total_pages}")
            
            embeds.append(embed)
        
        # Send with paginator if multiple pages
        if len(embeds) == 1:
            await ctx.send(embed=embeds[0])
        else:
            from src.tools.paginator import PaginatorView
            view = PaginatorView(embeds)
            await ctx.send(embed=embeds[0], view=view)

    @commands.command(name='lyrics', aliases=['ly'], extras={'example': 'lyrics spm vs los'})
    async def lyrics(self, ctx, *, query: str = None):
        """Get lyrics for a song"""
        if not query:
            return await ctx.send_help(ctx.command)
        
        try:
            # Fetch lyrics from API
            async with aiohttp.ClientSession() as session:
                async with session.get(f"https://api.rive.wtf/lyrics?title={query}") as resp:
                    if resp.status != 200:
                        embed = discord.Embed(
                            description=f"{Config.EMOJIS.ERROR} Could not fetch lyrics. Please try again later",
                            color=Config.COLORS.ERROR
                        )
                        return await ctx.send(embed=embed)
                    
                    data = await resp.json()
            
            # Check if the API returned success
            if not data.get('success'):
                embed = discord.Embed(
                    description=f"{Config.EMOJIS.ERROR} Could not find lyrics for **{query}**",
                    color=Config.COLORS.ERROR
                )
                return await ctx.send(embed=embed)
            
            lyrics_data = data.get('data', {})
            track_info = lyrics_data.get('track', {})
            lines = lyrics_data.get('lines', [])
            
            # Extract track information
            title = track_info.get('title', 'Unknown')
            author = track_info.get('author', 'Unknown')
            album_art = track_info.get('albumArt')
            
            if not lines:
                embed = discord.Embed(
                    description=f"{Config.EMOJIS.ERROR} No lyrics found for **{query}**",
                    color=Config.COLORS.ERROR
                )
                return await ctx.send(embed=embed)
            
            # Create embeds with 10 lines per page
            embeds = []
            lines_per_page = 10
            total_pages = (len(lines) + lines_per_page - 1) // lines_per_page
            
            for page in range(total_pages):
                start_idx = page * lines_per_page
                end_idx = min(start_idx + lines_per_page, len(lines))
                page_lines = lines[start_idx:end_idx]
                
                # Build description with lyrics
                description = ""
                for line_obj in page_lines:
                    line_text = line_obj.get('line', '').strip()
                    if line_text:
                        description += f"{line_text}\n"
                    else:
                        description += "\n"
                
                # Create embed
                embed = discord.Embed(
                    title=f"{title} - {author}",
                    description=description if description.strip() else "*No lyrics available*",
                    color=Config.COLORS.DEFAULT
                )
                
                # Set album art as thumbnail
                if album_art:
                    embed.set_thumbnail(url=album_art)
                
                embed.set_footer(text=f"Page {page + 1}/{total_pages}")
                
                embeds.append(embed)
            
            # Send with paginator if multiple pages
            if len(embeds) == 1:
                await ctx.send(embed=embeds[0])
            else:
                from src.tools.paginator import PaginatorView
                view = PaginatorView(embeds)
                await ctx.send(embed=embeds[0], view=view)
                
        except aiohttp.ClientError:
            embed = discord.Embed(
                description=f"{Config.EMOJIS.ERROR} Connection error. Please try again later",
                color=Config.COLORS.ERROR
            )
            await ctx.send(embed=embed)
        except Exception as e:
            embed = discord.Embed(
                description=f"{Config.EMOJIS.ERROR} An error occurred: {str(e)}",
                color=Config.COLORS.ERROR
            )
            await ctx.send(embed=embed)

    @commands.command(name='membercount', aliases=['mc', 'members'], extras={'example': 'membercount'})
    @commands.guild_only()
    async def membercount(self, ctx):
        """Get member statistics for the server"""
        guild = ctx.guild
        
        # Count member types
        total_members = guild.member_count
        humans = sum(1 for m in guild.members if not m.bot)
        bots = sum(1 for m in guild.members if m.bot)
        
        # Count online members
        online = sum(1 for m in guild.members if m.status != discord.Status.offline)
        
        # Create embed
        embed = discord.Embed(
            description=f">>> -# Total: **{total_members:,}**\n-# Humans: **{humans:,}**\n-# Bots: **{bots}**",
            color=Config.COLORS.DEFAULT
        )
        
        embed.set_author(
            name=f"{guild.name}'s members",
            icon_url=guild.icon.url if guild.icon else None
        )
        
        # Stats field
        stats_info = f">>> -# Online: **{online:,}**\n-# Offline: **{total_members - online:,}**"
        embed.add_field(name="Status:", value=stats_info, inline=True)
        
        await ctx.send(embed=embed)

    @commands.command(name='userinfo', aliases=['ui', 'whois'], extras={'example': 'userinfo @user'})
    @commands.guild_only()
    async def userinfo(self, ctx, user: Optional[discord.Member] = None):
        """Get information about a user"""
        user = user or ctx.author
        
        # Fetch full user for banner
        try:
            fetched_user = await self.bot.fetch_user(user.id)
        except:
            fetched_user = user
        
        # Get timestamps
        created_timestamp = int(user.created_at.timestamp())
        joined_timestamp = int(user.joined_at.timestamp()) if hasattr(user, 'joined_at') and user.joined_at else None
        
        # Calculate join position
        join_position = None
        if hasattr(user, 'joined_at') and user.joined_at:
            sorted_members = sorted(ctx.guild.members, key=lambda m: m.joined_at or discord.utils.utcnow())
            try:
                join_position = sorted_members.index(user) + 1
            except ValueError:
                join_position = None
        
        # Count mutual servers
        mutual_servers = sum(1 for g in self.bot.guilds if g.get_member(user.id))
        
        # Create embed
        embed = discord.Embed(color=Config.COLORS.DEFAULT)
        
        # Set author with user info and ID
        embed.set_author(
            name=f"{user.name} ({user.id})",
            icon_url=user.display_avatar.url
        )
        
        # Set thumbnail to avatar
        embed.set_thumbnail(url=user.display_avatar.url)
        
        # Roles section
        if hasattr(user, 'roles') and len(user.roles) > 1:
            roles = [role.mention for role in reversed(user.roles) if role.name != "@everyone"]
            role_count = len(roles)
            roles_display = " ".join(roles[:8])
            if role_count > 8:
                roles_display += f" +{role_count - 8} more"
            
            embed.add_field(
                name=f"Roles ({role_count})",
                value=roles_display,
                inline=False
            )
        
        # Dates section
        dates_text = f"**Created:** <t:{created_timestamp}:F> (<t:{created_timestamp}:R>)"
        if joined_timestamp:
            dates_text += f"\n**Joined:** <t:{joined_timestamp}:F> (<t:{joined_timestamp}:R>)"
        
        embed.add_field(
            name="Dates",
            value=dates_text,
            inline=False
        )
        
        # Footer with join position, mutual servers, and current time
        footer_parts = []
        if join_position:
            footer_parts.append(f"Join position: {join_position}")
        footer_parts.append(f"{mutual_servers} mutual server{'s' if mutual_servers != 1 else ''}")
        footer_parts.append(f"Today at {discord.utils.utcnow().strftime('%H:%M')}")
        
        embed.set_footer(text=" • ".join(footer_parts))
        
        await ctx.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())

    @commands.command(name='roleinfo', aliases=['ri', 'rinfo'], extras={'example': 'roleinfo @Moderator'})
    @commands.guild_only()
    async def roleinfo(self, ctx, *, role: discord.Role = None):
        """Get information about a role"""
        if not role:
            return await ctx.send_help(ctx.command)
        
        # Get timestamps
        created_timestamp = int(role.created_at.timestamp())
        
        # Count members with this role
        member_count = len(role.members)
        
        # Get permissions
        perms = []
        if role.permissions.administrator:
            perms.append("Administrator")
        if role.permissions.manage_guild:
            perms.append("Manage Server")
        if role.permissions.manage_roles:
            perms.append("Manage Roles")
        if role.permissions.manage_channels:
            perms.append("Manage Channels")
        if role.permissions.kick_members:
            perms.append("Kick Members")
        if role.permissions.ban_members:
            perms.append("Ban Members")
        if role.permissions.manage_messages:
            perms.append("Manage Messages")
        if role.permissions.mention_everyone:
            perms.append("Mention Everyone")
        
        embed = discord.Embed(
            color=role.color if role.color.value else Config.COLORS.DEFAULT
        )
        
        embed.set_author(name=f"{role.name} ({role.id})")
        
        # Role info
        info_text = f"**Color:** `{str(role.color)}`\n"
        info_text += f"**Position:** {role.position}\n"
        info_text += f"**Mentionable:** {'Yes' if role.mentionable else 'No'}\n"
        info_text += f"**Hoisted:** {'Yes' if role.hoist else 'No'}\n"
        info_text += f"**Members:** {member_count}"
        
        embed.add_field(name="Info", value=info_text, inline=True)
        
        # Permissions
        if perms:
            embed.add_field(name="Key Permissions", value=", ".join(perms[:6]), inline=True)
        
        embed.set_footer(text=f"Created: {role.created_at.strftime('%b %d, %Y')}")
        
        await ctx.send(embed=embed)

    @commands.command(name='channelinfo', aliases=['ci', 'channel'], extras={'example': 'channelinfo #general'})
    @commands.guild_only()
    async def channelinfo(self, ctx, channel: Optional[discord.TextChannel] = None):
        """Get information about a channel"""
        channel = channel or ctx.channel
        
        created_timestamp = int(channel.created_at.timestamp())
        
        embed = discord.Embed(color=Config.COLORS.DEFAULT)
        embed.set_author(name=f"#{channel.name} ({channel.id})")
        
        info_text = f"**Type:** {str(channel.type).replace('_', ' ').title()}\n"
        info_text += f"**Category:** {channel.category.name if channel.category else 'None'}\n"
        info_text += f"**Position:** {channel.position}\n"
        info_text += f"**NSFW:** {'Yes' if channel.is_nsfw() else 'No'}\n"
        info_text += f"**Slowmode:** {channel.slowmode_delay}s" if channel.slowmode_delay else f"**Slowmode:** Off"
        
        embed.add_field(name="Info", value=info_text, inline=False)
        
        if channel.topic:
            embed.add_field(name="Topic", value=channel.topic[:200], inline=False)
        
        embed.set_footer(text=f"Created: {channel.created_at.strftime('%b %d, %Y')}")
        
        await ctx.send(embed=embed)

    @commands.command(name='emojis', aliases=['emojilist', 'emotes'], extras={'example': 'emojis'})
    @commands.guild_only()
    async def emojis(self, ctx):
        """List all emojis in the server"""
        emojis = ctx.guild.emojis
        
        if not emojis:
            return await ctx.warn("No custom emojis found")
        
        static = [e for e in emojis if not e.animated]
        animated = [e for e in emojis if e.animated]
        
        embed = discord.Embed(color=Config.COLORS.DEFAULT)
        embed.set_author(name=f"Emojis in {ctx.guild.name}", icon_url=ctx.guild.icon.url if ctx.guild.icon else None)
        
        if static:
            static_text = " ".join([str(e) for e in static[:50]])
            if len(static) > 50:
                static_text += f" +{len(static) - 50} more"
            embed.add_field(name=f"Static ({len(static)})", value=static_text, inline=False)
        
        if animated:
            animated_text = " ".join([str(e) for e in animated[:50]])
            if len(animated) > 50:
                animated_text += f" +{len(animated) - 50} more"
            embed.add_field(name=f"Animated ({len(animated)})", value=animated_text, inline=False)
        
        embed.set_footer(text=f"{len(emojis)}/{ctx.guild.emoji_limit} slots used")
        
        await ctx.send(embed=embed)

    @commands.command(name='boosters', extras={'example': 'boosters'})
    @commands.guild_only()
    async def boosters(self, ctx):
        """List all server boosters"""
        boosters = [m for m in ctx.guild.members if m.premium_since]
        
        if not boosters:
            return await ctx.warn("No boosters found")
        
        # Sort by boost date
        boosters.sort(key=lambda m: m.premium_since)
        
        chunks = [boosters[i:i+15] for i in range(0, len(boosters), 15)]
        embeds = []
        
        for chunk in chunks:
            desc = "\n".join([f"{m.mention} - <t:{int(m.premium_since.timestamp())}:R>" for m in chunk])
            embed = discord.Embed(description=desc, color=0xf47fff)
            embed.set_author(name=f"Boosters ({len(boosters)})", icon_url=ctx.guild.icon.url if ctx.guild.icon else None)
            embeds.append(embed)
        
        if len(embeds) == 1:
            await ctx.send(embed=embeds[0], allowed_mentions=discord.AllowedMentions.none())
        else:
            view = PaginatorView(embeds, ctx.author.id)
            await ctx.send(embed=embeds[0], view=view, allowed_mentions=discord.AllowedMentions.none())

    @commands.command(name='oldest', extras={'example': 'oldest'})
    @commands.guild_only()
    async def oldest(self, ctx):
        """Show the oldest members in the server"""
        members = sorted(ctx.guild.members, key=lambda m: m.joined_at or discord.utils.utcnow())[:10]
        
        desc = "\n".join([
            f"`{i+1}.` {m.mention} - <t:{int(m.joined_at.timestamp())}:R>" 
            for i, m in enumerate(members) if m.joined_at
        ])
        
        embed = discord.Embed(description=desc, color=Config.COLORS.DEFAULT)
        embed.set_author(name=f"Oldest Members", icon_url=ctx.guild.icon.url if ctx.guild.icon else None)
        
        await ctx.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())

    @commands.command(name='newest', extras={'example': 'newest'})
    @commands.guild_only()
    async def newest(self, ctx):
        """Show the newest members in the server"""
        members = sorted(ctx.guild.members, key=lambda m: m.joined_at or discord.utils.utcnow(), reverse=True)[:10]
        
        desc = "\n".join([
            f"`{i+1}.` {m.mention} - <t:{int(m.joined_at.timestamp())}:R>" 
            for i, m in enumerate(members) if m.joined_at
        ])
        
        embed = discord.Embed(description=desc, color=Config.COLORS.DEFAULT)
        embed.set_author(name=f"Newest Members", icon_url=ctx.guild.icon.url if ctx.guild.icon else None)
        
        await ctx.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())

    @commands.command(name='inrole', extras={'example': 'inrole @Moderator'})
    @commands.guild_only()
    async def inrole(self, ctx, *, role: discord.Role = None):
        """List members with a specific role"""
        if not role:
            return await ctx.send_help(ctx.command)
        
        members = role.members
        
        if not members:
            return await ctx.warn(f"No members have {role.mention}")
        
        chunks = [members[i:i+20] for i in range(0, len(members), 20)]
        embeds = []
        
        for chunk in chunks:
            desc = "\n".join([f"{m.mention}" for m in chunk])
            embed = discord.Embed(description=desc, color=role.color if role.color.value else Config.COLORS.DEFAULT)
            embed.set_author(name=f"Members with {role.name} ({len(members)})")
            embeds.append(embed)
        
        if len(embeds) == 1:
            await ctx.send(embed=embeds[0], allowed_mentions=discord.AllowedMentions.none())
        else:
            view = PaginatorView(embeds, ctx.author.id)
            await ctx.send(embed=embeds[0], view=view, allowed_mentions=discord.AllowedMentions.none())

    @commands.command(name='8ball', aliases=['8b', 'magic8ball'], extras={'example': '8ball Will I win?'})
    async def eightball(self, ctx, *, question: str = None):
        """Ask the magic 8ball a question"""
        if not question:
            return await ctx.send_help(ctx.command)
        
        responses = [
            "Yes", "No", "Maybe", "Definitely", "Absolutely not",
            "Most likely", "Don't count on it", "Yes, definitely",
            "Ask again later", "Cannot predict now", "Outlook good",
            "Very doubtful", "Without a doubt", "My sources say no"
        ]
        
        embed = discord.Embed(color=Config.COLORS.DEFAULT)
        embed.add_field(name="Question", value=question, inline=False)
        embed.add_field(name="Answer", value=f"🎱 {random.choice(responses)}", inline=False)
        
        await ctx.send(embed=embed)

    @commands.command(name='choose', aliases=['pick'], extras={'example': 'choose pizza, burger, tacos'})
    async def choose(self, ctx, *, choices: str = None):
        """Choose between multiple options (comma separated)"""
        if not choices:
            return await ctx.send_help(ctx.command)
        
        options = [c.strip() for c in choices.split(',') if c.strip()]
        
        if len(options) < 2:
            return await ctx.deny("Give me at least 2 options separated by commas")
        
        choice = random.choice(options)
        
        embed = discord.Embed(
            description=f"🎯 I choose **{choice}**",
            color=Config.COLORS.DEFAULT
        )
        
        await ctx.send(embed=embed)

    @commands.group(name="timezone", aliases=["tz"], invoke_without_command=True)
    async def timezone_group(self, ctx, member: discord.Member = None):
        """Show your or another user's timezone"""
        if pytz is None:
            return await ctx.deny("Timezone module not installed")

        target = member or ctx.author
        user_tz = get_user_timezone(target.id)

        if not user_tz:
            if target == ctx.author:
                return await ctx.deny(f"You haven't set your timezone yet. Use `{ctx.prefix}timezone set <timezone>`")
            else:
                return await ctx.deny(f"{target.display_name} hasn't set their timezone")

        try:
            tz = pytz.timezone(user_tz)
            now = datetime.now(tz)

            time_str = now.strftime("%I:%M %p")
            date_str = now.strftime("%A, %B %d, %Y")

            embed = discord.Embed(color=0x2b2d31)
            embed.set_author(name=f"{target.display_name}'s Time", icon_url=target.display_avatar.url)
            embed.add_field(name="Time", value=time_str, inline=True)
            embed.add_field(name="Date", value=date_str, inline=True)
            embed.add_field(name="Timezone", value=user_tz.replace("_", "\\_"), inline=True)

            await ctx.send(embed=embed)
        except Exception as e:
            await ctx.deny(f"Error: {e}")

    @timezone_group.command(name="set")
    async def timezone_set(self, ctx, *, tz: str = None):
        """Set your timezone"""
        if pytz is None:
            return await ctx.deny("Timezone module not installed")

        if not tz:
            return await ctx.deny(f"Usage: `{ctx.prefix}timezone set <timezone>`\nExample: `{ctx.prefix}timezone set America/New_York` or `{ctx.prefix}timezone set New York`")

        # Try to validate the timezone directly first
        try:
            pytz.timezone(tz)
            set_user_timezone(ctx.author.id, tz)
            return await ctx.approve(f"Timezone set to `{tz}`")
        except pytz.UnknownTimeZoneError:
            pass

        # Try to find a match by city/country name
        tz_lower = tz.lower().replace(" ", "_")
        matches = []

        for timezone in pytz.all_timezones:
            tz_parts = timezone.lower().split("/")
            if tz_lower in tz_parts[-1] or any(tz_lower in part for part in tz_parts):
                matches.append(timezone)

        if len(matches) == 1:
            set_user_timezone(ctx.author.id, matches[0])
            return await ctx.approve(f"Timezone set to `{matches[0]}`")
        elif matches:
            suggestions = "\n".join([f"`{m}`" for m in matches[:10]])
            return await ctx.deny(f"Multiple timezones found. Did you mean:\n{suggestions}")

        return await ctx.deny(f"Invalid timezone `{tz}`. Use format like `America/New_York`, `Europe/London`, or city name like `New York`")

    @timezone_group.command(name="list")
    async def timezone_list(self, ctx, region: str = None):
        """List available timezones"""
        if pytz is None:
            return await ctx.deny("Timezone module not installed")

        if not region:
            regions = set()
            for tz in pytz.all_timezones:
                if "/" in tz:
                    regions.add(tz.split("/")[0])

            embed = discord.Embed(
                title="Timezone Regions",
                description="\n".join(sorted(regions)),
                color=0x2b2d31
            )
            embed.set_footer(text=f"Use {ctx.prefix}timezone list <region> to see timezones")
            return await ctx.send(embed=embed)

        matches = [tz for tz in pytz.all_timezones if tz.lower().startswith(region.lower())][:20]
        if not matches:
            return await ctx.deny(f"No timezones found for region `{region}`")

        embed = discord.Embed(
            title=f"Timezones in {region}",
            description="\n".join([f"`{tz}`" for tz in matches]),
            color=0x2b2d31
        )
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Utility(bot))
