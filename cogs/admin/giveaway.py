import discord
import asyncio
import random
from discord.ext import commands, tasks
from src.config import Config
from datetime import datetime, timezone, timedelta
from typing import Optional
import re


def parse_time(time_str: str) -> Optional[int]:
    """Parse time string like 1d, 2h, 30m, 1w into seconds"""
    time_regex = re.compile(r"(\d+)([smhdw])")
    matches = time_regex.findall(time_str.lower())
    
    if not matches:
        return None
    
    total_seconds = 0
    time_units = {
        's': 1,
        'm': 60,
        'h': 3600,
        'd': 86400,
        'w': 604800
    }
    
    for amount, unit in matches:
        total_seconds += int(amount) * time_units[unit]
    
    return total_seconds if total_seconds > 0 else None


class GiveawayView(discord.ui.View):
    def __init__(self, giveaway_id: int, cog):
        super().__init__(timeout=None)
        self.giveaway_id = giveaway_id
        self.cog = cog
    
    @discord.ui.button(emoji="🎉", style=discord.ButtonStyle.primary, custom_id="giveaway_enter")
    async def enter_giveaway(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.handle_entry(interaction, self.giveaway_id)
    
    @discord.ui.button(label="View Participants", style=discord.ButtonStyle.secondary, custom_id="giveaway_view")
    async def view_participants(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.view_participants(interaction, self.giveaway_id)


class Giveaway(commands.Cog):
    """Giveaway management system"""

    def __init__(self, bot):
        self.bot = bot
        self.cache = {}  # giveaway_id -> giveaway data
        self.blacklist_cache = {}  # guild_id -> set of role_ids
        self.max_entries_cache = {}  # guild_id -> {role_id: max_entries}
        bot.loop.create_task(self.setup_tables())
    
    async def setup_tables(self):
        """Create the giveaway tables if they don't exist"""
        await self.bot.wait_until_ready()
        if not self.bot.db_pool:
            return

        async with self.bot.db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                # Giveaways table
                await cur.execute("""
                    CREATE TABLE IF NOT EXISTS giveaways (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        guild_id BIGINT NOT NULL,
                        channel_id BIGINT NOT NULL,
                        message_id BIGINT NOT NULL,
                        host_id BIGINT NOT NULL,
                        prize VARCHAR(255) NOT NULL,
                        winners INT DEFAULT 1,
                        ends_at DATETIME NOT NULL,
                        ended BOOLEAN DEFAULT FALSE,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # Giveaway entries table
                await cur.execute("""
                    CREATE TABLE IF NOT EXISTS giveaway_entries (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        giveaway_id INT NOT NULL,
                        user_id BIGINT NOT NULL,
                        UNIQUE KEY unique_entry (giveaway_id, user_id),
                        FOREIGN KEY (giveaway_id) REFERENCES giveaways(id) ON DELETE CASCADE
                    )
                """)
                
                # Giveaway blacklisted roles
                await cur.execute("""
                    CREATE TABLE IF NOT EXISTS giveaway_blacklist (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        guild_id BIGINT NOT NULL,
                        role_id BIGINT NOT NULL,
                        UNIQUE KEY unique_blacklist (guild_id, role_id)
                    )
                """)
                
                # Max entries per role
                await cur.execute("""
                    CREATE TABLE IF NOT EXISTS giveaway_max_entries (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        guild_id BIGINT NOT NULL,
                        role_id BIGINT NOT NULL,
                        max_entries INT NOT NULL,
                        UNIQUE KEY unique_max (guild_id, role_id)
                    )
                """)

        await self.load_cache()
        self.check_giveaways.start()
    
    async def load_cache(self):
        """Load active giveaways and settings into cache"""
        if not self.bot.db_pool:
            return

        async with self.bot.db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                # Load active giveaways
                await cur.execute("""
                    SELECT id, guild_id, channel_id, message_id, host_id, prize, winners, ends_at
                    FROM giveaways WHERE ended = FALSE
                """)
                rows = await cur.fetchall()
                for row in rows:
                    self.cache[row[0]] = {
                        'guild_id': row[1],
                        'channel_id': row[2],
                        'message_id': row[3],
                        'host_id': row[4],
                        'prize': row[5],
                        'winners': row[6],
                        'ends_at': row[7]
                    }
                
                # Load blacklisted roles
                await cur.execute("SELECT guild_id, role_id FROM giveaway_blacklist")
                rows = await cur.fetchall()
                for guild_id, role_id in rows:
                    if guild_id not in self.blacklist_cache:
                        self.blacklist_cache[guild_id] = set()
                    self.blacklist_cache[guild_id].add(role_id)
                
                # Load max entries
                await cur.execute("SELECT guild_id, role_id, max_entries FROM giveaway_max_entries")
                rows = await cur.fetchall()
                for guild_id, role_id, max_entries in rows:
                    if guild_id not in self.max_entries_cache:
                        self.max_entries_cache[guild_id] = {}
                    self.max_entries_cache[guild_id][role_id] = max_entries
    
    def cog_unload(self):
        self.check_giveaways.cancel()
    
    @tasks.loop(seconds=15)
    async def check_giveaways(self):
        """Check for ended giveaways"""
        now = datetime.now(timezone.utc)
        ended_ids = []
        
        for giveaway_id, data in list(self.cache.items()):
            ends_at = data['ends_at']
            if isinstance(ends_at, datetime):
                if ends_at.tzinfo is None:
                    ends_at = ends_at.replace(tzinfo=timezone.utc)
            
            if now >= ends_at:
                ended_ids.append(giveaway_id)
        
        for giveaway_id in ended_ids:
            await self.end_giveaway_internal(giveaway_id)
    
    @check_giveaways.before_loop
    async def before_check(self):
        await self.bot.wait_until_ready()
    
    async def handle_entry(self, interaction: discord.Interaction, giveaway_id: int):
        """Handle a user entering a giveaway"""
        if giveaway_id not in self.cache:
            return await interaction.response.send_message("This giveaway has ended!", ephemeral=True)
        
        guild_id = interaction.guild_id
        user = interaction.user
        
        # Check blacklist
        if guild_id in self.blacklist_cache:
            user_role_ids = {r.id for r in user.roles}
            if user_role_ids & self.blacklist_cache[guild_id]:
                return await interaction.response.send_message(
                    "You have a blacklisted role and cannot enter this giveaway!", 
                    ephemeral=True
                )
        
        # Check max entries for roles
        if guild_id in self.max_entries_cache:
            for role_id, max_entries in self.max_entries_cache[guild_id].items():
                role = interaction.guild.get_role(role_id)
                if role and role in user.roles:
                    # Count user's current entries
                    async with self.bot.db_pool.acquire() as conn:
                        async with conn.cursor() as cur:
                            await cur.execute("""
                                SELECT COUNT(*) FROM giveaway_entries ge
                                JOIN giveaways g ON ge.giveaway_id = g.id
                                WHERE ge.user_id = %s AND g.guild_id = %s AND g.ended = FALSE
                            """, (user.id, guild_id))
                            result = await cur.fetchone()
                            if result[0] >= max_entries:
                                return await interaction.response.send_message(
                                    f"You've reached the max entries ({max_entries}) for your role!",
                                    ephemeral=True
                                )
        
        # Try to add entry
        async with self.bot.db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                try:
                    await cur.execute(
                        "INSERT INTO giveaway_entries (giveaway_id, user_id) VALUES (%s, %s)",
                        (giveaway_id, user.id)
                    )
                    await interaction.response.send_message("You've entered the giveaway! 🎉", ephemeral=True)
                    await self.update_giveaway_message(giveaway_id)
                except Exception:
                    # Already entered, remove entry
                    await cur.execute(
                        "DELETE FROM giveaway_entries WHERE giveaway_id = %s AND user_id = %s",
                        (giveaway_id, user.id)
                    )
                    await interaction.response.send_message("You've left the giveaway.", ephemeral=True)
                    await self.update_giveaway_message(giveaway_id)
    
    async def view_participants(self, interaction: discord.Interaction, giveaway_id: int):
        """View giveaway participants"""
        async with self.bot.db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT user_id FROM giveaway_entries WHERE giveaway_id = %s",
                    (giveaway_id,)
                )
                rows = await cur.fetchall()
        
        if not rows:
            return await interaction.response.send_message("No participants yet!", ephemeral=True)
        
        participants = [f"<@{row[0]}>" for row in rows[:20]]
        extra = len(rows) - 20 if len(rows) > 20 else 0
        
        desc = "\n".join(participants)
        if extra > 0:
            desc += f"\n...and {extra} more"
        
        embed = discord.Embed(
            title="Giveaway Participants",
            description=desc,
            color=Config.COLORS.DEFAULT
        )
        embed.set_footer(text=f"Total: {len(rows)} entries")
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    async def update_giveaway_message(self, giveaway_id: int):
        """Update the giveaway embed with current entry count"""
        if giveaway_id not in self.cache:
            return
        
        data = self.cache[giveaway_id]
        
        try:
            channel = self.bot.get_channel(data['channel_id'])
            if not channel:
                return
            
            message = await channel.fetch_message(data['message_id'])
            
            async with self.bot.db_pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        "SELECT COUNT(*) FROM giveaway_entries WHERE giveaway_id = %s",
                        (giveaway_id,)
                    )
                    result = await cur.fetchone()
                    entry_count = result[0]
            
            ends_at = data['ends_at']
            if isinstance(ends_at, datetime) and ends_at.tzinfo is None:
                ends_at = ends_at.replace(tzinfo=timezone.utc)
            
            embed = discord.Embed(
                title=data['prize'],
                color=Config.COLORS.DEFAULT
            )
            embed.add_field(name="Winners", value=str(data['winners']), inline=True)
            embed.add_field(name="Entries", value=str(entry_count), inline=True)
            embed.add_field(
                name="Ends",
                value=f"<t:{int(ends_at.timestamp())}:R> (<t:{int(ends_at.timestamp())}:F>)",
                inline=False
            )
            
            host = self.bot.get_user(data['host_id'])
            embed.set_footer(text=f"hosted by {host.name if host else 'Unknown'}")
            
            await message.edit(embed=embed)
        except Exception:
            pass
    
    async def end_giveaway_internal(self, giveaway_id: int):
        """End a giveaway and pick winners"""
        if giveaway_id not in self.cache:
            return
        
        data = self.cache.pop(giveaway_id)
        
        async with self.bot.db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("UPDATE giveaways SET ended = TRUE WHERE id = %s", (giveaway_id,))
                await cur.execute(
                    "SELECT user_id FROM giveaway_entries WHERE giveaway_id = %s",
                    (giveaway_id,)
                )
                entries = await cur.fetchall()
        
        try:
            channel = self.bot.get_channel(data['channel_id'])
            if not channel:
                return
            
            message = await channel.fetch_message(data['message_id'])
            
            if not entries:
                embed = discord.Embed(
                    title=data['prize'],
                    description="No valid entries - no winners!",
                    color=Config.COLORS.ERROR
                )
                embed.set_footer(text="Giveaway ended")
                await message.edit(embed=embed, view=None)
                return
            
            user_ids = [e[0] for e in entries]
            winner_count = min(data['winners'], len(user_ids))
            winner_ids = random.sample(user_ids, winner_count)
            
            winners_mention = ", ".join([f"<@{uid}>" for uid in winner_ids])
            
            embed = discord.Embed(
                title=data['prize'],
                description=f"**Winners:** {winners_mention}",
                color=Config.COLORS.SUCCESS
            )
            embed.add_field(name="Entries", value=str(len(entries)), inline=True)
            embed.set_footer(text="Giveaway ended")
            
            await message.edit(embed=embed, view=None)
            await channel.send(f"🎉 Congratulations {winners_mention}! You won **{data['prize']}**!")
        except Exception:
            pass
    
    async def reroll_giveaway_internal(self, giveaway_id: int, winner_count: int = 1):
        """Reroll winners for an ended giveaway"""
        async with self.bot.db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT guild_id, channel_id, message_id, prize FROM giveaways WHERE id = %s AND ended = TRUE",
                    (giveaway_id,)
                )
                giveaway = await cur.fetchone()
                
                if not giveaway:
                    return None
                
                await cur.execute(
                    "SELECT user_id FROM giveaway_entries WHERE giveaway_id = %s",
                    (giveaway_id,)
                )
                entries = await cur.fetchall()
        
        if not entries:
            return []
        
        user_ids = [e[0] for e in entries]
        winner_count = min(winner_count, len(user_ids))
        return random.sample(user_ids, winner_count), giveaway[3]

    @commands.group(name="giveaway", aliases=["gw", "g"], invoke_without_command=True)
    @commands.cooldown(1, 4, commands.BucketType.user)
    async def giveaway(self, ctx):
        """Giveaway management commands"""
        await ctx.send_help(ctx.command)
    
    @giveaway.command(name="start", aliases=["create", "new"])
    @commands.has_permissions(manage_guild=True)
    async def giveaway_start(self, ctx, duration: str = None, winners: int = 1, *, prize: str = None):
        """Start a new giveaway
        
        Example: ;giveaway start 1d 1 Nitro Classic
        """
        if not duration or not prize:
            return await ctx.send_help(ctx.command)
        
        seconds = parse_time(duration)
        if not seconds:
            return await ctx.deny("Invalid duration! Use format like `1d`, `2h`, `30m`")
        
        if winners < 1 or winners > 20:
            return await ctx.deny("Winners must be between 1 and 20")
        
        ends_at = datetime.now(timezone.utc) + timedelta(seconds=seconds)
        
        # Create initial embed
        embed = discord.Embed(
            title=prize,
            color=Config.COLORS.DEFAULT
        )
        embed.add_field(name="Winners", value=str(winners), inline=True)
        embed.add_field(name="Entries", value="0", inline=True)
        embed.add_field(
            name="Ends",
            value=f"<t:{int(ends_at.timestamp())}:R> (<t:{int(ends_at.timestamp())}:F>)",
            inline=False
        )
        embed.set_footer(text=f"hosted by {ctx.author.name}")
        
        # Send starting message
        start_msg = await ctx.send("Starting giveaway...")
        
        # Create giveaway in database
        async with self.bot.db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("""
                    INSERT INTO giveaways (guild_id, channel_id, message_id, host_id, prize, winners, ends_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (ctx.guild.id, ctx.channel.id, start_msg.id, ctx.author.id, prize, winners, ends_at))
                giveaway_id = cur.lastrowid
        
        # Add to cache
        self.cache[giveaway_id] = {
            'guild_id': ctx.guild.id,
            'channel_id': ctx.channel.id,
            'message_id': start_msg.id,
            'host_id': ctx.author.id,
            'prize': prize,
            'winners': winners,
            'ends_at': ends_at
        }
        
        # Update message with view
        view = GiveawayView(giveaway_id, self)
        await start_msg.edit(content=None, embed=embed, view=view)
    
    @giveaway.command(name="end", aliases=["stop"])
    @commands.has_permissions(manage_guild=True)
    async def giveaway_end(self, ctx, message_id: int = None):
        """End a giveaway early
        
        Example: ;giveaway end 123456789
        """
        if not message_id:
            return await ctx.send_help(ctx.command)
        
        # Find giveaway by message_id
        giveaway_id = None
        for gid, data in self.cache.items():
            if data['message_id'] == message_id and data['guild_id'] == ctx.guild.id:
                giveaway_id = gid
                break
        
        if not giveaway_id:
            return await ctx.deny("Giveaway not found or already ended")
        
        await self.end_giveaway_internal(giveaway_id)
        await ctx.approve("Giveaway ended!")
    
    @giveaway.command(name="reroll")
    @commands.has_permissions(manage_guild=True)
    async def giveaway_reroll(self, ctx, message_id: int = None, winners: int = 1):
        """Reroll winners for an ended giveaway
        
        Example: ;giveaway reroll 123456789 1
        """
        if not message_id:
            return await ctx.send_help(ctx.command)
        
        # Find giveaway by message_id
        async with self.bot.db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT id FROM giveaways WHERE message_id = %s AND guild_id = %s AND ended = TRUE",
                    (message_id, ctx.guild.id)
                )
                result = await cur.fetchone()
        
        if not result:
            return await ctx.deny("Ended giveaway not found")
        
        giveaway_id = result[0]
        reroll_result = await self.reroll_giveaway_internal(giveaway_id, winners)
        
        if reroll_result is None:
            return await ctx.deny("Giveaway not found")
        
        winner_ids, prize = reroll_result
        if not winner_ids:
            return await ctx.deny("No entries to reroll from")
        
        winners_mention = ", ".join([f"<@{uid}>" for uid in winner_ids])
        await ctx.send(f"🎉 New winner(s): {winners_mention} for **{prize}**!")
    
    @giveaway.command(name="blacklist", aliases=["bl"])
    @commands.has_permissions(manage_guild=True)
    async def giveaway_blacklist(self, ctx, action: str = None, role: discord.Role = None):
        """Blacklist a role from entering giveaways
        
        Example: ;giveaway blacklist add @Muted
        Example: ;giveaway blacklist remove @Muted
        Example: ;giveaway blacklist list
        """
        if not action:
            return await ctx.send_help(ctx.command)
        
        action = action.lower()
        
        if action == "list":
            if ctx.guild.id not in self.blacklist_cache or not self.blacklist_cache[ctx.guild.id]:
                return await ctx.warn("No blacklisted roles")
            
            roles = []
            for role_id in self.blacklist_cache[ctx.guild.id]:
                r = ctx.guild.get_role(role_id)
                if r:
                    roles.append(r.mention)
            
            embed = discord.Embed(
                title="Blacklisted Roles",
                description="\n".join(roles) if roles else "None",
                color=Config.COLORS.DEFAULT
            )
            return await ctx.send(embed=embed)
        
        if not role:
            return await ctx.deny("Please specify a role")
        
        if action in ["add", "+"]:
            if ctx.guild.id in self.blacklist_cache and role.id in self.blacklist_cache[ctx.guild.id]:
                return await ctx.deny(f"{role.mention} is already blacklisted")
            
            async with self.bot.db_pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        "INSERT INTO giveaway_blacklist (guild_id, role_id) VALUES (%s, %s)",
                        (ctx.guild.id, role.id)
                    )
            
            if ctx.guild.id not in self.blacklist_cache:
                self.blacklist_cache[ctx.guild.id] = set()
            self.blacklist_cache[ctx.guild.id].add(role.id)
            
            await ctx.approve(f"Blacklisted {role.mention} from giveaways")
        
        elif action in ["remove", "-", "del", "delete"]:
            if ctx.guild.id not in self.blacklist_cache or role.id not in self.blacklist_cache[ctx.guild.id]:
                return await ctx.deny(f"{role.mention} is not blacklisted")
            
            async with self.bot.db_pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        "DELETE FROM giveaway_blacklist WHERE guild_id = %s AND role_id = %s",
                        (ctx.guild.id, role.id)
                    )
            
            self.blacklist_cache[ctx.guild.id].discard(role.id)
            await ctx.approve(f"Removed {role.mention} from blacklist")
        else:
            return await ctx.deny("Invalid action. Use `add`, `remove`, or `list`")
    
    @giveaway.command(name="setmax", aliases=["maxentries", "limit"])
    @commands.has_permissions(manage_guild=True)
    async def giveaway_setmax(self, ctx, role: discord.Role = None, max_entries: int = None):
        """Set max entries for users with a specific role
        
        Example: ;giveaway setmax @Member 5
        Example: ;giveaway setmax @Member 0 (removes limit)
        """
        if not role:
            # Show current limits
            if ctx.guild.id not in self.max_entries_cache or not self.max_entries_cache[ctx.guild.id]:
                return await ctx.warn("No entry limits configured")
            
            lines = []
            for role_id, max_e in self.max_entries_cache[ctx.guild.id].items():
                r = ctx.guild.get_role(role_id)
                if r:
                    lines.append(f"{r.mention}: **{max_e}** entries")
            
            embed = discord.Embed(
                title="Max Entry Limits",
                description="\n".join(lines) if lines else "None",
                color=Config.COLORS.DEFAULT
            )
            return await ctx.send(embed=embed)
        
        if max_entries is None:
            return await ctx.send_help(ctx.command)
        
        if max_entries < 0:
            return await ctx.deny("Max entries must be 0 or higher")
        
        async with self.bot.db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                if max_entries == 0:
                    # Remove limit
                    await cur.execute(
                        "DELETE FROM giveaway_max_entries WHERE guild_id = %s AND role_id = %s",
                        (ctx.guild.id, role.id)
                    )
                    if ctx.guild.id in self.max_entries_cache:
                        self.max_entries_cache[ctx.guild.id].pop(role.id, None)
                    await ctx.approve(f"Removed entry limit for {role.mention}")
                else:
                    # Set/update limit
                    await cur.execute("""
                        INSERT INTO giveaway_max_entries (guild_id, role_id, max_entries)
                        VALUES (%s, %s, %s)
                        ON DUPLICATE KEY UPDATE max_entries = %s
                    """, (ctx.guild.id, role.id, max_entries, max_entries))
                    
                    if ctx.guild.id not in self.max_entries_cache:
                        self.max_entries_cache[ctx.guild.id] = {}
                    self.max_entries_cache[ctx.guild.id][role.id] = max_entries
                    
                    await ctx.approve(f"Set max entries for {role.mention} to **{max_entries}**")


async def setup(bot):
    await bot.add_cog(Giveaway(bot))
