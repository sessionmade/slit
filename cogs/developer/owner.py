import discord
from discord.ext import commands
from src.config import Config
import aiohttp
import aiomysql
from typing import Union
import datetime
import os
import subprocess
import asyncio

class Owner(commands.Cog):
    """Owner-only commands"""
    
    def __init__(self, bot):
        self.bot = bot
        self.db_pool = None
    
    async def cog_load(self):
        """Initialize database connection pool"""
        self.db_pool = await aiomysql.create_pool(
            host=Config.DB_HOST,
            port=Config.DB_PORT,
            user=Config.DB_USER,
            password=Config.DB_PASSWORD,
            db=Config.DB_NAME,
            autocommit=True
        )
    
    async def cog_unload(self):
        """Cleanup when cog is unloaded"""
        if self.db_pool:
            self.db_pool.close()
            await self.db_pool.wait_closed()
    
    async def cog_check(self, ctx):
        """Check if the user is the bot owner"""
        return await self.bot.is_owner(ctx.author)
    
    def get_cog_path(self, cog_name: str):
        """Find the full path of a cog by its name"""
        cog_name_lower = cog_name.lower()
        
        # Search in cogs directory and subdirectories
        for root, dirs, files in os.walk('cogs'):
            for file in files:
                if file.endswith('.py') and file[:-3].lower() == cog_name_lower:
                    # Convert file path to module path
                    path = os.path.join(root, file)
                    module_path = path.replace(os.sep, '.')[:-3]  # Remove .py
                    return module_path
        
        return None
    
    @commands.command(name="gitpull", aliases=["pull", "update"])
    async def gitpull(self, ctx):
        """Pull the latest changes from the GitHub repository"""
        embed = discord.Embed(
            title="Pulling from GitHub",
            description="Fetching latest changes",
            color=Config.COLORS.DEFAULT
        )
        msg = await ctx.send(embed=embed)
        
        try:
            # Run git pull command
            process = await asyncio.create_subprocess_exec(
                'git', 'pull',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            # Decode output
            output = stdout.decode('utf-8') if stdout else ""
            error = stderr.decode('utf-8') if stderr else ""
            
            # Check if successful
            if process.returncode == 0:
                # Check if already up to date
                if "Already up to date" in output or "Already up-to-date" in output:
                    embed = discord.Embed(
                        title="Already Up to Date",
                        description="No new changes to pull.",
                        color=Config.COLORS.WARNING
                    )
                else:
                    # Show changes
                    changes = output.strip() if output else "Changes pulled successfully"
                    
                    embed = discord.Embed(
                        title="✅ Successfully Pulled",
                        description=f"```\n{changes[:1900]}\n```",
                        color=Config.COLORS.SUCCESS
                    )
                    embed.set_footer(text=f"Use {ctx.prefix}reload all to reload all cogs with the new changes")
            else:
                # Error occurred
                error_msg = error if error else "Unknown error occurred"
                embed = discord.Embed(
                    title="❌ Pull Failed",
                    description=f"```\n{error_msg[:1900]}\n```",
                    color=Config.COLORS.ERROR
                )
            
            await msg.edit(embed=embed)
            
        except FileNotFoundError:
            embed = discord.Embed(
                title="❌ Git Not Found",
                description="Git is not installed or not in PATH.",
                color=Config.COLORS.ERROR
            )
            await msg.edit(embed=embed)
        except Exception as e:
            embed = discord.Embed(
                title="❌ Error",
                description=f"```py\n{str(e)[:1900]}\n```",
                color=Config.COLORS.ERROR
            )
            await msg.edit(embed=embed)
    
    @commands.group(name="reload", invoke_without_command=True)
    async def reload(self, ctx, cog: str):
        """Reload a cog by its name (e.g., ,reload music)"""
        # Find the cog path
        cog_path = self.get_cog_path(cog)
        
        if not cog_path:
            embed = discord.Embed(
                description=f"{Config.EMOJIS.ERROR} Cog `{cog}` not found",
                color=Config.COLORS.ERROR
            )
            await ctx.send(embed=embed)
            return
        
        try:
            await self.bot.reload_extension(cog_path)
            embed = discord.Embed(
                description=f"{Config.EMOJIS.SUCCESS} Reloaded `{cog_path}`",
                color=Config.COLORS.SUCCESS
            )
            await ctx.send(embed=embed)
        except Exception as e:
            embed = discord.Embed(
                description=f"{Config.EMOJIS.ERROR} Failed to reload `{cog_path}`\n```py\n{e}\n```",
                color=Config.COLORS.ERROR
            )
            await ctx.send(embed=embed)
    
    @reload.command(name="all")
    async def reload_all(self, ctx):
        """Reload all cogs"""
        reloaded = []
        failed = []
        
        # Get all loaded extensions
        extensions = list(self.bot.extensions.keys())
        
        for extension in extensions:
            try:
                await self.bot.reload_extension(extension)
                reloaded.append(extension)
            except Exception as e:
                failed.append(f"{extension}: {str(e)}")
        
        embed = discord.Embed(
            title="Reload All Cogs",
            color=Config.COLORS.SUCCESS if not failed else Config.COLORS.WARNING
        )
        
        if reloaded:
            embed.add_field(
                name=f"✅ Reloaded ({len(reloaded)})",
                value="\n".join([f"`{ext}`" for ext in reloaded]) if len(reloaded) <= 10 else f"`{len(reloaded)} cogs reloaded`",
                inline=False
            )
        
        if failed:
            embed.add_field(
                name=f"❌ Failed ({len(failed)})",
                value="\n".join([f"`{ext}`" for ext in failed[:5]]),
                inline=False
            )
        
        await ctx.send(embed=embed)
    
    @commands.command(name="load")
    async def load(self, ctx, cog: str):
        """Load a cog by its name"""
        cog_path = self.get_cog_path(cog)
        
        if not cog_path:
            embed = discord.Embed(
                description=f"{Config.EMOJIS.ERROR} Cog `{cog}` not found",
                color=Config.COLORS.ERROR
            )
            await ctx.send(embed=embed)
            return
        
        try:
            await self.bot.load_extension(cog_path)
            embed = discord.Embed(
                description=f"{Config.EMOJIS.SUCCESS} Loaded `{cog_path}`",
                color=Config.COLORS.SUCCESS
            )
            await ctx.send(embed=embed)
        except Exception as e:
            embed = discord.Embed(
                description=f"{Config.EMOJIS.ERROR} Failed to load `{cog_path}`\n```py\n{e}\n```",
                color=Config.COLORS.ERROR
            )
            await ctx.send(embed=embed)
    
    @commands.command(name="unload")
    async def unload(self, ctx, cog: str):
        """Unload a cog by its name"""
        cog_path = self.get_cog_path(cog)
        
        if not cog_path:
            embed = discord.Embed(
                description=f"{Config.EMOJIS.ERROR} Cog `{cog}` not found",
                color=Config.COLORS.ERROR
            )
            await ctx.send(embed=embed)
            return
        
        try:
            await self.bot.unload_extension(cog_path)
            embed = discord.Embed(
                description=f"{Config.EMOJIS.SUCCESS} Unloaded `{cog_path}`",
                color=Config.COLORS.SUCCESS
            )
            await ctx.send(embed=embed)
        except Exception as e:
            embed = discord.Embed(
                description=f"{Config.EMOJIS.ERROR} Failed to unload `{cog_path}`\n```py\n{e}\n```",
                color=Config.COLORS.ERROR
            )
            await ctx.send(embed=embed)
    
    @commands.command(name="cogs", aliases=["extensions"])
    async def cogs(self, ctx):
        """List all loaded cogs"""
        extensions = list(self.bot.extensions.keys())
        
        embed = discord.Embed(
            title="Loaded Cogs",
            description=f"Total: **{len(extensions)}** cogs",
            color=Config.COLORS.DEFAULT
        )
        
        # Group by directory
        grouped = {}
        for ext in extensions:
            parts = ext.split('.')
            if len(parts) > 1:
                category = parts[1] if len(parts) > 2 else parts[0]  # Use subfolder name
                name = parts[-1]
            else:
                category = "root"
                name = ext
            
            if category not in grouped:
                grouped[category] = []
            grouped[category].append(name)
        
        for category, cog_list in sorted(grouped.items()):
            cog_names = ", ".join([f"`{c}`" for c in sorted(cog_list)])
            embed.add_field(
                name=f"📁 {category}",
                value=cog_names,
                inline=False
            )
        
        await ctx.send(embed=embed)

    @commands.command(name="setpfp")
    async def set_profile_picture(self, ctx, url: str):
        """Sets the bot's profile picture using a URL."""
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    return await ctx.send("Could not download image.")
                data = await resp.read()
                try:
                    await self.bot.user.edit(avatar=data)
                    await ctx.send("Profile picture updated successfully!")
                except discord.HTTPException as e:
                    await ctx.send(f"Failed to update profile picture: {e}")

    @commands.command(name="setbanner")
    async def set_banner(self, ctx, url: str):
        """Sets the bot's banner using a URL."""
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    return await ctx.send("Could not download image.")
                data = await resp.read()
                try:
                    await self.bot.user.edit(banner=data)
                    await ctx.send("Banner updated successfully!")
                except discord.HTTPException as e:
                    await ctx.send(f"Failed to update banner: {e}")

async def setup(bot):
    await bot.add_cog(Owner(bot))
