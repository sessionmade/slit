import discord
from discord.ext import commands
from discord import ui
from src.config import Config
from typing import Optional


class VMEmojis:
    LOCK = "<:lock:1452719565309214944>"
    UNLOCK = "<:unlock:1452719577393008691>"
    GHOST = "<:ghost:1452719561257259061>"
    REVEAL = "<:reveal:1452719572565233664>"
    CLAIM = "<:claim:1452719493959647333>"
    INCREASE = "<:increase:1452719563304079390>"
    DECREASE = "<:decrease:1452719514104893522>"
    DISCONNECT = "<:disconnect:1452719558669500547>"


class RenameModal(ui.Modal, title="Rename Voice Channel"):
    name = ui.TextInput(label="Channel Name", placeholder="Enter new channel name...", max_length=100)

    def __init__(self, cog, channel: discord.VoiceChannel):
        super().__init__()
        self.cog = cog
        self.channel = channel

    async def on_submit(self, interaction: discord.Interaction):
        await self.channel.edit(name=self.name.value)
        await interaction.response.send_message(
            embed=discord.Embed(description=f"{Config.EMOJIS.SUCCESS} {interaction.user.mention}: Renamed your voice channel to **{self.name.value}**", color=Config.COLORS.SUCCESS),
            ephemeral=True
        )


class VoiceMasterView(ui.View):
    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog

    async def get_user_vc(self, interaction: discord.Interaction):
        if not interaction.user.voice or not interaction.user.voice.channel:
            return None, "You must be in a voice channel"
        channel = interaction.user.voice.channel
        async with self.cog.bot.db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT owner_id FROM voicemaster_channels WHERE channel_id = %s", (channel.id,))
                result = await cur.fetchone()
        if not result:
            return None, "This is not a VoiceMaster channel"
        return channel, result[0]

    async def check_owner(self, interaction: discord.Interaction):
        channel, result = await self.get_user_vc(interaction)
        if not channel:
            await interaction.response.send_message(embed=discord.Embed(description=f"{Config.EMOJIS.ERROR} {interaction.user.mention}: {result}", color=Config.COLORS.ERROR), ephemeral=True)
            return None, None
        if result != interaction.user.id:
            await interaction.response.send_message(embed=discord.Embed(description=f"{Config.EMOJIS.ERROR} {interaction.user.mention}: You don't own this channel", color=Config.COLORS.ERROR), ephemeral=True)
            return None, None
        return channel, result


    @ui.button(emoji="<:lock:1452719565309214944>", style=discord.ButtonStyle.secondary, custom_id="vm_lock", row=0)
    async def lock_btn(self, interaction: discord.Interaction, button: ui.Button):
        channel, _ = await self.check_owner(interaction)
        if not channel:
            return
        await channel.set_permissions(interaction.guild.default_role, connect=False)
        await interaction.response.send_message(embed=discord.Embed(description=f"{Config.EMOJIS.SUCCESS} {interaction.user.mention}: Locked your voice channel", color=Config.COLORS.SUCCESS), ephemeral=True)

    @ui.button(emoji="<:unlock:1452719577393008691>", style=discord.ButtonStyle.secondary, custom_id="vm_unlock", row=0)
    async def unlock_btn(self, interaction: discord.Interaction, button: ui.Button):
        channel, _ = await self.check_owner(interaction)
        if not channel:
            return
        await channel.set_permissions(interaction.guild.default_role, connect=True)
        await interaction.response.send_message(embed=discord.Embed(description=f"{Config.EMOJIS.SUCCESS} {interaction.user.mention}: Unlocked your voice channel", color=Config.COLORS.SUCCESS), ephemeral=True)

    @ui.button(emoji="<:ghost:1452719561257259061>", style=discord.ButtonStyle.secondary, custom_id="vm_ghost", row=0)
    async def ghost_btn(self, interaction: discord.Interaction, button: ui.Button):
        channel, _ = await self.check_owner(interaction)
        if not channel:
            return
        await channel.set_permissions(interaction.guild.default_role, view_channel=False)
        await interaction.response.send_message(embed=discord.Embed(description=f"{Config.EMOJIS.SUCCESS} {interaction.user.mention}: Hidden your voice channel", color=Config.COLORS.SUCCESS), ephemeral=True)

    @ui.button(emoji="<:reveal:1452719572565233664>", style=discord.ButtonStyle.secondary, custom_id="vm_reveal", row=0)
    async def reveal_btn(self, interaction: discord.Interaction, button: ui.Button):
        channel, _ = await self.check_owner(interaction)
        if not channel:
            return
        await channel.set_permissions(interaction.guild.default_role, view_channel=True)
        await interaction.response.send_message(embed=discord.Embed(description=f"{Config.EMOJIS.SUCCESS} {interaction.user.mention}: Revealed your voice channel", color=Config.COLORS.SUCCESS), ephemeral=True)

    @ui.button(emoji="<:claim:1452719493959647333>", style=discord.ButtonStyle.secondary, custom_id="vm_claim", row=1)
    async def claim_btn(self, interaction: discord.Interaction, button: ui.Button):
        if not interaction.user.voice or not interaction.user.voice.channel:
            return await interaction.response.send_message(embed=discord.Embed(description=f"{Config.EMOJIS.ERROR} {interaction.user.mention}: You must be in a voice channel", color=Config.COLORS.ERROR), ephemeral=True)
        channel = interaction.user.voice.channel
        async with self.cog.bot.db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT owner_id FROM voicemaster_channels WHERE channel_id = %s", (channel.id,))
                result = await cur.fetchone()
        if not result:
            return await interaction.response.send_message(embed=discord.Embed(description=f"{Config.EMOJIS.ERROR} {interaction.user.mention}: This is not a VoiceMaster channel", color=Config.COLORS.ERROR), ephemeral=True)
        owner = interaction.guild.get_member(result[0])
        if owner and owner in channel.members:
            return await interaction.response.send_message(embed=discord.Embed(description=f"{Config.EMOJIS.ERROR} {interaction.user.mention}: The owner is still in the channel", color=Config.COLORS.ERROR), ephemeral=True)
        async with self.cog.bot.db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("UPDATE voicemaster_channels SET owner_id = %s WHERE channel_id = %s", (interaction.user.id, channel.id))
        await channel.edit(name=f"{interaction.user.display_name}'s channel")
        await interaction.response.send_message(embed=discord.Embed(description=f"{Config.EMOJIS.SUCCESS} {interaction.user.mention}: You now own this voice channel", color=Config.COLORS.SUCCESS), ephemeral=True)


    @ui.button(emoji="<:increase:1452719563304079390>", style=discord.ButtonStyle.secondary, custom_id="vm_increase", row=1)
    async def increase_btn(self, interaction: discord.Interaction, button: ui.Button):
        channel, _ = await self.check_owner(interaction)
        if not channel:
            return
        limit = channel.user_limit + 1 if channel.user_limit < 99 else 99
        await channel.edit(user_limit=limit)
        await interaction.response.send_message(embed=discord.Embed(description=f"{Config.EMOJIS.SUCCESS} {interaction.user.mention}: User limit set to **{limit}**", color=Config.COLORS.SUCCESS), ephemeral=True)

    @ui.button(emoji="<:decrease:1452719514104893522>", style=discord.ButtonStyle.secondary, custom_id="vm_decrease", row=1)
    async def decrease_btn(self, interaction: discord.Interaction, button: ui.Button):
        channel, _ = await self.check_owner(interaction)
        if not channel:
            return
        limit = channel.user_limit - 1 if channel.user_limit > 0 else 0
        await channel.edit(user_limit=limit)
        await interaction.response.send_message(embed=discord.Embed(description=f"{Config.EMOJIS.SUCCESS} {interaction.user.mention}: User limit set to **{limit}**", color=Config.COLORS.SUCCESS), ephemeral=True)

    @ui.button(emoji="<:disconnect:1452719558669500547>", style=discord.ButtonStyle.secondary, custom_id="vm_disconnect", row=1)
    async def disconnect_btn(self, interaction: discord.Interaction, button: ui.Button):
        channel, _ = await self.check_owner(interaction)
        if not channel:
            return
        await channel.delete()
        async with self.cog.bot.db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("DELETE FROM voicemaster_channels WHERE channel_id = %s", (channel.id,))
        await interaction.response.send_message(embed=discord.Embed(description=f"{Config.EMOJIS.SUCCESS} {interaction.user.mention}: Deleted your voice channel", color=Config.COLORS.SUCCESS), ephemeral=True)


class VoiceMaster(commands.Cog):
    """VoiceMaster system for temporary voice channels"""
    
    def __init__(self, bot):
        self.bot = bot
        self.bot.add_view(VoiceMasterView(self))

    async def cog_load(self):
        async with self.bot.db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("""
                    CREATE TABLE IF NOT EXISTS voicemaster_settings (
                        guild_id BIGINT PRIMARY KEY,
                        category_id BIGINT,
                        jtc_channel_id BIGINT,
                        interface_channel_id BIGINT
                    )
                """)
                await cur.execute("""
                    CREATE TABLE IF NOT EXISTS voicemaster_channels (
                        channel_id BIGINT PRIMARY KEY,
                        guild_id BIGINT,
                        owner_id BIGINT
                    )
                """)


    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        # User joined a channel
        if after.channel:
            async with self.bot.db_pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute("SELECT category_id, jtc_channel_id FROM voicemaster_settings WHERE guild_id = %s", (member.guild.id,))
                    settings = await cur.fetchone()
            
            if settings and after.channel.id == settings[1]:
                category = member.guild.get_channel(settings[0])
                if category:
                    vc = await member.guild.create_voice_channel(
                        name=f"{member.display_name}'s channel",
                        category=category,
                        reason="VoiceMaster: User joined JTC"
                    )
                    await member.move_to(vc)
                    async with self.bot.db_pool.acquire() as conn:
                        async with conn.cursor() as cur:
                            await cur.execute("INSERT INTO voicemaster_channels (channel_id, guild_id, owner_id) VALUES (%s, %s, %s)", (vc.id, member.guild.id, member.id))

        # User left a channel
        if before.channel:
            async with self.bot.db_pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute("SELECT channel_id FROM voicemaster_channels WHERE channel_id = %s", (before.channel.id,))
                    result = await cur.fetchone()
            
            if result and len(before.channel.members) == 0:
                await before.channel.delete(reason="VoiceMaster: Channel empty")
                async with self.bot.db_pool.acquire() as conn:
                    async with conn.cursor() as cur:
                        await cur.execute("DELETE FROM voicemaster_channels WHERE channel_id = %s", (before.channel.id,))

    @commands.group(name="voicemaster", aliases=["vm"], invoke_without_command=True)
    async def voicemaster(self, ctx):
        """VoiceMaster commands"""
        await ctx.send_help(ctx.command)

    @voicemaster.command(name="setup")
    @commands.has_permissions(administrator=True)
    async def vm_setup(self, ctx):
        """Setup the VoiceMaster system"""
        async with self.bot.db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT * FROM voicemaster_settings WHERE guild_id = %s", (ctx.guild.id,))
                if await cur.fetchone():
                    return await ctx.deny("VoiceMaster is already setup in this server")

        category = await ctx.guild.create_category("slit vm")
        jtc = await ctx.guild.create_voice_channel("Join To Create", category=category)
        interface = await ctx.guild.create_text_channel("interface", category=category)
        
        # Lock the interface channel so only the bot can send messages
        await interface.set_permissions(ctx.guild.default_role, send_messages=False)
        await interface.set_permissions(ctx.guild.me, send_messages=True)

        async with self.bot.db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("INSERT INTO voicemaster_settings (guild_id, category_id, jtc_channel_id, interface_channel_id) VALUES (%s, %s, %s, %s)", (ctx.guild.id, category.id, jtc.id, interface.id))

        embed = discord.Embed(
            title="Voicemaster Menu",
            description="Welcome to the Voicemaster interface! Here you can manage your voice channels with ease. Below are the available options\n\n"
                        f"> {VMEmojis.LOCK} **Lock** - Lock your voice channel\n"
                        f"> {VMEmojis.UNLOCK} **Unlock** - Unlock your voice channel\n"
                        f"> {VMEmojis.GHOST} **Hide** - Hide your voice channel\n"
                        f"> {VMEmojis.REVEAL} **Reveal** - Reveal your hidden voice channel\n"
                        f"> {VMEmojis.CLAIM} **Claim** - Claim an unclaimed voice channel\n"
                        f"> {VMEmojis.INCREASE} **Increase** - Increase the user limit of your voice channel\n"
                        f"> {VMEmojis.DECREASE} **Decrease** - Decrease the user limit of your voice channel\n"
                        f"> {VMEmojis.DISCONNECT} **Delete** - Delete your voice channel",
            color=Config.COLORS.DEFAULT
        )
        await interface.send(embed=embed, view=VoiceMasterView(self))
        await ctx.approve("VoiceMaster has been setup successfully")


    @voicemaster.command(name="lock")
    async def vm_lock(self, ctx):
        """Lock your voice channel"""
        if not ctx.author.voice or not ctx.author.voice.channel:
            return await ctx.deny("You must be in a voice channel")
        channel = ctx.author.voice.channel
        async with self.bot.db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT owner_id FROM voicemaster_channels WHERE channel_id = %s", (channel.id,))
                result = await cur.fetchone()
        if not result:
            return await ctx.deny("This is not a VoiceMaster channel")
        if result[0] != ctx.author.id:
            return await ctx.deny("You don't own this channel")
        await channel.set_permissions(ctx.guild.default_role, connect=False)
        await ctx.approve("Locked your voice channel")

    @voicemaster.command(name="unlock")
    async def vm_unlock(self, ctx):
        """Unlock your voice channel"""
        if not ctx.author.voice or not ctx.author.voice.channel:
            return await ctx.deny("You must be in a voice channel")
        channel = ctx.author.voice.channel
        async with self.bot.db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT owner_id FROM voicemaster_channels WHERE channel_id = %s", (channel.id,))
                result = await cur.fetchone()
        if not result:
            return await ctx.deny("This is not a VoiceMaster channel")
        if result[0] != ctx.author.id:
            return await ctx.deny("You don't own this channel")
        await channel.set_permissions(ctx.guild.default_role, connect=True)
        await ctx.approve("Unlocked your voice channel")

    @voicemaster.command(name="hide", aliases=["ghost"])
    async def vm_hide(self, ctx):
        """Hide your voice channel"""
        if not ctx.author.voice or not ctx.author.voice.channel:
            return await ctx.deny("You must be in a voice channel")
        channel = ctx.author.voice.channel
        async with self.bot.db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT owner_id FROM voicemaster_channels WHERE channel_id = %s", (channel.id,))
                result = await cur.fetchone()
        if not result:
            return await ctx.deny("This is not a VoiceMaster channel")
        if result[0] != ctx.author.id:
            return await ctx.deny("You don't own this channel")
        await channel.set_permissions(ctx.guild.default_role, view_channel=False)
        await ctx.approve("Hidden your voice channel")

    @voicemaster.command(name="reveal", aliases=["unhide"])
    async def vm_reveal(self, ctx):
        """Reveal your voice channel"""
        if not ctx.author.voice or not ctx.author.voice.channel:
            return await ctx.deny("You must be in a voice channel")
        channel = ctx.author.voice.channel
        async with self.bot.db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT owner_id FROM voicemaster_channels WHERE channel_id = %s", (channel.id,))
                result = await cur.fetchone()
        if not result:
            return await ctx.deny("This is not a VoiceMaster channel")
        if result[0] != ctx.author.id:
            return await ctx.deny("You don't own this channel")
        await channel.set_permissions(ctx.guild.default_role, view_channel=True)
        await ctx.approve("Revealed your voice channel")

    @voicemaster.command(name="claim")
    async def vm_claim(self, ctx):
        """Claim an unclaimed voice channel"""
        if not ctx.author.voice or not ctx.author.voice.channel:
            return await ctx.deny("You must be in a voice channel")
        channel = ctx.author.voice.channel
        async with self.bot.db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT owner_id FROM voicemaster_channels WHERE channel_id = %s", (channel.id,))
                result = await cur.fetchone()
        if not result:
            return await ctx.deny("This is not a VoiceMaster channel")
        owner = ctx.guild.get_member(result[0])
        if owner and owner in channel.members:
            return await ctx.deny("The owner is still in the channel")
        async with self.bot.db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("UPDATE voicemaster_channels SET owner_id = %s WHERE channel_id = %s", (ctx.author.id, channel.id))
        await channel.edit(name=f"{ctx.author.display_name}'s channel")
        await ctx.approve("You now own this voice channel")


    @voicemaster.command(name="increase")
    async def vm_increase(self, ctx):
        """Increase the user limit"""
        if not ctx.author.voice or not ctx.author.voice.channel:
            return await ctx.deny("You must be in a voice channel")
        channel = ctx.author.voice.channel
        async with self.bot.db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT owner_id FROM voicemaster_channels WHERE channel_id = %s", (channel.id,))
                result = await cur.fetchone()
        if not result:
            return await ctx.deny("This is not a VoiceMaster channel")
        if result[0] != ctx.author.id:
            return await ctx.deny("You don't own this channel")
        limit = channel.user_limit + 1 if channel.user_limit < 99 else 99
        await channel.edit(user_limit=limit)
        await ctx.approve(f"User limit set to **{limit}**")

    @voicemaster.command(name="decrease")
    async def vm_decrease(self, ctx):
        """Decrease the user limit"""
        if not ctx.author.voice or not ctx.author.voice.channel:
            return await ctx.deny("You must be in a voice channel")
        channel = ctx.author.voice.channel
        async with self.bot.db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT owner_id FROM voicemaster_channels WHERE channel_id = %s", (channel.id,))
                result = await cur.fetchone()
        if not result:
            return await ctx.deny("This is not a VoiceMaster channel")
        if result[0] != ctx.author.id:
            return await ctx.deny("You don't own this channel")
        limit = channel.user_limit - 1 if channel.user_limit > 0 else 0
        await channel.edit(user_limit=limit)
        await ctx.approve(f"User limit set to **{limit}**")

    @voicemaster.command(name="rename")
    async def vm_rename(self, ctx, *, name: str):
        """Rename your voice channel"""
        if not ctx.author.voice or not ctx.author.voice.channel:
            return await ctx.deny("You must be in a voice channel")
        channel = ctx.author.voice.channel
        async with self.bot.db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT owner_id FROM voicemaster_channels WHERE channel_id = %s", (channel.id,))
                result = await cur.fetchone()
        if not result:
            return await ctx.deny("This is not a VoiceMaster channel")
        if result[0] != ctx.author.id:
            return await ctx.deny("You don't own this channel")
        await channel.edit(name=name)
        await ctx.approve(f"Renamed your voice channel to **{name}**")

    @voicemaster.command(name="delete", aliases=["disconnect"])
    async def vm_delete(self, ctx):
        """Delete your voice channel"""
        if not ctx.author.voice or not ctx.author.voice.channel:
            return await ctx.deny("You must be in a voice channel")
        channel = ctx.author.voice.channel
        async with self.bot.db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT owner_id FROM voicemaster_channels WHERE channel_id = %s", (channel.id,))
                result = await cur.fetchone()
        if not result:
            return await ctx.deny("This is not a VoiceMaster channel")
        if result[0] != ctx.author.id:
            return await ctx.deny("You don't own this channel")
        await channel.delete()
        async with self.bot.db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("DELETE FROM voicemaster_channels WHERE channel_id = %s", (channel.id,))

    @voicemaster.command(name="reset")
    @commands.has_permissions(administrator=True)
    async def vm_reset(self, ctx):
        """Reset the VoiceMaster system"""
        async with self.bot.db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT category_id, jtc_channel_id, interface_channel_id FROM voicemaster_settings WHERE guild_id = %s", (ctx.guild.id,))
                settings = await cur.fetchone()
        if not settings:
            return await ctx.deny("VoiceMaster is not setup in this server")
        
        for channel_id in settings:
            channel = ctx.guild.get_channel(channel_id)
            if channel:
                try:
                    await channel.delete()
                except:
                    pass
        
        async with self.bot.db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("DELETE FROM voicemaster_settings WHERE guild_id = %s", (ctx.guild.id,))
                await cur.execute("DELETE FROM voicemaster_channels WHERE guild_id = %s", (ctx.guild.id,))
        
        await ctx.approve("VoiceMaster has been reset")


async def setup(bot):
    await bot.add_cog(VoiceMaster(bot))
