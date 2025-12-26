from .autoresponder import AutoResponder


async def setup(bot):
    await bot.add_cog(AutoResponder(bot))
