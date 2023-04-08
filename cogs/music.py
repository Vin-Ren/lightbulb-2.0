
import asyncio
import yt_dlp

import discord
from discord.ext import commands

# Suppress noise about console usage from errors
yt_dlp.utils.bug_reports_message = lambda: ""


ytdl_format_options = {
    "format": "bestaudio/best",
    "outtmpl": "%(extractor)s-%(id)s-%(title)s.%(ext)s",
    "restrictfilenames": True,
    "noplaylist": True,
    "nocheckcertificate": True,
    "ignoreerrors": False,
    "logtostderr": False,
    "quiet": True,
    "no_warnings": True,
    "default_search": "auto",
    "source_address": (
        "0.0.0.0"
    ),  # Bind to ipv4 since ipv6 addresses cause issues at certain times
}

ffmpeg_options = {
    'options': '-vn',
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5"
}

ytdl = yt_dlp.YoutubeDL(ytdl_format_options)


class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source: discord.AudioSource, *, data: dict, volume: float = 0.5):
        super().__init__(source, volume)

        self.data = data

        self.title = data.get("title")
        self.url = data.get("url")
        self.humanized_data = {'duration': self.format_duration(data.get('duration', -1)), 
                               'views': self.format_numbers(data.get('view_count', -1)), 
                               'likes': self.format_numbers(data.get('like_count', -1))}
    
    def create_discord_embed(self, **kwargs):
        embed = discord.Embed(title="Now playing", **kwargs)
        embed.add_field(name="Title", value=f'{self.data["title"]}\n[🔗 Link]({self.data["webpage_url"]})', inline=False)
        embed.add_field(name="Uploader", value=self.data["uploader"], inline=True)
        embed.add_field(name="Duration", value=self.humanized_data['duration'], inline=False)
        embed.add_field(name="Stats", value=f"Views: {self.humanized_data['views']}\nLikes: {self.humanized_data['likes']}")
        embed.set_thumbnail(url=self.data["thumbnail"])
        return embed
    
    @staticmethod
    def format_duration(duration: int):
        if duration == -1: return 'Unknown'
        duration, seconds = divmod(duration, 60)
        if seconds == 0:
            return "LIVE"
        duration, minutes = divmod(duration, 60)
        if minutes == 0: return f"{seconds}s"
        duration, hours = divmod(duration, 24)
        if hours == 0: return f"{minutes}m {seconds}s"
        return f"{hours}h {minutes}m {seconds}s"
    
    @staticmethod
    def format_numbers(number: int):
        if number == -1: return 'Unknown'
        thousands, ones = divmod(number, 1000)
        if thousands == 0:
            return f"{ones}"
        mils, thousands = divmod(thousands, 1000)
        if mils == 0:
            return f"{thousands}K"
        bils, mils = divmod(mils, 1000)
        if bils == 0:
            hundred_thousands, thousands = divmod(thousands, 100)
            return f"{mils}M" if hundred_thousands == 0 else f"{mils}.{hundred_thousands}M"
        hundred_mils, mils = divmod(mils, 100)
        return f"{bils}B" if hundred_mils == 0 else f"{bils}.{hundred_mils}B"

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=False):
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(
            None, lambda: ytdl.extract_info(url, download=not stream)
        )

        if "entries" in data:
            # Takes the first item from a playlist
            data = data["entries"][0]

        filename = data["url"] if stream else ytdl.prepare_filename(data)
        return cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data=data)


class Music(commands.Cog):
    def __init__(self, bot_: commands.Bot):
        self.bot = bot_
        self.auto_voice_disconnect_timeout = 15*60
        self.connected_voice = {}

    @commands.command()
    async def join(self, ctx: commands.Context, *, channel: discord.VoiceChannel):
        """Joins a voice channel"""

        if ctx.voice_client is not None:
            return await ctx.voice_client.move_to(channel)

        await channel.connect()

    @commands.command(aliases=['play'])
    async def stream(self, ctx: commands.Context, *, url: str):
        """Streams audio from a url or query"""

        msg = await ctx.send(f"Processing request...")
        
        async with ctx.typing():
            player = await YTDLSource.from_url(url, loop=self.bot.loop, stream=True)
            ctx.voice_client.play(player, after=lambda e: print(f"Player error: {e}") if e else None)
        
        embed = player.create_discord_embed(color=ctx.author.color)
        
        await msg.edit(content="", embeds=[embed])
        await asyncio.sleep(player.data["duration"])
        await msg.edit(content="Finished playing.", embeds=[embed])
    
    @commands.slash_command(name='play')
    async def slash_stream(self, ctx: discord.ApplicationContext, url: str):
        """Streams audio from a url or query"""
        response = await ctx.respond(content="Processing request...")
        
        player = await YTDLSource.from_url(url, loop=self.bot.loop, stream=True)
        ctx.voice_client.play(player, after=lambda e: print(f"Player error: {e}") if e else None)
        
        embed = player.create_discord_embed(color=ctx.author.color)
        
        await response.edit_original_response(content="", embeds=[embed])
        await asyncio.sleep(player.data["duration"])
        await response.edit_original_response(content="Finished playing.", embeds=[embed])

    @commands.command()
    async def volume(self, ctx: commands.Context, volume: int):
        """Changes the player's volume"""

        if ctx.voice_client is None:
            return await ctx.send("Not connected to a voice channel.")

        ctx.voice_client.source.volume = volume / 100
        await ctx.send(f"Changed volume to {volume}%")

    @commands.command()
    async def stop(self, ctx: commands.Context):
        """Stops and disconnects the bot from voice"""

        await ctx.voice_client.disconnect(force=True)

    @slash_stream.before_invoke
    @stream.before_invoke
    async def ensure_voice(self, ctx: commands.Context):
        if ctx.voice_client is None:
            if ctx.author.voice:
                await ctx.author.voice.channel.connect()
            else:
                await ctx.send("You are not connected to a voice channel.")
                raise commands.CommandError("Author not connected to a voice channel.")
        elif ctx.voice_client.is_playing():
            ctx.voice_client.stop()
    
    @slash_stream.after_invoke
    @stream.after_invoke
    async def auto_disconnect_voice(self, ctx: commands.Context):
        await asyncio.sleep(self.auto_voice_disconnect_timeout)
        
        if ctx.voice_client is None or ctx.voice_client.is_playing():
            return
        
        if isinstance(ctx, discord.ApplicationContext):
            await ctx.followup.send("Automatically disconnected from voice.")
        else:
            await ctx.send("Automatically disconnected from voice.")
        await ctx.voice_client.disconnect(force=True)
    
    @slash_stream.error
    async def handle_slash_stream_error(self, ctx, *_):
        await ctx.respond("Something went wrong.")
    
    @stream.error
    async def handle_stream_error(self, ctx, *_):
        await ctx.send("Something went wrong.")


def setup(bot):
    bot.add_cog(Music(bot))
