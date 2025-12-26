import discord
from discord.ext import commands
import aiohttp
from src.config import Config
from src.tools.paginator import PaginatorView


class Crypto(commands.Cog):
    """Cryptocurrency commands"""

    def __init__(self, bot):
        self.bot = bot
        self.base_url = "https://pro-api.coinmarketcap.com/v1"
        self.api_key = Config.COINMARKETCAP

    async def fetch_crypto(self, symbol: str):
        """Fetch crypto data from CoinMarketCap API"""
        url = f"{self.base_url}/cryptocurrency/quotes/latest"
        headers = {"X-CMC_PRO_API_KEY": self.api_key, "Accepts": "application/json"}
        params = {"symbol": symbol.upper()}
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, params=params) as resp:
                if resp.status != 200:
                    return None
                return await resp.json()

    async def fetch_conversion(self, amount: float, from_symbol: str, to_symbols: str):
        """Fetch conversion data from CoinMarketCap API"""
        url = f"{self.base_url}/tools/price-conversion"
        headers = {"X-CMC_PRO_API_KEY": self.api_key, "Accepts": "application/json"}
        params = {
            "amount": amount,
            "symbol": from_symbol.upper(),
            "convert": to_symbols.upper()
        }
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, params=params) as resp:
                if resp.status != 200:
                    return None
                try:
                    return await resp.json()
                except:
                    return None

    async def fetch_logo(self, symbol: str):
        """Fetch coin logo from CoinMarketCap API"""
        url = f"{self.base_url}/cryptocurrency/info"
        headers = {"X-CMC_PRO_API_KEY": self.api_key, "Accepts": "application/json"}
        params = {"symbol": symbol.upper()}
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, params=params) as resp:
                if resp.status != 200:
                    return None
                return await resp.json()

    @commands.group(name="crypto", invoke_without_command=True)
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def crypto(self, ctx, symbol: str = None):
        """Get cryptocurrency information"""
        if not symbol:
            return await ctx.send_help(ctx.command)

        data = await self.fetch_crypto(symbol)
        if not data or data.get("status", {}).get("error_code") != 0:
            return await ctx.deny(f"Could not fetch data for **{symbol.upper()}**")

        coin = data["data"][symbol.upper()]
        quote = coin["quote"]["USD"]
        price = f"${quote['price']:,.2f}"
        p1h = f"{quote['percent_change_1h']:.2f}%"
        p24h = f"{quote['percent_change_24h']:.2f}%"
        p7d = f"{quote['percent_change_7d']:.2f}%"
        p30d = f"{quote['percent_change_30d']:.2f}%"

        logo_data = await self.fetch_logo(symbol)
        logo_url = None
        if logo_data and "data" in logo_data and symbol.upper() in logo_data["data"]:
            logo_url = logo_data["data"][symbol.upper()]["logo"]

        embed = discord.Embed(
            description=f"**(USD) Current Price**\n> {price}\n\u200b",
            color=Config.COLORS.DEFAULT
        )
        embed.add_field(name="(1h) Change", value=f"> {p1h}", inline=True)
        embed.add_field(name="(24h) Change", value=f"> {p24h}", inline=True)
        embed.add_field(name="\u200b", value="\u200b", inline=True)
        embed.add_field(name="(7d) Change", value=f"> {p7d}", inline=True)
        embed.add_field(name="(30d) Change", value=f"> {p30d}", inline=True)
        embed.add_field(name="\u200b", value="\u200b", inline=True)
        embed.set_author(name=f"[{coin['name']}] {coin['symbol']} Information", icon_url=logo_url)

        await ctx.send(embed=embed)

    @crypto.command(name="convert")
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def convert(self, ctx, amount: float = None, from_symbol: str = None, to_symbol: str = None):
        """Convert between cryptocurrencies"""
        if not amount or not from_symbol or not to_symbol:
            return await ctx.send_help(ctx.command)

        data = await self.fetch_conversion(amount, from_symbol, to_symbol)
        if not data or data.get("status", {}).get("error_code") != 0:
            return await ctx.deny("Failed to fetch conversion")

        try:
            converted_value = data["data"]["quote"][to_symbol.upper()]["price"]
        except:
            return await ctx.deny("Error parsing conversion result")

        usd_from = None
        usd_to = None

        from_usd = await self.fetch_conversion(amount, from_symbol, "USD")
        if from_usd and from_usd.get("status", {}).get("error_code") == 0:
            usd_from = from_usd["data"]["quote"]["USD"]["price"]

        to_usd = await self.fetch_conversion(1, to_symbol, "USD")
        if to_usd and to_usd.get("status", {}).get("error_code") == 0:
            usd_to = to_usd["data"]["quote"]["USD"]["price"]

        desc = f"> **{amount} {from_symbol.upper()} = {converted_value:,.6f} {to_symbol.upper()}**\n\n"
        if usd_from and usd_to:
            desc += (
                f"> **{amount} {from_symbol.upper()} = ${usd_from:,.2f}**\n"
                f"> **{converted_value:,.6f} {to_symbol.upper()} = ${converted_value * usd_to:,.2f}**"
            )

        embed = discord.Embed(description=desc, color=Config.COLORS.DEFAULT)
        embed.set_author(name="Crypto Conversion", icon_url=ctx.bot.user.display_avatar.url)

        await ctx.send(embed=embed)

    @crypto.command(name="price")
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def price(self, ctx, symbol: str = None, amount: float = 1.0):
        """Get the price of a cryptocurrency in USD"""
        if not symbol:
            return await ctx.send_help(ctx.command)

        data = await self.fetch_conversion(amount, symbol, "USD")
        if not data or data.get("status", {}).get("error_code") != 0:
            return await ctx.deny(f"Could not fetch price for **{symbol.upper()}**")

        usd_value = data["data"]["quote"]["USD"]["price"]
        desc = f"> **{amount:,.3f} {symbol.upper()} = ${usd_value:,.2f}**"

        embed = discord.Embed(description=desc, color=Config.COLORS.DEFAULT)
        embed.set_author(name="Crypto Price", icon_url=ctx.bot.user.display_avatar.url)

        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Crypto(bot))
