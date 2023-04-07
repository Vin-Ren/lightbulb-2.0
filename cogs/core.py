import time
import discord
from discord.ext import commands
from discord import Embed, Status, Activity, ActivityType


def format_duration(duration: int):
    duration, seconds = divmod(duration, 60)
    if seconds == 0: return ""
    duration, minutes = divmod(duration, 60)
    if minutes == 0: return f"{seconds}s"
    duration, hours = divmod(duration, 24)
    if hours == 0: return f"{minutes}m {seconds}s"
    return f"{hours}h {minutes}m {seconds}s"


class Core(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.start = round(time.time())

    @commands.Cog.listener()
    async def on_ready(self):
        print("Connection Established.")
        print(f"{f'Connected As [{self.bot.user.name}]':^25}\n")
        await self.bot.change_presence(status=Status.online, activity=Activity(type=ActivityType.listening, name="Prefix[~]"))

    def get_info_embed(self, ctx):
        embed=Embed(title="Bot Information", color=discord.Colour.dark_blue())
        embed.add_field(name="Client Name", value=self.bot.user.name, inline=False)
        embed.add_field(name=f'Servers', value=f'Serving {len(self.bot.guilds)} servers.', inline=False)
        embed.add_field(name="Uptime", value=format_duration(round(time.time()-self.start)), inline=False)
        embed.add_field(name="Latency", value=f"{round(self.bot.latency*1000)} ms")
        embed.add_field(name="Prefix", value=f"Prefix [~]", inline=False)
        embed.set_thumbnail(url=self.bot.user.avatar.url)
        embed.set_footer(icon_url=ctx.author.avatar.url, text=f"Requested by {ctx.author.name}")
        return embed

    @commands.command(brief="Pings The Server.")
    @commands.cooldown(5, 60, commands.BucketType.channel)
    async def ping(self, ctx):
        await ctx.send(f"Pong! Latency: {round(self.bot.latency*1000)} ms")
    
    @commands.slash_command(name="ping", description="Pings the bot")
    async def slash_ping(self, ctx):
        await ctx.respond(f"Pong! Latency: {round(self.bot.latency*1000)} ms")

    @commands.command(aliases=['info'], brief="Shows Brief Information About Bot")
    @commands.cooldown(5, 60, commands.BucketType.guild)
    async def _info(self, ctx):
        embed = self.get_info_embed(ctx)
        await ctx.send(embeds=[embed])
    
    @commands.slash_command(name="botinfo", description="Gets information about bot")
    async def slash_info(self, ctx: discord.ApplicationContext):
        embed = self.get_info_embed(ctx)
        await ctx.respond(embeds=[embed])

    @commands.command(brief=f"Clears an amount of messages from the channel")
    @commands.has_permissions(manage_messages=True)
    async def clear(self, ctx, amount=5):
        await ctx.channel.purge(limit=amount)

    @ping.error
    @_info.error
    @clear.error
    async def error_handler(self, ctx, error):
        if isinstance(error, commands.BotMissingPermissions):pass
        elif isinstance(error, commands.CommandOnCooldown):await ctx.send("Command On Cooldown.")


def setup(bot):
    bot.add_cog(Core(bot))
