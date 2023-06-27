import asyncio
import yt_dlp
import discord
import json

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
        embed.add_field(name="Title", value=f'{self.data["title"]} [🔗 Link]({self.data["webpage_url"]})')
        embed.add_field(name="Uploader", value=self.data["uploader"])
        embed.add_field(name="Duration", value=self.humanized_data['duration'])
        embed.add_field(name="Views", value=self.humanized_data['views'])
        embed.add_field(name="Likes", value=self.humanized_data['likes'])
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
