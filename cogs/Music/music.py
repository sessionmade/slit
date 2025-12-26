import discord
from discord.ext import commands
import wavelink
import json
import os

# ---------------- Music Channel Config ----------------
MUSIC_CHANNELS_FILE = "src/music_channels.json"

if not os.path.exists(MUSIC_CHANNELS_FILE):
    with open(MUSIC_CHANNELS_FILE, "w") as f:
        json.dump({}, f)


def get_music_channel(guild_id):
    with open(MUSIC_CHANNELS_FILE, "r") as f:
        data = json.load(f)
    return int(data.get(str(guild_id), 0))


def set_music_channel(guild_id, channel_id):
    with open(MUSIC_CHANNELS_FILE, "r") as f:
        data = json.load(f)
    data[str(guild_id)] = channel_id
    with open(MUSIC_CHANNELS_FILE, "w") as f:
        json.dump(data, f, indent=4)


def format_duration(ms) -> str:
    if not ms:
        return "Unknown"
    seconds = int(ms) // 1000
    if seconds < 3600:
        return f"{seconds // 60}:{seconds % 60:02d}"
    return f"{seconds // 3600}:{(seconds % 3600) // 60:02d}:{seconds % 60:02d}"


class NowPlayingControls(discord.ui.View):
    def __init__(self, player):
        super().__init__(timeout=60)
        self.player = player

    @discord.ui.button(label="◀◀", style=discord.ButtonStyle.secondary)
    async def rewind_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.player and self.player.current:
            await self.player.seek(0)
            await interaction.response.send_message("Restarted", ephemeral=True)
        else:
            await interaction.response.send_message("Nothing playing", ephemeral=True)

    @discord.ui.button(label="▐▐", style=discord.ButtonStyle.secondary)
    async def pause_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.player:
            if self.player.paused:
                await self.player.pause(False)
                await interaction.response.send_message("Resumed", ephemeral=True)
            else:
                await self.player.pause(True)
                await interaction.response.send_message("Paused", ephemeral=True)
        else:
            await interaction.response.send_message("Nothing playing", ephemeral=True)

    @discord.ui.button(label="▶▶", style=discord.ButtonStyle.secondary)
    async def skip_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.player and self.player.playing:
            await self.player.skip()
            await interaction.response.send_message("Skipped", ephemeral=True)
        else:
            await interaction.response.send_message("Nothing playing", ephemeral=True)


class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.loop_mode = {}
        self.requesters = {}

    async def cog_load(self):
        self.bot.loop.create_task(self.connect_nodes())

    async def connect_nodes(self):
        await self.bot.wait_until_ready()
        try:
            node = wavelink.Node(uri="http://melo.wisp.uno:9394", password="zokys")
            await wavelink.Pool.connect(client=self.bot, nodes=[node])
            print("[Music] Connected to Lavalink")
        except Exception as e:
            print(f"[Music] Failed to connect to Lavalink: {e}")

    async def cog_unload(self):
        try:
            await wavelink.Pool.close()
        except:
            pass

    async def check_channel(self, ctx):
        music_channel_id = get_music_channel(ctx.guild.id)
        if music_channel_id and ctx.channel.id != music_channel_id:
            await ctx.deny(f"Music commands only allowed in <#{music_channel_id}>")
            return False
        return True

    @commands.Cog.listener()
    async def on_wavelink_track_end(self, payload: wavelink.TrackEndEventPayload):
        player = payload.player
        if not player or not player.guild:
            return
        guild_id = player.guild.id
        loop_mode = self.loop_mode.get(guild_id, "off")
        if loop_mode == "song" and payload.track:
            await player.play(payload.track)
            return
        if loop_mode == "queue" and payload.track:
            await player.queue.put_wait(payload.track)
        if not player.queue.is_empty:
            await player.play(player.queue.get())

    @commands.command()
    async def play(self, ctx, *, search: str = None):
        if not search:
            return await ctx.deny("Please provide a song to search")
        if not await self.check_channel(ctx):
            return
        if not ctx.author.voice:
            return await ctx.deny("Join a voice channel first")

        # Check if Lavalink is connected
        if not wavelink.Pool.nodes:
            return await ctx.deny("Music server not connected. Try again in a moment.")

        player = ctx.voice_client
        if not player:
            try:
                player = await ctx.author.voice.channel.connect(cls=wavelink.Player, self_deaf=True)
                player.text_channel = ctx.channel
            except Exception as e:
                return await ctx.deny(f"Could not join voice channel: {e}")

        guild_id = ctx.guild.id
        self.loop_mode.setdefault(guild_id, "off")
        self.requesters.setdefault(guild_id, {})

        try:
            tracks = None
            if search.startswith(("http://", "https://")):
                tracks = await wavelink.Playable.search(search)
            else:
                # Try multiple search sources
                for source in ["ytsearch:", "scsearch:", ""]:
                    try:
                        tracks = await wavelink.Playable.search(f"{source}{search}")
                        if tracks:
                            break
                    except:
                        continue
        except Exception as e:
            print(f"[Music] Search error: {e}")
            return await ctx.deny(f"Search error: {e}")

        if not tracks:
            return await ctx.deny("Could not find that song")

        if isinstance(tracks, wavelink.Playlist):
            for track in tracks.tracks:
                self.requesters[guild_id][track.identifier] = ctx.author
                await player.queue.put_wait(track)
            await ctx.approve(f"Added playlist **{tracks.name}**")
            if not player.playing:
                await player.play(player.queue.get())
        else:
            track = tracks[0]
            self.requesters[guild_id][track.identifier] = ctx.author
            if player.playing:
                await player.queue.put_wait(track)
                await ctx.approve(f"Added **{track.title}** to queue")
            else:
                await player.play(track)
                await ctx.approve(f"Now playing **{track.title}**")

    @commands.command()
    async def pause(self, ctx):
        if not await self.check_channel(ctx):
            return
        player = ctx.voice_client
        if player and player.playing:
            await player.pause(True)
            await ctx.approve("Paused")
        else:
            await ctx.deny("Nothing is playing")

    @commands.command()
    async def resume(self, ctx):
        if not await self.check_channel(ctx):
            return
        player = ctx.voice_client
        if player and player.paused:
            await player.pause(False)
            await ctx.approve("Resumed")
        else:
            await ctx.deny("Nothing to resume")

    @commands.command()
    async def skip(self, ctx):
        if not await self.check_channel(ctx):
            return
        player = ctx.voice_client
        if player and player.playing:
            await player.skip()
            await ctx.approve("Skipped")
        else:
            await ctx.deny("Nothing is playing")

    @commands.command()
    async def stop(self, ctx):
        if not await self.check_channel(ctx):
            return
        player = ctx.voice_client
        if player:
            player.queue.clear()
            await player.stop()
            await ctx.approve("Stopped")
        else:
            await ctx.deny("Nothing is playing")

    @commands.command(aliases=["leave"])
    async def disconnect(self, ctx):
        if not await self.check_channel(ctx):
            return
        player = ctx.voice_client
        if player:
            await player.disconnect()
            await ctx.approve("Disconnected")
        else:
            await ctx.deny("Not connected")

    @commands.command()
    async def volume(self, ctx, vol: int = None):
        if not await self.check_channel(ctx):
            return
        player = ctx.voice_client
        if vol is None:
            return await ctx.approve(f"Volume: **{player.volume if player else 100}%**")
        if not player:
            return await ctx.deny("Not connected")
        await player.set_volume(max(0, min(vol, 100)))
        await ctx.approve(f"Volume set to **{vol}%**")

    @commands.command()
    async def loop(self, ctx, mode: str = None):
        if not await self.check_channel(ctx):
            return
        if mode not in ["off", "song", "queue"]:
            return await ctx.deny("Use `off`, `song`, or `queue`")
        self.loop_mode[ctx.guild.id] = mode
        await ctx.approve(f"Loop: **{mode}**")

    @commands.command(aliases=["q"])
    async def queue(self, ctx):
        if not await self.check_channel(ctx):
            return
        player = ctx.voice_client
        if not player or not player.current:
            return await ctx.deny("Queue is empty")
        
        desc = f"**Now:** {player.current.title}\n\n"
        for i, track in enumerate(list(player.queue)[:10], 1):
            desc += f"`{i}.` {track.title}\n"
        
        embed = discord.Embed(title="Queue", description=desc, color=0xA4EB78)
        await ctx.send(embed=embed)

    @commands.command(aliases=["np"])
    async def nowplaying(self, ctx):
        if not await self.check_channel(ctx):
            return
        player = ctx.voice_client
        if not player or not player.current:
            return await ctx.deny("Nothing is playing")

        track = player.current
        requester = self.requesters.get(ctx.guild.id, {}).get(track.identifier)

        embed = discord.Embed(color=0x2b2d31)
        embed.set_author(name="Now Playing", icon_url="https://upload.wikimedia.org/wikipedia/commons/thumb/8/84/Spotify_icon.svg/1982px-Spotify_icon.svg.png")
        desc = f"• {track.title}\n• Duration: `{format_duration(track.length)}`"
        if requester:
            desc += f" - ( {requester.mention} )"
        embed.description = desc
        if track.artwork:
            embed.set_thumbnail(url=track.artwork)

        await ctx.send(embed=embed, view=NowPlayingControls(player))

    @commands.command()
    async def shuffle(self, ctx):
        if not await self.check_channel(ctx):
            return
        player = ctx.voice_client
        if player and player.queue.count >= 2:
            player.queue.shuffle()
            await ctx.approve("Shuffled")
        else:
            await ctx.deny("Not enough songs")

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def musicchannel(self, ctx, channel: discord.TextChannel = None):
        if not channel:
            return await ctx.deny("Mention a channel")
        set_music_channel(ctx.guild.id, channel.id)
        await ctx.approve(f"Music channel set to {channel.mention}")

    @commands.command()
    @commands.is_owner()
    async def testsearch(self, ctx, *, query: str):
        """Debug command to test search"""
        results = []
        for prefix in ["ytsearch:", "scsearch:", "ytmsearch:", ""]:
            try:
                tracks = await wavelink.Playable.search(f"{prefix}{query}")
                results.append(f"`{prefix or 'default'}`: {len(tracks) if tracks else 0} results")
            except Exception as e:
                results.append(f"`{prefix or 'default'}`: Error - {str(e)[:50]}")
        await ctx.send("\n".join(results))


async def setup(bot):
    await bot.add_cog(Music(bot))
