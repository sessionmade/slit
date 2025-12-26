import discord
import aiohttp
import re
from datetime import datetime
from discord.ext import commands
from src.config import Config


class Social(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.session = None

    async def get_session(self):
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session

    async def cog_unload(self):
        if self.session and not self.session.closed:
            await self.session.close()

    # ==================== TIKTOK ====================
    @commands.command(name="tiktok", aliases=["tt"])
    async def tiktok(self, ctx, username: str):
        """Look up a TikTok profile"""
        username = username.lstrip("@")
        session = await self.get_session()
        
        async with session.get(
            "https://tiktok-scraper7.p.rapidapi.com/user/info",
            params={"unique_id": username},
            headers={
                "X-RapidAPI-Key": Config.RAPIDAPI_KEY,
                "X-RapidAPI-Host": "tiktok-scraper7.p.rapidapi.com"
            }
        ) as resp:
            if resp.status != 200:
                return await ctx.deny(f"API returned status {resp.status}")
            data = await resp.json()
            
        if data.get("code") != 0 or not data.get("data"):
            return await ctx.deny(f"Could not find TikTok user **@{username}**")
        
        user = data["data"]["user"]
        stats = data["data"]["stats"]
        
        display_name = user.get("nickname", username)
        bio = user.get("signature", "No bio") or "No bio"
        user_id = user.get("id", "Unknown")
        avatar = user.get("avatarLarger", "")
        
        followers = stats.get("followerCount", 0)
        following = stats.get("followingCount", 0)
        likes = stats.get("heartCount", 0)
        videos = stats.get("videoCount", 0)

        embed = discord.Embed(
            title=f"@{display_name}",
            url=f"https://www.tiktok.com/@{username}",
            description=bio[:200] if bio else "No bio",
            color=Config.COLORS.SUCCESS
        )
        embed.add_field(name="Username", value=f"@{username}", inline=True)
        embed.add_field(name="Followers", value=f"{followers:,}", inline=True)
        embed.add_field(name="Following", value=f"{following:,}", inline=True)
        embed.add_field(name="Likes", value=f"{likes:,}", inline=True)
        embed.add_field(name="Videos", value=f"{videos:,}", inline=True)
        embed.set_footer(text=f"ID: {user_id}")
        if avatar:
            embed.set_thumbnail(url=avatar)
        
        await ctx.reply(embed=embed, mention_author=False)

    # ==================== INSTAGRAM ====================
    @commands.command(name="instagram", aliases=["ig"])
    async def instagram(self, ctx, *, username: str):
        """View an Instagram user's profile"""
        username = username.lstrip("@")
        session = await self.get_session()
        
        async with ctx.typing():
            try:
                api_url = f"https://i.instagram.com/api/v1/users/web_profile_info/?username={username}"
                headers = {
                    "User-Agent": "Instagram 76.0.0.15.395 Android",
                    "x-ig-app-id": "936619743392459"
                }
                
                async with session.get(api_url, headers=headers) as resp:
                    if resp.status != 200:
                        return await ctx.deny(f"Could not find user **@{username}**")
                    data = await resp.json()
                    
            except Exception:
                return await ctx.deny("Could not fetch user data")
            
            user = data.get("data", {}).get("user", {})
            if not user:
                return await ctx.deny(f"Could not find user **@{username}**")
            
            embed = discord.Embed(
                title=user.get("full_name") or f"@{username}",
                url=f"https://www.instagram.com/{username}",
                description=user.get("biography") or "No bio",
                color=Config.COLORS.SUCCESS
            )
            
            if user.get("profile_pic_url_hd"):
                embed.set_thumbnail(url=user["profile_pic_url_hd"])
            
            embed.add_field(name="Username", value=f"@{user.get('username', username)}", inline=True)
            embed.add_field(name="Followers", value=f"{user.get('edge_followed_by', {}).get('count', 0):,}", inline=True)
            embed.add_field(name="Following", value=f"{user.get('edge_follow', {}).get('count', 0):,}", inline=True)
            embed.add_field(name="Posts", value=f"{user.get('edge_owner_to_timeline_media', {}).get('count', 0):,}", inline=True)
            
            if user.get("is_verified"):
                embed.add_field(name="Verified", value="Yes", inline=True)
            if user.get("is_private"):
                embed.add_field(name="Private", value="Yes", inline=True)
            if user.get("external_url"):
                embed.add_field(name="Website", value=user["external_url"], inline=False)
            
            embed.set_footer(text=f"ID: {user.get('id', 'Unknown')}")
            
            await ctx.reply(embed=embed, mention_author=False)

    # ==================== ROBLOX ====================
    @commands.command(name="roblox")
    async def roblox(self, ctx, username: str):
        """Look up a Roblox profile"""
        session = await self.get_session()
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json",
        }
        
        # Get user ID from username
        async with session.post(
            "https://users.roblox.com/v1/usernames/users",
            json={"usernames": [username], "excludeBannedUsers": False},
            headers=headers
        ) as resp:
            if resp.status != 200:
                return await ctx.deny("Failed to connect to Roblox")
            data = await resp.json()
            
        if not data.get("data"):
            return await ctx.deny(f"Could not find Roblox user **{username}**")
        
        user_data = data["data"][0]
        user_id = user_data["id"]
        display_name = user_data.get("displayName", username)
        
        # Get user info
        description = "No description"
        created = "Unknown"
        is_banned = False
        async with session.get(f"https://users.roblox.com/v1/users/{user_id}", headers=headers) as resp:
            if resp.status == 200:
                user_info = await resp.json()
                description = user_info.get("description", "") or "No description"
                is_banned = user_info.get("isBanned", False)
                created_raw = user_info.get("created", "")
                if created_raw:
                    try:
                        dt = datetime.fromisoformat(created_raw.replace("Z", "+00:00"))
                        created = dt.strftime("%B %d, %Y")
                    except:
                        created = created_raw[:10]

        # Get friends count
        friends = 0
        async with session.get(f"https://friends.roblox.com/v1/users/{user_id}/friends/count", headers=headers) as resp:
            if resp.status == 200:
                friends_data = await resp.json()
                friends = friends_data.get("count", 0)

        # Get followers count
        followers = 0
        async with session.get(f"https://friends.roblox.com/v1/users/{user_id}/followers/count", headers=headers) as resp:
            if resp.status == 200:
                followers_data = await resp.json()
                followers = followers_data.get("count", 0)

        # Get following count
        following = 0
        async with session.get(f"https://friends.roblox.com/v1/users/{user_id}/followings/count", headers=headers) as resp:
            if resp.status == 200:
                following_data = await resp.json()
                following = following_data.get("count", 0)

        # Get presence (online status)
        presence = "Offline"
        last_online = "Unknown"
        async with session.post(
            "https://presence.roblox.com/v1/presence/users",
            json={"userIds": [user_id]},
            headers=headers
        ) as resp:
            if resp.status == 200:
                presence_data = await resp.json()
                if presence_data.get("userPresences"):
                    p = presence_data["userPresences"][0]
                    presence_type = p.get("userPresenceType", 0)
                    if presence_type == 0:
                        presence = "Offline"
                    elif presence_type == 1:
                        presence = "Online"
                    elif presence_type == 2:
                        presence = "In Game"
                    elif presence_type == 3:
                        presence = "In Studio"
                    last_online_raw = p.get("lastOnline", "")
                    if last_online_raw:
                        try:
                            dt = datetime.fromisoformat(last_online_raw.replace("Z", "+00:00"))
                            last_online = dt.strftime("%B %d, %Y")
                        except:
                            last_online = "Unknown"

        # Get Rolimons data (RAP, Value)
        rap = 0
        value = 0
        try:
            async with session.get(
                f"https://www.rolimons.com/playerapi/player/{user_id}",
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            ) as resp:
                if resp.status == 200:
                    rolimons_data = await resp.json()
                    if rolimons_data.get("success"):
                        rap = rolimons_data.get("rap", 0) or 0
                        value = rolimons_data.get("value", 0) or 0
        except:
            pass

        embed = discord.Embed(
            title=display_name,
            url=f"https://www.roblox.com/users/{user_id}/profile",
            description=f"{friends:,} Friends | {followers:,} Followers | {following:,} Following",
            color=Config.COLORS.SUCCESS
        )
        
        embed.add_field(name="ID", value=str(user_id), inline=True)
        embed.add_field(name="Verified", value="No", inline=True)
        embed.add_field(name="Banned", value="Yes" if is_banned else "No", inline=True)
        
        embed.add_field(name="RAP", value=f"{rap:,}", inline=True)
        embed.add_field(name="Value", value=f"{value:,}", inline=True)
        embed.add_field(name="Status", value=presence, inline=True)
        
        embed.add_field(name="Created", value=created, inline=True)
        embed.add_field(name="Last Online", value=last_online, inline=True)
        embed.add_field(name="\u200b", value="\u200b", inline=True)
        
        embed.add_field(name="Description", value=description[:1024] if description else "No description", inline=False)
        
        embed.set_thumbnail(url=f"https://www.roblox.com/headshot-thumbnail/image?userId={user_id}&width=420&height=420&format=png")
        embed.set_image(url=f"https://www.roblox.com/avatar-thumbnail/image?userId={user_id}&width=420&height=420&format=png")
        
        await ctx.reply(embed=embed, mention_author=False)

    # ==================== TELEGRAM ====================
    @commands.command(name="telegram", aliases=["tg"])
    async def telegram(self, ctx, username: str):
        """Look up a Telegram profile"""
        username = username.lstrip("@")
        session = await self.get_session()
        
        try:
            async with session.get(
                f"https://t.me/{username}",
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            ) as resp:
                if resp.status != 200:
                    return await ctx.deny(f"Could not find Telegram user **@{username}**")
                html = await resp.text()
                
            if "tgme_page_title" not in html and "tgme_channel_info" not in html:
                return await ctx.deny(f"Could not find Telegram user **@{username}**")
            
            title_match = re.search(r'<div class="tgme_page_title[^"]*"[^>]*><span[^>]*>([^<]+)</span>', html)
            desc_match = re.search(r'<div class="tgme_page_description[^"]*"[^>]*>([^<]+)', html)
            
            display_name = title_match.group(1) if title_match else username
            bio = desc_match.group(1).strip() if desc_match else "No bio"
                
        except Exception:
            return await ctx.deny("Failed to connect to Telegram")

        embed = discord.Embed(
            title=f"@{display_name}",
            url=f"https://t.me/{username}",
            description=bio[:200] if bio else "No bio",
            color=Config.COLORS.SUCCESS
        )
        embed.add_field(name="Username", value=f"@{username}", inline=True)
        embed.set_footer(text="Telegram")
        
        await ctx.reply(embed=embed, mention_author=False)

    # ==================== ERROR HANDLERS ====================
    @tiktok.error
    @instagram.error
    @roblox.error
    @telegram.error
    async def social_error(self, ctx, error):
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.deny("Please provide a **username**")
        else:
            # Show the actual error for debugging
            error = getattr(error, 'original', error)
            await ctx.deny(f"Error: {str(error)[:100]}")


async def setup(bot):
    await bot.add_cog(Social(bot))
