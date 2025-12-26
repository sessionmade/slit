import discord
from discord.ext import commands
from src.config import Config
import aiohttp
from typing import Optional
from datetime import datetime

class LastFM(commands.Cog):
    """Last.fm integration commands"""
    
    def __init__(self, bot):
        self.bot = bot
        self.api_key = Config.LASTFM
        self.base_url = "http://ws.audioscrobbler.com/2.0/"
        bot.loop.create_task(self._setup_lastfm_table())
    
    async def _setup_lastfm_table(self):
        """Create lastfm users table if it doesn't exist"""
        await self.bot.wait_until_ready()
        if not getattr(self.bot, 'db_pool', None):
            return
        
        async with self.bot.db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("""
                    CREATE TABLE IF NOT EXISTS lastfm_users (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        user_id BIGINT NOT NULL UNIQUE,
                        lastfm_username VARCHAR(255) NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
    
    async def get_lastfm_user(self, user_id: int):
        """Get Last.fm username for a Discord user"""
        if not getattr(self.bot, 'db_pool', None):
            return None
        
        async with self.bot.db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT lastfm_username FROM lastfm_users WHERE user_id = %s",
                    (user_id,)
                )
                result = await cur.fetchone()
                return result[0] if result else None
    
    async def set_lastfm_user(self, user_id: int, lastfm_username: str):
        """Set Last.fm username for a Discord user"""
        if not getattr(self.bot, 'db_pool', None):
            return False
        
        async with self.bot.db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    INSERT INTO lastfm_users (user_id, lastfm_username)
                    VALUES (%s, %s)
                    ON DUPLICATE KEY UPDATE lastfm_username = VALUES(lastfm_username)
                    """,
                    (user_id, lastfm_username)
                )
                return True
    
    async def remove_lastfm_user(self, user_id: int):
        """Remove Last.fm username for a Discord user"""
        if not getattr(self.bot, 'db_pool', None):
            return False
        
        async with self.bot.db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "DELETE FROM lastfm_users WHERE user_id = %s",
                    (user_id,)
                )
                return True
    
    async def lastfm_request(self, method: str, params: dict):
        """Make a request to the Last.fm API"""
        params.update({
            'api_key': self.api_key,
            'format': 'json',
            'method': method
        })
        
        async with aiohttp.ClientSession() as session:
            async with session.get(self.base_url, params=params) as resp:
                if resp.status == 200:
                    return await resp.json()
                return None
    
    @commands.group(name='lastfm', aliases=['fm', 'lf'], invoke_without_command=True)
    async def lastfm(self, ctx, user: Optional[discord.Member] = None):
        """Show your currently playing or last played track"""
        user = user or ctx.author
        
        # Get Last.fm username
        lastfm_user = await self.get_lastfm_user(user.id)
        
        if not lastfm_user:
            if user == ctx.author:
                embed = discord.Embed(
                    description=f"{Config.EMOJIS.ERROR} You haven't set your Last.fm username. Use `;lastfm set <username>`",
                    color=Config.COLORS.ERROR
                )
            else:
                embed = discord.Embed(
                    description=f"{Config.EMOJIS.ERROR} **{user.name}** hasn't set their Last.fm username",
                    color=Config.COLORS.ERROR
                )
            return await ctx.send(embed=embed)
        
        # Get recent tracks
        data = await self.lastfm_request('user.getrecenttracks', {
            'user': lastfm_user,
            'limit': 1
        })
        
        if not data or 'recenttracks' not in data:
            embed = discord.Embed(
                description=f"{Config.EMOJIS.ERROR} Could not fetch Last.fm data",
                color=Config.COLORS.ERROR
            )
            return await ctx.send(embed=embed)
        
        tracks = data['recenttracks'].get('track', [])
        
        if not tracks:
            embed = discord.Embed(
                description=f"{Config.EMOJIS.ERROR} No recent tracks found",
                color=Config.COLORS.ERROR
            )
            return await ctx.send(embed=embed)
        
        # Get track info
        track = tracks[0] if isinstance(tracks, list) else tracks
        
        artist = track.get('artist', {})
        artist_name = artist.get('#text', 'Unknown') if isinstance(artist, dict) else str(artist)
        
        track_name = track.get('name', 'Unknown')
        album_name = track.get('album', {}).get('#text', 'Unknown')
        
        # Check if currently playing
        now_playing = '@attr' in track and 'nowplaying' in track['@attr']
        
        # Get album art
        images = track.get('image', [])
        image_url = None
        for img in images:
            if img.get('size') == 'large':
                image_url = img.get('#text')
                break
        
        # Create embed
        status = "Now Playing" if now_playing else "Last Played"
        
        embed = discord.Embed(
            description=f"**[{track_name}]({track.get('url', 'https://last.fm')})**\nby **{artist_name}**",
            color=Config.COLORS.DEFAULT
        )
        
        embed.set_author(
            name=f"Last.FM: {lastfm_user}",
            icon_url=user.display_avatar.url
        )
        
        if image_url:
            embed.set_thumbnail(url=image_url)
        
        await ctx.send(embed=embed)
    
    @lastfm.command(name='set')
    async def lastfm_set(self, ctx, username: str):
        """Set your Last.fm username"""
        # Verify the username exists
        data = await self.lastfm_request('user.getinfo', {'user': username})
        
        if not data or 'user' not in data:
            embed = discord.Embed(
                description=f"{Config.EMOJIS.ERROR} Last.fm user **{username}** not found",
                color=Config.COLORS.ERROR
            )
            return await ctx.send(embed=embed)
        
        # Save to database
        await self.set_lastfm_user(ctx.author.id, username)
        
        embed = discord.Embed(
            description=f"{Config.EMOJIS.SUCCESS} Set your Last.fm username to **{username}**",
            color=Config.COLORS.SUCCESS
        )
        await ctx.send(embed=embed)
    
    @lastfm.command(name='remove', aliases=['unset', 'delete'])
    async def lastfm_remove(self, ctx):
        """Remove your Last.fm username"""
        lastfm_user = await self.get_lastfm_user(ctx.author.id)
        
        if not lastfm_user:
            embed = discord.Embed(
                description=f"{Config.EMOJIS.ERROR} You don't have a Last.fm username set",
                color=Config.COLORS.ERROR
            )
            return await ctx.send(embed=embed)
        
        await self.remove_lastfm_user(ctx.author.id)
        
        embed = discord.Embed(
            description=f"{Config.EMOJIS.SUCCESS} Removed your Last.fm username",
            color=Config.COLORS.SUCCESS
        )
        await ctx.send(embed=embed)
    
    @lastfm.command(name='recent', aliases=['recents'])
    async def lastfm_recent(self, ctx, user: Optional[discord.Member] = None, limit: int = 10):
        """Show recent tracks"""
        user = user or ctx.author
        
        if limit < 1 or limit > 50:
            limit = 10
        
        # Get Last.fm username
        lastfm_user = await self.get_lastfm_user(user.id)
        
        if not lastfm_user:
            if user == ctx.author:
                embed = discord.Embed(
                    description=f"{Config.EMOJIS.ERROR} You haven't set your Last.fm username. Use `;lastfm set <username>`",
                    color=Config.COLORS.ERROR
                )
            else:
                embed = discord.Embed(
                    description=f"{Config.EMOJIS.ERROR} **{user.name}** hasn't set their Last.fm username",
                    color=Config.COLORS.ERROR
                )
            return await ctx.send(embed=embed)
        
        # Get recent tracks
        data = await self.lastfm_request('user.getrecenttracks', {
            'user': lastfm_user,
            'limit': limit
        })
        
        if not data or 'recenttracks' not in data:
            embed = discord.Embed(
                description=f"{Config.EMOJIS.ERROR} Could not fetch Last.fm data",
                color=Config.COLORS.ERROR
            )
            return await ctx.send(embed=embed)
        
        tracks = data['recenttracks'].get('track', [])
        
        if not tracks:
            embed = discord.Embed(
                description=f"{Config.EMOJIS.ERROR} No recent tracks found",
                color=Config.COLORS.ERROR
            )
            return await ctx.send(embed=embed)
        
        # Build track list
        track_list = []
        for idx, track in enumerate(tracks[:limit], 1):
            artist = track.get('artist', {})
            artist_name = artist.get('#text', 'Unknown') if isinstance(artist, dict) else str(artist)
            track_name = track.get('name', 'Unknown')
            
            now_playing = '@attr' in track and 'nowplaying' in track['@attr']
            status = "🎵" if now_playing else f"`{idx:02d}.`"
            
            track_list.append(f"{status} **{track_name}** by {artist_name}")
        
        embed = discord.Embed(
            description="\n".join(track_list),
            color=Config.COLORS.DEFAULT
        )
        
        embed.set_author(
            name=f"{user.name}'s Recent Tracks",
            icon_url=user.display_avatar.url
        )
        
        embed.set_footer(text=f"Last.fm: {lastfm_user}")
        
        await ctx.send(embed=embed)
    
    @lastfm.command(name='toptracks', aliases=['tt', 'tracks'])
    async def lastfm_toptracks(self, ctx, user: Optional[discord.Member] = None, period: str = '7day'):
        """Show top tracks (period: overall, 7day, 1month, 3month, 6month, 12month)"""
        user = user or ctx.author
        
        valid_periods = ['overall', '7day', '1month', '3month', '6month', '12month']
        if period not in valid_periods:
            period = '7day'
        
        # Get Last.fm username
        lastfm_user = await self.get_lastfm_user(user.id)
        
        if not lastfm_user:
            if user == ctx.author:
                embed = discord.Embed(
                    description=f"{Config.EMOJIS.ERROR} You haven't set your Last.fm username. Use `;lastfm set <username>`",
                    color=Config.COLORS.ERROR
                )
            else:
                embed = discord.Embed(
                    description=f"{Config.EMOJIS.ERROR} **{user.name}** hasn't set their Last.fm username",
                    color=Config.COLORS.ERROR
                )
            return await ctx.send(embed=embed)
        
        # Get top tracks
        data = await self.lastfm_request('user.gettoptracks', {
            'user': lastfm_user,
            'period': period,
            'limit': 10
        })
        
        if not data or 'toptracks' not in data:
            embed = discord.Embed(
                description=f"{Config.EMOJIS.ERROR} Could not fetch Last.fm data",
                color=Config.COLORS.ERROR
            )
            return await ctx.send(embed=embed)
        
        tracks = data['toptracks'].get('track', [])
        
        if not tracks:
            embed = discord.Embed(
                description=f"{Config.EMOJIS.ERROR} No top tracks found",
                color=Config.COLORS.ERROR
            )
            return await ctx.send(embed=embed)
        
        # Build track list
        track_list = []
        for idx, track in enumerate(tracks[:10], 1):
            artist = track.get('artist', {})
            artist_name = artist.get('name', 'Unknown') if isinstance(artist, dict) else str(artist)
            track_name = track.get('name', 'Unknown')
            playcount = track.get('playcount', 0)
            
            track_list.append(f"`{idx:02d}.` **{track_name}** by {artist_name} ({playcount} plays)")
        
        period_names = {
            'overall': 'Overall',
            '7day': 'Past 7 Days',
            '1month': 'Past Month',
            '3month': 'Past 3 Months',
            '6month': 'Past 6 Months',
            '12month': 'Past Year'
        }
        
        embed = discord.Embed(
            description="\n".join(track_list),
            color=Config.COLORS.DEFAULT
        )
        
        embed.set_author(
            name=f"{user.name}'s Top Tracks ({period_names.get(period, period)})",
            icon_url=user.display_avatar.url
        )
        
        embed.set_footer(text=f"Last.fm: {lastfm_user}")
        
        await ctx.send(embed=embed)
    
    @lastfm.command(name='topartists', aliases=['ta', 'artists'])
    async def lastfm_topartists(self, ctx, user: Optional[discord.Member] = None, period: str = '7day'):
        """Show top artists (period: overall, 7day, 1month, 3month, 6month, 12month)"""
        user = user or ctx.author
        
        valid_periods = ['overall', '7day', '1month', '3month', '6month', '12month']
        if period not in valid_periods:
            period = '7day'
        
        # Get Last.fm username
        lastfm_user = await self.get_lastfm_user(user.id)
        
        if not lastfm_user:
            if user == ctx.author:
                embed = discord.Embed(
                    description=f"{Config.EMOJIS.ERROR} You haven't set your Last.fm username. Use `;lastfm set <username>`",
                    color=Config.COLORS.ERROR
                )
            else:
                embed = discord.Embed(
                    description=f"{Config.EMOJIS.ERROR} **{user.name}** hasn't set their Last.fm username",
                    color=Config.COLORS.ERROR
                )
            return await ctx.send(embed=embed)
        
        # Get top artists
        data = await self.lastfm_request('user.gettopartists', {
            'user': lastfm_user,
            'period': period,
            'limit': 10
        })
        
        if not data or 'topartists' not in data:
            embed = discord.Embed(
                description=f"{Config.EMOJIS.ERROR} Could not fetch Last.fm data",
                color=Config.COLORS.ERROR
            )
            return await ctx.send(embed=embed)
        
        artists = data['topartists'].get('artist', [])
        
        if not artists:
            embed = discord.Embed(
                description=f"{Config.EMOJIS.ERROR} No top artists found",
                color=Config.COLORS.ERROR
            )
            return await ctx.send(embed=embed)
        
        # Build artist list
        artist_list = []
        for idx, artist in enumerate(artists[:10], 1):
            artist_name = artist.get('name', 'Unknown')
            playcount = artist.get('playcount', 0)
            
            artist_list.append(f"`{idx:02d}.` **{artist_name}** ({playcount} plays)")
        
        period_names = {
            'overall': 'Overall',
            '7day': 'Past 7 Days',
            '1month': 'Past Month',
            '3month': 'Past 3 Months',
            '6month': 'Past 6 Months',
            '12month': 'Past Year'
        }
        
        embed = discord.Embed(
            description="\n".join(artist_list),
            color=Config.COLORS.DEFAULT
        )
        
        embed.set_author(
            name=f"{user.name}'s Top Artists ({period_names.get(period, period)})",
            icon_url=user.display_avatar.url
        )
        
        embed.set_footer(text=f"Last.fm: {lastfm_user}")
        
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(LastFM(bot))
