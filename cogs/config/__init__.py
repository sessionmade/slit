from .config import GuildConfig


async def setup(bot):
    await bot.add_cog(GuildConfig(bot))
