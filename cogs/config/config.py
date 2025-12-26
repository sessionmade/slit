import discord
import aiohttp
import json
import asyncio
from discord.ext import commands
from src.config import Config
import base64
import aiohttp
from datetime import datetime, timezone

class StarboardView(discord.ui.View):
    """View with jump-to-message button."""
    
    def __init__(self, message_url: str):
        super().__init__()
        self.add_item(discord.ui.Button(
            label="Jump to Message",
            url=message_url,
            style=discord.ButtonStyle.link
        ))


class GuildConfig(commands.Cog):
    """Guild configuration commands: icon, banner, splash, starboard."""

    def __init__(self, bot):
        self.bot = bot
        self.starboard_path = "src/starboard.json"
        self.starboard_data: dict = {}
        bot.loop.create_task(self._load_starboard())
        # Antinuke storage
        self.antinuke_path = "src/antinuke.json"
        self.antinuke_data: dict = {}
        self.recent_actions: dict = {}  # guild_id -> executor_id -> list[timestamp]
        bot.loop.create_task(self._load_antinuke())

    async def download_to_data_uri(self, url: str):
        """Download an image and convert it to a data URI"""
        from aiohttp import ClientSession
        from base64 import b64encode
        
        async with ClientSession() as session:
            try:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        return None
                    img = await resp.read()
            except:
                return None
        encoded = b64encode(img).decode()
        return f"data:image/png;base64,{encoded}"
    
    async def _load_starboard(self):
        await self.bot.wait_until_ready()
        loop = asyncio.get_event_loop()

        def _read():
            try:
                with open(self.starboard_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except FileNotFoundError:
                return {}
            except Exception:
                return {}

        self.starboard_data = await loop.run_in_executor(None, _read)

    async def _save_starboard(self):
        loop = asyncio.get_event_loop()

        def _write(d):
            with open(self.starboard_path, "w", encoding="utf-8") as f:
                json.dump(d, f, ensure_ascii=False, indent=2)

        await loop.run_in_executor(None, _write, self.starboard_data)

    def _get_starboard_config(self, guild_id: int) -> dict:
        key = str(guild_id)
        if key not in self.starboard_data:
            self.starboard_data[key] = {"channel_id": None, "emoji": None, "count": 3, "posted_messages": {}}
        return self.starboard_data[key]

    def _is_starboard_enabled(self, guild_id: int) -> bool:
        cfg = self._get_starboard_config(guild_id)
        return cfg.get("channel_id") and cfg.get("emoji")

    async def _get_reaction_count(self, message: discord.Message, emoji: str) -> int:
        """Get reaction count for specific emoji."""
        for reaction in message.reactions:
            if str(reaction.emoji) == emoji:
                return reaction.count
        return 0

    async def _build_starboard_embed(self, message: discord.Message, count: int) -> discord.Embed:
        """Build embed for starboard message."""
        embed = discord.Embed(
            description=message.content or "(no text content)",
            color=discord.Color.gold(),
            timestamp=datetime.now(timezone.utc)
        )
        embed.set_author(
            name=message.author.display_name,
            icon_url=message.author.display_avatar.url
        )
        embed.set_footer(text=f"⭐ {count}")

        # Add image if present
        if message.attachments:
            for att in message.attachments:
                if att.content_type and att.content_type.startswith('image/'):
                    embed.set_image(url=att.url)
                    break

        return embed

    async def _post_or_update_starboard(self, message: discord.Message, guild_id: int):
        """Post new starboard message or update existing one."""
        cfg = self._get_starboard_config(guild_id)
        channel_id = cfg.get("channel_id")
        emoji = cfg.get("emoji")
        threshold = cfg.get("count", 3)

        if not channel_id or not emoji:
            return

        # Get current reaction count
        reaction_count = await self._get_reaction_count(message, emoji)

        if reaction_count < threshold:
            # Below threshold: don't post or delete if exists
            msg_key = f"{message.channel.id}_{message.id}"
            if msg_key in cfg.get("posted_messages", {}):
                try:
                    sb_msg = cfg["posted_messages"][msg_key]
                    channel = self.bot.get_channel(channel_id)
                    if channel:
                        try:
                            sb = await channel.fetch_message(sb_msg)
                            await sb.delete()
                        except discord.NotFound:
                            pass
                except Exception:
                    pass
                del cfg["posted_messages"][msg_key]
                await self._save_starboard()
            return

        # Above threshold: post or update
        channel = self.bot.get_channel(channel_id)
        if not channel:
            return

        embed = await self._build_starboard_embed(message, reaction_count)
        view = StarboardView(message.jump_url)
        msg_key = f"{message.channel.id}_{message.id}"
        posted = cfg.get("posted_messages", {})

        try:
            if msg_key in posted:
                # Update existing
                try:
                    sb = await channel.fetch_message(posted[msg_key])
                    await sb.edit(embed=embed, view=view)
                except discord.NotFound:
                    # Message deleted, post new
                    sb = await channel.send(embed=embed, view=view)
                    posted[msg_key] = sb.id
            else:
                # Post new
                sb = await channel.send(embed=embed, view=view)
                posted[msg_key] = sb.id

            await self._save_starboard()
        except Exception as e:
            print(f"Starboard error: {e}")

    # -------------------- Antinuke helpers & listeners --------------------
    async def _load_antinuke(self):
        await self.bot.wait_until_ready()
        loop = asyncio.get_event_loop()

        def _read():
            try:
                with open(self.antinuke_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except FileNotFoundError:
                return {}
            except Exception:
                return {}

        self.antinuke_data = await loop.run_in_executor(None, _read)

    async def _save_antinuke(self):
        loop = asyncio.get_event_loop()

        def _write(d):
            with open(self.antinuke_path, "w", encoding="utf-8") as f:
                json.dump(d, f, ensure_ascii=False, indent=2)

        await loop.run_in_executor(None, _write, self.antinuke_data)

    def _get_antinuke_config(self, guild_id: int) -> dict:
        key = str(guild_id)
        if key not in self.antinuke_data:
            # default config
            self.antinuke_data[key] = {
                "enabled": False,
                "threshold": 3,
                "window_seconds": 10,
                "punish": "kick",  # kick | ban | demote
                "bot_whitelist": [],
                "user_whitelist": [],
                "exempt_roles": [],
                "modlog_channel_id": None,
                "notify_owner": False,
                "notify_role_id": None
            }
        return self.antinuke_data[key]

    async def _punish_executor(self, guild: discord.Guild, executor: discord.Member, punish: str):
        cfg = self._get_antinuke_config(guild.id)
        modlog_id = cfg.get("modlog_channel_id")
        notify_owner = cfg.get("notify_owner", False)

        try:
            if punish == "ban":
                await guild.ban(executor, reason="Antinuke triggered")
            elif punish == "kick":
                await guild.kick(executor, reason="Antinuke triggered")
            elif punish == "demote":
                # remove roles with administrator/manage_guild perms
                for role in list(executor.roles):
                    if role.is_default():
                        continue
                    try:
                        await executor.remove_roles(role, reason="Antinuke triggered")
                    except Exception:
                        pass
        except Exception as e:
            print(f"Failed to punish executor: {e}")

        # send modlog entry if configured
        try:
            notify_role_id = cfg.get("notify_role_id")
            notify_role = guild.get_role(notify_role_id) if notify_role_id else None

            embed = discord.Embed(title="Antinuke Action",
                                  description=f"{executor} was {punish}ed by antinuke",
                                  color=discord.Color.red(),
                                  timestamp=datetime.now(timezone.utc))
            embed.add_field(name="Executor", value=f"{executor} ({executor.id})", inline=True)
            embed.add_field(name="Guild", value=f"{guild.name} ({guild.id})", inline=True)

            if modlog_id:
                channel = self.bot.get_channel(modlog_id)
                if channel and isinstance(channel, discord.TextChannel):
                    try:
                        if notify_role:
                            await channel.send(content=notify_role.mention, embed=embed)
                        else:
                            await channel.send(embed=embed)
                    except Exception:
                        pass

            # DM guild owner if requested
            if notify_owner:
                try:
                    owner = guild.owner
                    if owner:
                        await owner.send(embed=embed)
                except Exception:
                    pass
        except Exception:
            pass

    async def _register_action_and_check(self, guild: discord.Guild, executor: discord.Member) -> bool:
        """Record an action by executor and return True if threshold exceeded."""
        cfg = self._get_antinuke_config(guild.id)
        if not cfg.get("enabled"):
            return False

        gid = str(guild.id)
        eid = str(executor.id)
        now = int(datetime.now(timezone.utc).timestamp())

        self.recent_actions.setdefault(gid, {})
        self.recent_actions[gid].setdefault(eid, [])
        self.recent_actions[gid][eid].append(now)

        # prune
        window = cfg.get("window_seconds", 10)
        cutoff = now - int(window)
        self.recent_actions[gid][eid] = [t for t in self.recent_actions[gid][eid] if t >= cutoff]

        return len(self.recent_actions[gid][eid]) >= int(cfg.get("threshold", 3))

    async def _get_audit_executor(self, guild: discord.Guild, action: discord.AuditLogAction, target_id: int):
        try:
            async for entry in guild.audit_logs(limit=5, action=action):
                if entry.target and getattr(entry.target, 'id', None) == target_id:
                    return entry.user
        except Exception:
            return None
        return None

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User):
        cfg = self._get_antinuke_config(guild.id)
        if not cfg.get("enabled"):
            return

        executor = await self._get_audit_executor(guild, discord.AuditLogAction.ban, user.id)
        if not executor or executor.bot:
            return

        # check whitelist and exempt roles
        bot_wl = cfg.get("bot_whitelist", [])
        user_wl = cfg.get("user_whitelist", [])
        exempt = cfg.get("exempt_roles", [])

        if str(executor.id) in map(str, bot_wl + user_wl):
            return

        member = guild.get_member(executor.id)
        if member:
            for r in member.roles:
                if str(r.id) in map(str, exempt):
                    return

        triggered = await self._register_action_and_check(guild, member or executor)
        if triggered:
            punish = cfg.get("punish", "kick")
            if member:
                await self._punish_executor(guild, member, punish)
                if guild.system_channel:
                    try:
                        await guild.system_channel.send(f"Antinuke: punished {executor} for mass bans")
                    except Exception:
                        pass

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role):
        guild = role.guild
        cfg = self._get_antinuke_config(guild.id)
        if not cfg.get("enabled"):
            return

        executor = await self._get_audit_executor(guild, discord.AuditLogAction.role_delete, role.id)
        if not executor or executor.bot:
            return

        bot_wl = cfg.get("bot_whitelist", [])
        user_wl = cfg.get("user_whitelist", [])
        exempt = cfg.get("exempt_roles", [])

        if str(executor.id) in map(str, bot_wl + user_wl):
            return

        member = guild.get_member(executor.id)
        if member:
            for r in member.roles:
                if str(r.id) in map(str, exempt):
                    return

        triggered = await self._register_action_and_check(guild, member or executor)
        if triggered:
            punish = cfg.get("punish", "kick")
            if member:
                await self._punish_executor(guild, member, punish)
                if guild.system_channel:
                    try:
                        await guild.system_channel.send(f"Antinuke: punished {executor} for role deletions")
                    except Exception:
                        pass

    async def _setup_autorole_table(self):
        """Create autorole table if it doesn't exist"""
        if not self.bot.db_pool:
            return
        
        try:
            async with self.bot.db_pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute("""
                        CREATE TABLE IF NOT EXISTS autoroles (
                            id INT AUTO_INCREMENT PRIMARY KEY,
                            guild_id BIGINT NOT NULL,
                            role_id BIGINT NOT NULL,
                            UNIQUE KEY unique_autorole (guild_id, role_id)
                        )
                    """)
        except Exception as e:
            print(f"Error setting up autorole table: {e}")

    async def _get_autoroles(self, guild_id: int) -> list:
        """Get all autoroles for a guild"""
        if not self.bot.db_pool:
            return []
        
        try:
            async with self.bot.db_pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        "SELECT role_id FROM autoroles WHERE guild_id = %s",
                        (guild_id,)
                    )
                    rows = await cur.fetchall()
                    return [row[0] for row in rows]
        except Exception as e:
            print(f"Error getting autoroles: {e}")
            return []

    async def _add_autorole(self, guild_id: int, role_id: int) -> bool:
        """Add autorole to guild"""
        if not self.bot.db_pool:
            return False
        
        try:
            async with self.bot.db_pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        "INSERT INTO autoroles (guild_id, role_id) VALUES (%s, %s)",
                        (guild_id, role_id)
                    )
                    await conn.commit()
                    return True
        except Exception as e:
            print(f"Error adding autorole: {e}")
            return False

    async def _remove_autorole(self, guild_id: int, role_id: int) -> bool:
        """Remove autorole from guild"""
        if not self.bot.db_pool:
            return False
        
        try:
            async with self.bot.db_pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        "DELETE FROM autoroles WHERE guild_id = %s AND role_id = %s",
                        (guild_id, role_id)
                    )
                    await conn.commit()
                    return True
        except Exception as e:
            print(f"Error removing autorole: {e}")
            return False

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        guild = channel.guild
        cfg = self._get_antinuke_config(guild.id)
        if not cfg.get("enabled"):
            return

        executor = await self._get_audit_executor(guild, discord.AuditLogAction.channel_delete, channel.id)
        if not executor or executor.bot:
            return

        bot_wl = cfg.get("bot_whitelist", [])
        user_wl = cfg.get("user_whitelist", [])
        exempt = cfg.get("exempt_roles", [])

        if str(executor.id) in map(str, bot_wl + user_wl):
            return

        member = guild.get_member(executor.id)
        if member:
            for r in member.roles:
                if str(r.id) in map(str, exempt):
                    return

        triggered = await self._register_action_and_check(guild, member or executor)
        if triggered:
            punish = cfg.get("punish", "kick")
            if member:
                await self._punish_executor(guild, member, punish)
                if guild.system_channel:
                    try:
                        await guild.system_channel.send(f"Antinuke: punished {executor} for channel deletions")
                    except Exception:
                        pass

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction: discord.Reaction, user: discord.User):
        if not reaction.message.guild or user.bot:
            return

        if not self._is_starboard_enabled(reaction.message.guild.id):
            return

        cfg = self._get_starboard_config(reaction.message.guild.id)
        if str(reaction.emoji) == cfg.get("emoji"):
            await self._post_or_update_starboard(reaction.message, reaction.message.guild.id)

    @commands.Cog.listener()
    async def on_reaction_remove(self, reaction: discord.Reaction, user: discord.User):
        if not reaction.message.guild or user.bot:
            return

        if not self._is_starboard_enabled(reaction.message.guild.id):
            return

        cfg = self._get_starboard_config(reaction.message.guild.id)
        if str(reaction.emoji) == cfg.get("emoji"):
            await self._post_or_update_starboard(reaction.message, reaction.message.guild.id)

    async def _fetch_image(self, url: str) -> bytes:
        """Fetch image from URL."""
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    raise ValueError(f"HTTP {resp.status}")
                return await resp.read()

    async def _get_image_bytes(self, ctx, url: str = None) -> bytes:
        """Get image bytes from URL or first attachment."""
        if url:
            return await self._fetch_image(url)
        elif ctx.message.attachments:
            att = ctx.message.attachments[0]
            if not att.content_type or not att.content_type.startswith('image/'):
                raise ValueError("Attachment is not an image")
            return await att.read()
        else:
            raise ValueError("No image URL or attachment provided")

    @commands.group(name='set', invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def set(self, ctx):
        """Guild configuration group."""
        await ctx.send_help(ctx.command)

    @set.command(name='icon')
    @commands.has_permissions(manage_guild=True)
    async def set_icon(self, ctx, url: str = None):
        """Set guild icon from URL or attachment.

        Usage: ;set icon <url> or ;set icon (with attachment)
        """
        try:
            image_bytes = await self._get_image_bytes(ctx, url)
            await ctx.guild.edit(icon=image_bytes)
            await ctx.approve("Guild icon updated")
        except ValueError as e:
            await ctx.deny(f"Invalid image: {str(e)}")
        except discord.HTTPException as e:
            await ctx.deny(f"Discord error: {e}")
        except Exception as e:
            await ctx.deny(f"Error: {str(e)}")

    @set.command(name='banner')
    @commands.has_permissions(manage_guild=True)
    async def set_banner(self, ctx, url: str = None):
        """Set guild banner from URL or attachment.

        Usage: ;set banner <url> or ;set banner (with attachment)
        """
        try:
            image_bytes = await self._get_image_bytes(ctx, url)
            await ctx.guild.edit(banner=image_bytes)
            await ctx.approve("Guild banner updated")
        except ValueError as e:
            await ctx.deny(f"Invalid image: {str(e)}")
        except discord.HTTPException as e:
            await ctx.deny(f"Discord error: {e}")
        except Exception as e:
            await ctx.deny(f"Error: {str(e)}")

    @set.command(name='splash')
    @commands.has_permissions(manage_guild=True)
    async def set_splash(self, ctx, url: str = None):
        """Set guild splash from URL or attachment.

        Usage: ;set splash <url> or ;set splash (with attachment)
        Note: Requires guild to have INVITE_SPLASH feature.
        """
        try:
            image_bytes = await self._get_image_bytes(ctx, url)
            await ctx.guild.edit(splash=image_bytes)
            await ctx.approve("Guild splash updated")
        except ValueError as e:
            await ctx.deny(f"Invalid image: {str(e)}")
        except discord.HTTPException as e:
            await ctx.deny(f"Discord error: {e}")
        except Exception as e:
            await ctx.deny(f"Error: {str(e)}")

    @commands.group(name="starboard", invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def starboard(self, ctx):
        """Manage starboard."""
        await ctx.send_help(ctx.command)

    @starboard.command(name="setup")
    @commands.has_permissions(manage_guild=True)
    async def starboard_setup(self, ctx, channel: discord.TextChannel = None, emoji: str = None, count: int = None):
        """Setup starboard: !starboard setup #channel emoji count
        
        Example: ;starboard setup #starboard ⭐ 3
        """
        if not channel or not emoji or count is None:
            return await ctx.send_help(ctx.command)

        cfg = self._get_starboard_config(ctx.guild.id)
        cfg["channel_id"] = channel.id
        cfg["emoji"] = emoji
        cfg["count"] = count
        cfg.setdefault("posted_messages", {})

        await self._save_starboard()
        await ctx.approve(f"Starboard setup: {channel.mention} with {emoji} threshold {count}")

    @starboard.command(name="channel")
    @commands.has_permissions(manage_guild=True)
    async def starboard_channel(self, ctx, channel: discord.TextChannel = None):
        """Set starboard channel."""
        if not channel:
            return await ctx.send_help(ctx.command)

        cfg = self._get_starboard_config(ctx.guild.id)
        cfg["channel_id"] = channel.id
        await self._save_starboard()
        await ctx.approve(f"Starboard channel set to {channel.mention}")

    @starboard.command(name="emoji")
    @commands.has_permissions(manage_guild=True)
    async def starboard_emoji(self, ctx, emoji: str = None):
        """Set starboard emoji."""
        if not emoji:
            return await ctx.send_help(ctx.command)

        cfg = self._get_starboard_config(ctx.guild.id)
        cfg["emoji"] = emoji
        await self._save_starboard()
        await ctx.approve(f"Starboard emoji set to {emoji}")

    @starboard.command(name="count")
    @commands.has_permissions(manage_guild=True)
    async def starboard_count(self, ctx, count: int = None):
        """Set starboard reaction threshold."""
        if count is None or count < 1:
            return await ctx.send_help(ctx.command)

        cfg = self._get_starboard_config(ctx.guild.id)
        cfg["count"] = count
        await self._save_starboard()
        await ctx.approve(f"Starboard threshold set to {count}")

    @starboard.command(name="info")
    async def starboard_info(self, ctx):
        """Show starboard configuration."""
        cfg = self._get_starboard_config(ctx.guild.id)
        channel_id = cfg.get("channel_id")
        emoji = cfg.get("emoji")
        count = cfg.get("count", 3)

        if not channel_id or not emoji:
            return await ctx.warn("Starboard not configured")

        channel = self.bot.get_channel(channel_id)
        ch_name = channel.mention if channel else f"(Unknown channel {channel_id})"

        embed = discord.Embed(color=discord.Color.gold())
        embed.set_author(name="Starboard Configuration", icon_url=ctx.guild.icon.url if ctx.guild.icon else None)
        embed.add_field(name="Channel", value=ch_name, inline=False)
        embed.add_field(name="Emoji", value=emoji, inline=True)
        embed.add_field(name="Threshold", value=str(count), inline=True)

        await ctx.send(embed=embed)

    @starboard.command(name="disable")
    @commands.has_permissions(manage_guild=True)
    async def starboard_disable(self, ctx):
        """Disable starboard."""
        cfg = self._get_starboard_config(ctx.guild.id)
        cfg["channel_id"] = None
        cfg["emoji"] = None
        await self._save_starboard()
        await ctx.approve("Starboard disabled")

    @commands.group(name="antinuke", invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def antinuke(self, ctx):
        """Manage antinuke settings."""
        await ctx.send_help(ctx.command)

    @antinuke.command(name="enable")
    @commands.has_permissions(manage_guild=True)
    async def antinuke_enable(self, ctx):
        """Enable antinuke protection."""
        cfg = self._get_antinuke_config(ctx.guild.id)
        cfg["enabled"] = True
        await self._save_antinuke()
        await ctx.approve("Antinuke enabled")

    @antinuke.command(name="disable")
    @commands.has_permissions(manage_guild=True)
    async def antinuke_disable(self, ctx):
        """Disable antinuke protection."""
        cfg = self._get_antinuke_config(ctx.guild.id)
        cfg["enabled"] = False
        await self._save_antinuke()
        await ctx.approve("Antinuke disabled")

    @antinuke.command(name="status")
    async def antinuke_status(self, ctx):
        """Show current antinuke configuration and settings."""
        cfg = self._get_antinuke_config(ctx.guild.id)
        enabled = cfg.get("enabled")
        threshold = cfg.get("threshold")
        window = cfg.get("window_seconds")
        punish = cfg.get("punish")
        wl = cfg.get("bot_whitelist", [])
        uwl = cfg.get("user_whitelist", [])
        exempt = cfg.get("exempt_roles", [])
        modlog = cfg.get("modlog_channel_id")
        notify_owner = cfg.get("notify_owner", False)

        embed = discord.Embed(color=discord.Color.red() if enabled else discord.Color.greyple())
        embed.set_author(name="Antinuke Status")
        embed.add_field(name="Enabled", value=str(enabled), inline=True)
        embed.add_field(name="Threshold", value=str(threshold), inline=True)
        embed.add_field(name="Window (s)", value=str(window), inline=True)
        embed.add_field(name="Punish", value=str(punish), inline=True)
        embed.add_field(name="Modlog", value=(f"<#{modlog}>" if modlog else "(none)"), inline=False)
        embed.add_field(name="Notify Owner", value=str(notify_owner), inline=True)
        embed.add_field(name="Bot Whitelist", value=(", ".join(wl) if wl else "(empty)"), inline=False)
        embed.add_field(name="User Whitelist", value=(", ".join(uwl) if uwl else "(empty)"), inline=False)
        embed.add_field(name="Exempt Roles", value=(", ".join(exempt) if exempt else "(empty)"), inline=False)
        await ctx.send(embed=embed)

    @antinuke.command(name="threshold")
    @commands.has_permissions(manage_guild=True)
    async def antinuke_threshold(self, ctx, count: int = None):
        """Set action threshold (number of destructive actions)."""
        if count is None or count < 1:
            return await ctx.send_help(ctx.command)
        cfg = self._get_antinuke_config(ctx.guild.id)
        cfg["threshold"] = count
        await self._save_antinuke()
        await ctx.approve(f"Antinuke threshold set to {count}")

    @antinuke.command(name="window")
    @commands.has_permissions(manage_guild=True)
    async def antinuke_window(self, ctx, seconds: int = None):
        """Set time window in seconds to count actions."""
        if seconds is None or seconds < 1:
            return await ctx.send_help(ctx.command)
        cfg = self._get_antinuke_config(ctx.guild.id)
        cfg["window_seconds"] = seconds
        await self._save_antinuke()
        await ctx.approve(f"Antinuke window set to {seconds}s")

    @antinuke.command(name="punish")
    @commands.has_permissions(manage_guild=True)
    async def antinuke_punish(self, ctx, punish: str = None):
        """Set punishment: kick | ban | demote"""
        if punish not in ("kick", "ban", "demote"):
            return await ctx.send_help(ctx.command)
        cfg = self._get_antinuke_config(ctx.guild.id)
        cfg["punish"] = punish
        await self._save_antinuke()
        await ctx.approve(f"Antinuke punish set to {punish}")

    @antinuke.group(name="bot", invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def antinuke_bot(self, ctx):
        """Manage bot whitelist."""
        await ctx.send_help(ctx.command)

    @antinuke_bot.command(name="add")
    @commands.has_permissions(manage_guild=True)
    async def antinuke_bot_add(self, ctx, member: discord.Member = None):
        """Add bot to whitelist."""
        if not member:
            return await ctx.send_help(ctx.command)
        cfg = self._get_antinuke_config(ctx.guild.id)
        wl = cfg.setdefault("bot_whitelist", [])
        if str(member.id) in map(str, wl):
            return await ctx.warn("Already whitelisted")
        wl.append(str(member.id))
        await self._save_antinuke()
        await ctx.approve(f"Added {member.mention}")

    @antinuke_bot.command(name="remove")
    @commands.has_permissions(manage_guild=True)
    async def antinuke_bot_remove(self, ctx, member: discord.Member = None):
        """Remove bot from whitelist."""
        if not member:
            return await ctx.send_help(ctx.command)
        cfg = self._get_antinuke_config(ctx.guild.id)
        wl = cfg.setdefault("bot_whitelist", [])
        if str(member.id) not in map(str, wl):
            return await ctx.warn("Not whitelisted")
        wl[:] = [x for x in wl if str(x) != str(member.id)]
        await self._save_antinuke()
        await ctx.approve(f"Removed {member.mention}")

    @antinuke_bot.command(name="list")
    async def antinuke_bot_list(self, ctx):
        """Show whitelisted bots."""
        cfg = self._get_antinuke_config(ctx.guild.id)
        wl = cfg.get("bot_whitelist", [])
        if not wl:
            return await ctx.warn("Bot whitelist is empty")
        lines = []
        for item in wl:
            member = ctx.guild.get_member(int(item))
            lines.append(member.mention if member else f"{item}")
        await ctx.send("\n".join(lines))

    @antinuke.command(name="add")
    @commands.has_permissions(manage_guild=True)
    async def antinuke_add(self, ctx, member: discord.Member = None):
        """Add member to whitelist."""
        if not member:
            return await ctx.send_help(ctx.command)
        cfg = self._get_antinuke_config(ctx.guild.id)
        wl = cfg.setdefault("user_whitelist", [])
        if str(member.id) in map(str, wl):
            return await ctx.warn("Already whitelisted")
        wl.append(str(member.id))
        await self._save_antinuke()
        await ctx.approve(f"Added {member.mention}")

    @antinuke.command(name="remove")
    @commands.has_permissions(manage_guild=True)
    async def antinuke_remove(self, ctx, member: discord.Member = None):
        """Remove member from whitelist."""
        if not member:
            return await ctx.send_help(ctx.command)
        cfg = self._get_antinuke_config(ctx.guild.id)
        wl = cfg.setdefault("user_whitelist", [])
        if str(member.id) not in map(str, wl):
            return await ctx.warn("Not whitelisted")
        wl[:] = [x for x in wl if str(x) != str(member.id)]
        await self._save_antinuke()
        await ctx.approve(f"Removed {member.mention}")

    @antinuke.command(name="list")
    async def antinuke_list(self, ctx):
        """Show whitelisted members."""
        cfg = self._get_antinuke_config(ctx.guild.id)
        wl = cfg.get("user_whitelist", [])
        if not wl:
            return await ctx.warn("Whitelist is empty")
        lines = []
        for item in wl:
            member = ctx.guild.get_member(int(item))
            lines.append(member.mention if member else f"{item}")
        await ctx.send("\n".join(lines))

    @antinuke.command(name="exadd")
    @commands.has_permissions(manage_guild=True)
    async def antinuke_exadd(self, ctx, role: discord.Role = None):
        """Add role to exempt list."""
        if not role:
            return await ctx.send_help(ctx.command)
        cfg = self._get_antinuke_config(ctx.guild.id)
        er = cfg.setdefault("exempt_roles", [])
        if str(role.id) in map(str, er):
            return await ctx.warn("Already exempt")
        er.append(str(role.id))
        await self._save_antinuke()
        await ctx.approve(f"Added {role.mention}")

    @antinuke.command(name="exremove")
    @commands.has_permissions(manage_guild=True)
    async def antinuke_exremove(self, ctx, role: discord.Role = None):
        """Remove role from exempt list."""
        if not role:
            return await ctx.send_help(ctx.command)
        cfg = self._get_antinuke_config(ctx.guild.id)
        er = cfg.setdefault("exempt_roles", [])
        if str(role.id) not in map(str, er):
            return await ctx.warn("Not exempt")
        er[:] = [x for x in er if str(x) != str(role.id)]
        await self._save_antinuke()
        await ctx.approve(f"Removed {role.mention}")

    @antinuke.command(name="exlist")
    async def antinuke_exlist(self, ctx):
        """Show exempt roles."""
        cfg = self._get_antinuke_config(ctx.guild.id)
        er = cfg.get("exempt_roles", [])
        if not er:
            return await ctx.warn("No exempt roles")
        lines = []
        for item in er:
            role = ctx.guild.get_role(int(item))
            lines.append(role.mention if role else f"{item}")
        await ctx.send("\n".join(lines))

    @antinuke.command(name="modlog")
    @commands.has_permissions(manage_guild=True)
    async def antinuke_modlog(self, ctx, channel: discord.TextChannel = None):
        """Set or clear modlog channel for antinuke messages.
        Use no argument to clear."""
        cfg = self._get_antinuke_config(ctx.guild.id)
        if channel is None:
            cfg["modlog_channel_id"] = None
            await self._save_antinuke()
            return await ctx.approve("Cleared antinuke modlog channel")
        cfg["modlog_channel_id"] = channel.id
        await self._save_antinuke()
        await ctx.approve(f"Set antinuke modlog to {channel.mention}")

    @antinuke.command(name="notifyowner")
    @commands.has_permissions(manage_guild=True)
    async def antinuke_notify_owner(self, ctx, flag: str = None):
        """Enable or disable DM notifications to guild owner on antinuke actions."""
        if flag not in ("on", "off"):
            return await ctx.send_help(ctx.command)
        cfg = self._get_antinuke_config(ctx.guild.id)
        cfg["notify_owner"] = (flag == "on")
        await self._save_antinuke()
        await ctx.approve(f"Notify owner set to {cfg['notify_owner']}")

    @antinuke.command(name="notifyrole")
    @commands.has_permissions(manage_guild=True)
    async def antinuke_notify_role(self, ctx, role: discord.Role = None):
        """Set a role to mention on antinuke punishments. Use no argument to clear."""
        cfg = self._get_antinuke_config(ctx.guild.id)
        if role is None:
            cfg["notify_role_id"] = None
            await self._save_antinuke()
            return await ctx.approve("Cleared notify role")
        cfg["notify_role_id"] = role.id
        await self._save_antinuke()
        await ctx.approve(f"Set notify role to {role.mention}")

    @antinuke.command(name="reset_counts")
    @commands.has_permissions(manage_guild=True)
    async def antinuke_reset_counts(self, ctx):
        """Reset action counters for this guild."""
        gid = str(ctx.guild.id)
        self.recent_actions.pop(gid, None)
        await ctx.approve("Reset recent action counters for this guild")

    @antinuke.command(name="test")
    @commands.has_permissions(manage_guild=True)
    async def antinuke_test(self, ctx, member: discord.Member = None):
        """Run a test of the antinuke punish flow against a member (dry-run)."""
        member = member or ctx.author
        cfg = self._get_antinuke_config(ctx.guild.id)
        # simulate threshold exceeded
        punish = cfg.get("punish", "kick")
        await ctx.approve(f"Test: would punish {member.mention} with {punish} (dry-run)")

    # ==================== AUTOROLE COMMANDS ====================

    @commands.group(name="autorole", invoke_without_command=True)
    @commands.has_permissions(manage_roles=True)
    async def autorole(self, ctx):
        """Manage autoroles - roles given to new members."""
        await ctx.send_help(ctx.command)

    @autorole.command(name="add")
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def autorole_add(self, ctx, role: discord.Role = None):
        """Add a role to autoroles."""
        if not role:
            return await ctx.send_help(ctx.command)
        
        # Check role hierarchy
        if role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
            return await ctx.deny("You cannot manage a role higher or equal to your top role.")
        
        if role >= ctx.guild.me.top_role:
            return await ctx.deny(f"I cannot manage {role.mention}, it's higher than my top role.")
        
        # Check if already autorole
        autoroles = await self._get_autoroles(ctx.guild.id)
        if role.id in autoroles:
            return await ctx.warn(f"{role.mention} is already an autorole.")
        
        # Add autorole
        success = await self._add_autorole(ctx.guild.id, role.id)
        if success:
            await ctx.approve(f"Added {role.mention} to autoroles")
        else:
            await ctx.deny("Failed to add autorole")

    @autorole.command(name="remove")
    @commands.has_permissions(manage_roles=True)
    async def autorole_remove(self, ctx, role: discord.Role = None):
        """Remove a role from autoroles."""
        if not role:
            return await ctx.send_help(ctx.command)
        
        # Check if autorole exists
        autoroles = await self._get_autoroles(ctx.guild.id)
        if role.id not in autoroles:
            return await ctx.warn(f"{role.mention} is not an autorole.")
        
        # Remove autorole
        success = await self._remove_autorole(ctx.guild.id, role.id)
        if success:
            await ctx.approve(f"Removed {role.mention} from autoroles")
        else:
            await ctx.deny("Failed to remove autorole")

    @autorole.command(name="list")
    async def autorole_list(self, ctx):
        """List all autoroles for this guild."""
        autoroles = await self._get_autoroles(ctx.guild.id)
        
        if not autoroles:
            return await ctx.warn("No autoroles configured")
        
        roles = []
        for role_id in autoroles:
            role = ctx.guild.get_role(role_id)
            if role:
                roles.append(role.mention)
            else:
                roles.append(f"(Unknown role {role_id})")
        
        embed = discord.Embed(
            color=Config.COLORS.SUCCESS,
            title="Autoroles"
        )
        embed.set_author(name=ctx.guild.name, icon_url=ctx.guild.icon.url if ctx.guild.icon else None)
        embed.description = "\n".join(roles)
        await ctx.send(embed=embed)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """Automatically assign autoroles to new members."""
        if member.bot:
            return
        

        await self._setup_autorole_table()
        

        autoroles = await self._get_autoroles(member.guild.id)
        
        if not autoroles:
            return
        

        roles_to_add = []
        for role_id in autoroles:
            role = member.guild.get_role(role_id)
            if role and role < member.guild.me.top_role:
                roles_to_add.append(role)
        
        if roles_to_add:
            try:
                await member.add_roles(*roles_to_add, reason="Autorole assignment")
            except Exception as e:
                print(f"Error assigning autoroles to {member}: {e}")

    @commands.group(name="customize", invoke_without_command=True)
    @commands.has_permissions(administrator=True)
    async def customize(self, ctx):
        """Customize the bot in your server"""
        return await ctx.send_help(ctx.command)
    
    @customize.command(name="banner", extras={'example': 'customize banner image url'})
    @commands.has_permissions(administrator=True)
    async def customize_banner(self, ctx, image_url: str = None):
        """Change the bot's banner for the server"""
        if not image_url:
            embed = discord.Embed(
                description=f"{Config.EMOJIS.ERROR} You're missing a **url**",
                color=Config.COLORS.ERROR
            )
            return await ctx.send(embed=embed)
        
        loading_embed = discord.Embed(
            description=f"{Config.EMOJIS.LOADING} Getting the **banner**...",
            color=Config.COLORS.LOADING
        )
        msg = await ctx.send(embed=loading_embed)
        
        data_uri = await self.download_to_data_uri(image_url)
        if not data_uri:
            error_embed = discord.Embed(
                description=f"{Config.EMOJIS.ERROR} Could not **download** the banner.",
                color=Config.COLORS.ERROR
            )
            return await msg.edit(embed=error_embed)
        
        from aiohttp import ClientSession
        payload = {"banner": data_uri}
        url = f"https://discord.com/api/v10/guilds/{ctx.guild.id}/members/@me"
        headers = {
            "Authorization": f"Bot {self.bot.http.token}",
            "Content-Type": "application/json",
            "X-Audit-Log-Reason": f"Updating bot server banner - by {ctx.author}"
        }
        
        async with ClientSession() as session:
            async with session.patch(url, headers=headers, json=payload) as resp:
                if resp.status == 200:
                    success_embed = discord.Embed(
                        description=f"{Config.EMOJIS.SUCCESS} Successfully updated the **banner**.",
                        color=Config.COLORS.SUCCESS
                    )
                    await msg.edit(embed=success_embed)
                else:
                    error_embed = discord.Embed(
                        description=f"{Config.EMOJIS.ERROR} Failed to update the **banner**.",
                        color=Config.COLORS.ERROR
                    )
                    await msg.edit(embed=error_embed)
    
    @customize.command(name="pfp", aliases=['avatar'], extras={'example': 'customize pfp image url'})
    @commands.has_permissions(administrator=True)
    async def customize_pfp(self, ctx, image_url: str = None):
        """Change the bot's avatar for the server"""
        if not image_url:
            embed = discord.Embed(
                description=f"{Config.EMOJIS.ERROR} You're missing a **url**",
                color=Config.COLORS.ERROR
            )
            return await ctx.send(embed=embed)
        
        loading_embed = discord.Embed(
            description=f"{Config.EMOJIS.LOADING} Getting the **avatar**...",
            color=Config.COLORS.LOADING
        )
        msg = await ctx.send(embed=loading_embed)
        
        data_uri = await self.download_to_data_uri(image_url)
        if not data_uri:
            error_embed = discord.Embed(
                description=f"{Config.EMOJIS.ERROR} Could not **download** the avatar.",
                color=Config.COLORS.ERROR
            )
            return await msg.edit(embed=error_embed)
        
        from aiohttp import ClientSession
        payload = {"avatar": data_uri}
        url = f"https://discord.com/api/v10/guilds/{ctx.guild.id}/members/@me"
        headers = {
            "Authorization": f"Bot {self.bot.http.token}",
            "Content-Type": "application/json",
            "X-Audit-Log-Reason": f"Updating bot server avatar - by {ctx.author}"
        }
        
        async with ClientSession() as session:
            async with session.patch(url, headers=headers, json=payload) as resp:
                if resp.status == 200:
                    success_embed = discord.Embed(
                        description=f"{Config.EMOJIS.SUCCESS} Successfully updated the **avatar**.",
                        color=Config.COLORS.SUCCESS
                    )
                    await msg.edit(embed=success_embed)
                else:
                    error_embed = discord.Embed(
                        description=f"{Config.EMOJIS.ERROR} Failed to update the **avatar**.",
                        color=Config.COLORS.ERROR
                    )
                    await msg.edit(embed=error_embed)
    
    @customize.command(name="bio", extras={'example': 'customize bio Hello World!'})
    @commands.has_permissions(administrator=True)
    async def customize_bio(self, ctx, *, text: str = None):
        """Change the bot's bio for the server"""
        if not text:
            embed = discord.Embed(
                description=f"{Config.EMOJIS.ERROR} You're missing a **bio**",
                color=Config.COLORS.ERROR
            )
            return await ctx.send(embed=embed)
        
        loading_embed = discord.Embed(
            description=f"{Config.EMOJIS.LOADING} Updating the **bio**...",
            color=Config.COLORS.LOADING
        )
        msg = await ctx.send(embed=loading_embed)
        
        from aiohttp import ClientSession
        payload = {"bio": text}
        url = f"https://discord.com/api/v10/guilds/{ctx.guild.id}/members/@me"
        headers = {
            "Authorization": f"Bot {self.bot.http.token}",
            "Content-Type": "application/json",
            "X-Audit-Log-Reason": f"Updating bot server bio - by {ctx.author}"
        }
        
        async with ClientSession() as session:
            async with session.patch(url, headers=headers, json=payload) as resp:
                if resp.status == 200:
                    success_embed = discord.Embed(
                        description=f"{Config.EMOJIS.SUCCESS} Successfully updated the **bio**.",
                        color=Config.COLORS.SUCCESS
                    )
                    await msg.edit(embed=success_embed)
                else:
                    error_embed = discord.Embed(
                        description=f"{Config.EMOJIS.ERROR} Failed to update the **bio**.",
                        color=Config.COLORS.ERROR
                    )
                    await msg.edit(embed=error_embed)

async def setup(bot):
    cog = GuildConfig(bot)
    bot.loop.create_task(cog._setup_autorole_table())
    await bot.add_cog(cog)
