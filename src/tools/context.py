import discord
from discord.ext import commands
from src.config import Config

class CustomContext(commands.Context):
    """Custom context class with enhanced embed responses"""
    
    async def approve(self, message: str, **kwargs) -> discord.Message:
        """
        Send an approval/success embed
        
        Args:
            message: The message to display
            **kwargs: Additional embed parameters (title, footer, etc.)
        """
        embed = discord.Embed(
            description=f"{Config.EMOJIS.SUCCESS} {self.author.mention}: {message}",
            color=Config.COLORS.SUCCESS,
            **kwargs
        )
        return await self.reply(embed=embed, mention_author=False)
    
    async def deny(self, message: str, **kwargs) -> discord.Message:
        """
        Send a denial/error embed
        
        Args:
            message: The message to display
            **kwargs: Additional embed parameters (title, footer, etc.)
        """
        embed = discord.Embed(
            description=f"{Config.EMOJIS.ERROR} {self.author.mention}: {message}",
            color=Config.COLORS.ERROR,
            **kwargs
        )
        return await self.reply(embed=embed, mention_author=False)
        
    async def neutral(self, message: str, **kwargs) -> discord.Message:
        """
        Send a neutral embed
        
        Args:
            message: The message to display
            **kwargs: Additional embed parameters (title, footer, etc.)
        """
        embed = discord.Embed(
            description=f"{self.author.mention}: {message}",
            color=Config.COLORS.DEFAULT,
            **kwargs
        )
        return await self.reply(embed=embed, mention_author=False)
        
    async def warn(self, message: str, **kwargs) -> discord.Message:
        """
        Send a warning embed
        
        Args:
            message: The message to display
            **kwargs: Additional embed parameters (title, footer, etc.)
        """
        embed = discord.Embed(
            description=f"{Config.EMOJIS.WARNING} {self.author.mention}: {message}",
            color=Config.COLORS.WARNING,
            **kwargs
        )
        return await self.reply(embed=embed, mention_author=False)
