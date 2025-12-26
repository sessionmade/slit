import discord
from discord.ext import commands
from discord.ui import Button, View
import io
import aiohttp


class ConfirmStealSticker(View):
    def __init__(self, ctx, sticker):
        super().__init__()
        self.ctx = ctx
        self.sticker = sticker
        self.confirmed = False

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.green)
    async def confirm_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.defer()
        
        self.confirmed = True
        await interaction.response.defer()
        
        async with aiohttp.ClientSession() as session:
            async with session.get(self.sticker.url) as resp:
                sticker_data = await resp.read()
        
        # Determine file extension
        ext = ".gif" if self.sticker.format == discord.StickerFormatType.lottie else (
            ".gif" if "gif" in self.sticker.url else ".png"
        )
        
        try:
            await self.ctx.guild.create_custom_emoji(
                name=self.sticker.name,
                image=sticker_data,
                reason=f"Stealsticker by {self.ctx.author}"
            )
            await self.ctx.approve(f"`{self.sticker.name}` added to server")
        except Exception as e:
            await self.ctx.deny(f"Failed to add emoji: {e}")
        
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.red)
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.defer()
        
        await interaction.response.defer()
        await self.ctx.deny("Cancelled")
        self.stop()


class Emoji(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.group(name="emoji", invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def emoji_group(self, ctx):
        """Emoji management commands."""
        await ctx.send_help(ctx.command)

    @emoji_group.command(name="add")
    @commands.has_permissions(manage_guild=True)
    async def emoji_add(self, ctx):
        """Add a single emoji from an attachment or reference."""
        if not ctx.message.attachments:
            return await ctx.deny("Please attach an image or use a sticker")
        
        attachment = ctx.message.attachments[0]
        
        # Download the attachment
        emoji_data = await attachment.read()
        emoji_name = attachment.filename.split('.')[0]
        
        try:
            emoji = await ctx.guild.create_custom_emoji(
                name=emoji_name,
                image=emoji_data,
                reason=f"Added by {ctx.author}"
            )
            await ctx.approve(f"Emoji {emoji} added")
        except Exception as e:
            await ctx.deny(f"Failed to add emoji: {e}")

    @emoji_group.command(name="multiple")
    @commands.has_permissions(manage_guild=True)
    async def emoji_multiple(self, ctx):
        """Add multiple emojis from attachments."""
        if not ctx.message.attachments:
            return await ctx.deny("Please attach at least one image")
        
        attachments = ctx.message.attachments
        added = 0
        failed = 0
        
        for attachment in attachments:
            emoji_data = await attachment.read()
            emoji_name = attachment.filename.split('.')[0]
            
            try:
                await ctx.guild.create_custom_emoji(
                    name=emoji_name,
                    image=emoji_data,
                    reason=f"Added by {ctx.author}"
                )
                added += 1
            except Exception as e:
                failed += 1
        
        msg = f"Added {added} emoji(s)"
        if failed > 0:
            msg += f", {failed} failed"
        await ctx.approve(msg)

    @commands.command(name="stealsticker")
    @commands.has_permissions(manage_guild=True)
    async def stealsticker(self, ctx, sticker: discord.GuildSticker = None):
        """Steal a sticker with confirmation button."""
        if not sticker:
            if ctx.message.stickers:
                sticker = ctx.message.stickers[0]
            else:
                # Fetch recent sticker from channel history
                async for message in ctx.channel.history(limit=50):
                    if message.stickers:
                        sticker = message.stickers[0]
                        break
                
                if not sticker:
                    return await ctx.deny("No sticker found in recent messages. Please reference a sticker or provide one")
        
        
        # Get sticker as image
        async with aiohttp.ClientSession() as session:
            async with session.get(sticker.url) as resp:
                sticker_data = await resp.read()
        
        # Determine file extension
        ext = ".gif" if "gif" in sticker.url else ".png"
        
        # Send preview with confirmation
        file = discord.File(io.BytesIO(sticker_data), filename=f"{sticker.name}{ext}")
        
        embed = discord.Embed(title="Steal Sticker", color=Config.COLORS.DEFAULT)
        embed.add_field(name="Name", value=sticker.name)
        embed.set_image(url=f"attachment://{sticker.name}{ext}")
        
        view = ConfirmStealSticker(ctx, sticker)
        await ctx.send(embed=embed, file=file, view=view)


async def setup(bot):
    await bot.add_cog(Emoji(bot))
