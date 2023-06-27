
import asyncio
import time

import discord
from discord.ext import commands, pages, bridge
from utils.downloader import YTDLSource


class QueueManager:
    def __init__(self, bot: commands.Bot, voice_channel: discord.VoiceClient, last_message: discord.Message):
        self.queue:list[YTDLSource]=[]
        self.bot=bot
        self._index=0
        self._current_vc=voice_channel
        self.last_message=last_message
        self.lock = asyncio.Lock()
    
    @property
    def index(self):
        return self._index
    
    @index.setter
    def index(self, newidx:int):
        self._index=newidx
        if (self._current_vc is None): return
        self._current_vc.stop()
        self.bot.loop.run_in_executor(None, lambda :(self.play(self._current_vc)))
    
    def get_pages(self, per_page: int = 4):
        embeds = [src.create_discord_embed() for src in self.queue]
        _pages=[]
        for i, page in enumerate(embeds):
            page.title=f"Entry#{i+1}"
        i=0
        cpage = []
        while i<len(embeds):
            cpage.append(embeds[i])
            if (i+1)%per_page==0:
                _pages.append(cpage.copy())
                cpage.clear()
            i+=1
        if len(cpage):
            _pages.append(cpage)
        if len(_pages)<=0:
            _pages.append(discord.Embed(title="The queue is empty...."))
        return _pages

    def get_paginator(self):
        page_buttons = [
            pages.PaginatorButton(
                "first", label="<<-", style=discord.ButtonStyle.green
            ),
            pages.PaginatorButton("prev", label="<-", style=discord.ButtonStyle.green),
            pages.PaginatorButton(
                "page_indicator", style=discord.ButtonStyle.gray, disabled=True
            ),
            pages.PaginatorButton("next", label="->", style=discord.ButtonStyle.green),
            pages.PaginatorButton("last", label="->>", style=discord.ButtonStyle.green),
        ]
        paginator = pages.Paginator(
            pages=self.get_pages(),
            show_disabled=True,
            show_indicator=True,
            use_default_buttons=False,
            custom_buttons=page_buttons,
            loop_pages=True,
        )
        return paginator
    
    def enqueue(self, src: YTDLSource):
        self.queue.append(src)
    
    async def add_from_url(self, url):
        while self.lock.locked():
            await asyncio.sleep(1)
        await self.lock.acquire()
        entry = await YTDLSource.from_url(url, loop=self.bot.loop, stream=True)
        self.queue.append(entry)
        self.lock.release()
        return entry
    
    def skip(self):
        self.index=self.index
    
    def reset(self):
        if (self._current_vc is not None):
            self._current_vc.stop()
        self.queue.clear()
        self.index=0
    
    async def stop(self):
        self._current_vc.stop()
    
    async def play(self, voice_client: discord.VoiceClient):
        self._current_vc=voice_client
        while self.lock.locked():
            await asyncio.sleep(1)
        while voice_client.is_connected() and self.index<len(self.queue):
            player = self.queue[self.index]
            ctx = await self.bot.get_context(self.last_message)
            embed = player.create_discord_embed(color=ctx.author.color)
            embed.title=embed.title+f" ({self.index+1} of {len(self.queue)})"
            await ctx.send(embed=embed)
            voice_client.play(player, after=lambda e: print(f"Player error: {e}") if e else None)
            while voice_client.is_playing():
                await asyncio.sleep(1)
            self.index+=1


class MusicQueue(commands.Cog):
    def __init__(self, bot_: commands.Bot):
        self.bot = bot_
        self.queue_managers: dict[int, QueueManager] = {}
    
    async def get_guild_queue_manager(self, ctx: commands.Context):
        if (self.queue_managers.get(ctx.guild.id) is None):
            if (ctx.author.voice is None):
                await ctx.send("You are not connected to a voice channel.")
                raise commands.CommandError("Author not connected to a voice channel.")
            self.queue_managers[ctx.guild.id] = QueueManager(self.bot, ctx.author.voice.channel, ctx.message)
        self.queue_managers[ctx.guild.id].last_message=ctx.message
        return self.queue_managers[ctx.guild.id]

    @commands.command(aliases=['showq'])
    async def show_queue(self, ctx: commands.Context):
        nctx = bridge.BridgeExtContext(message=ctx.message, bot=self.bot, view=ctx.view)
        qm = await self.get_guild_queue_manager(ctx)
        paginator = qm.get_paginator()
        await paginator.respond(nctx)
    
    @commands.slash_command(name='showq')
    async def slash_show_queue(self, ctx: discord.ApplicationContext):
        "Shows queue"
        qm = await self.get_guild_queue_manager(ctx)
        paginator = qm.get_paginator()
        await paginator.respond(ctx.interaction)
    
    @commands.command(aliases=['mq'])
    async def multi_queue(self, ctx: commands.Context, *, url:str):
        "Adds multiple item to the queue, seperated by commas [,]"
        qm = await self.get_guild_queue_manager(ctx)
        with ctx.typing():
            for name in url.split(','):
                entry = await qm.add_from_url(name)
                embed = entry.create_discord_embed()
                embed.title="Added entry"
                await ctx.send(embed=embed)

    @commands.command(aliases=['eq'])
    async def enqueue(self, ctx: commands.Context, *, url: str):
        "Adds the entry to the queue"
        qm = await self.get_guild_queue_manager(ctx)
        with ctx.typing():
            entry = await qm.add_from_url(url)
        embed = entry.create_discord_embed()
        embed.title="Added entry"
        await ctx.send(embed=embed)
    
    @commands.slash_command(name='enqueue')
    @discord.option("url", description="Url or query of the source")
    async def slash_enqueue(self, ctx: discord.ApplicationContext, url: str):
        "Adds the entry to the queue"
        qm = await self.get_guild_queue_manager(ctx)
        response = await ctx.respond(content="Processing request...")
        with ctx.typing():
            entry = await qm.add_from_url(url)
            embed = entry.create_discord_embed()
            embed.title="Added entry"
            await response.edit_original_response(content="", embeds=[embed])
    
    @commands.command(aliases=['pq', 'playq'])
    async def play_queue(self, ctx: commands.Context):
        "Starts queue playback"
        qm = await self.get_guild_queue_manager(ctx)
        if len(qm.queue) <=0:
            await ctx.send("The queue is empty.")
            return
        await qm.play(ctx.voice_client)
    
    @commands.slash_command(name='playqueue')
    async def slash_play_queue(self, ctx: discord.ApplicationContext):
        "Adds the entry to the queue"
        qm = await self.get_guild_queue_manager(ctx)
        if len(qm.queue)<=0:
            await ctx.respond(content="The queue is empty.")
            return
        await ctx.respond(content="Starting queue playback...")
        await qm.play(ctx.voice_client)
    
    @commands.command(aliases=['rep', 'replay'])
    async def replay_queue(self, ctx: commands.Context):
        "Replays the queue from the beginning"
        qm = await self.get_guild_queue_manager(ctx)
        if len(qm.queue)<=0:
            await ctx.respond(content="The queue is empty.")
            return
        qm.index=0
    
    @commands.slash_command(name='replayqueue')
    async def slash_play_queue(self, ctx: discord.ApplicationContext):
        "Replays the queue from the beginning"
        qm = await self.get_guild_queue_manager(ctx)
        if len(qm.queue)<=0:
            await ctx.respond(content="The queue is empty.")
            return
        await ctx.respond(content="Starting queue replay...")
        qm.index=0
    
    @commands.command(aliases=['sk', 'skp', 'skip'])
    async def skip_queue_entry(self, ctx: commands.Context):
        "Skips current entry"
        qm = await self.get_guild_queue_manager(ctx)
        await ctx.send("Skipping current entry...")
        qm.skip()
    
    @commands.slash_command(name='replayqueue')
    async def slash_skip_queue_entry(self, ctx: discord.ApplicationContext):
        "Skips current entry"
        qm = await self.get_guild_queue_manager(ctx)
        await ctx.respond(content="Skipping current entry...")
        qm.skip()
    
    @commands.command(aliases=['cq', 'clearq'])
    async def clear_queue(self, ctx: commands.Context):
        "Clears queue"
        qm = await self.get_guild_queue_manager(ctx)
        qm.reset()
        await ctx.send("Cleared queue")
    
    @commands.slash_command(name='clearqueue')
    async def slash_skip_queue_entry(self, ctx: discord.ApplicationContext):
        "Clears queue"
        qm = await self.get_guild_queue_manager(ctx)
        qm.reset()
        await ctx.respond(content="Cleared queue")
    
    @commands.command(aliases=['sq', 'stopq'])
    async def stop_queue(self, ctx: commands.Context):
        "Stops queue playing session"
        qm = await self.get_guild_queue_manager(ctx)
        await qm.stop()
        await ctx.send("Stopped queue playback")
    
    @commands.slash_command(name='clearqueue')
    async def slash_skip_queue_entry(self, ctx: discord.ApplicationContext):
        "Stops queue playing session"
        qm = await self.get_guild_queue_manager(ctx)
        await qm.stop()
        await ctx.respond(content="Stopped queue playback")
    
    @slash_play_queue.before_invoke
    @play_queue.before_invoke
    async def ensure_clean_voice(self, ctx: commands.Context):
        if ctx.voice_client is None:
            if ctx.author.voice:
                await ctx.author.voice.channel.connect()
                await ctx.guild.change_voice_state(channel=ctx.author.voice.channel, self_mute=False, self_deaf=True)
            else:
                await ctx.send("You are not connected to a voice channel.")
                raise commands.CommandError("Author not connected to a voice channel.")
        elif ctx.voice_client.is_playing():
            ctx.voice_client.stop()


class Music(commands.Cog):
    def __init__(self, bot_: commands.Bot):
        self.bot = bot_
        self.auto_disconnect_timeout = 15*60
        self.task_interval = 60
        self.last_timeout = {}
        self.bg_tasks = [self.bot.loop.create_task(self.auto_disconnect_task())]

    async def disconnect_vcs(self):
        await self.bot.wait_until_ready()
        curr_time = time.time()
        timed_out_ctxs = []
        for gid, (ctx, timeout_at) in self.last_timeout.items():
            if timeout_at<curr_time:
                timed_out_ctxs.append((gid, ctx))
        
        for gid, ctx in timed_out_ctxs:
            self.last_timeout.pop(gid)
            if ctx.voice_client is None or ctx.voice_client.is_playing(): 
                continue
            await ctx.send("Automatically disconnected from voice.")
            await ctx.voice_client.disconnect(force=True)
    
    async def auto_disconnect_task(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            await self.disconnect_vcs()
            await asyncio.sleep(self.task_interval)

    @commands.command()
    async def join(self, ctx: commands.Context, *, channel: discord.VoiceChannel):
        """Joins a voice channel"""

        if ctx.voice_client is not None:
            return await ctx.voice_client.move_to(channel)

        await channel.connect()
    
    @commands.command(aliases=['play', 'p'])
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
    @discord.option("url", description="Url or query of the source")
    @discord.option("ephemeral", choices=["Normal", "Ephemeral"], default="Normal", description="Message visible only for you", required=False)
    async def slash_stream(self, ctx: discord.ApplicationContext, url: str, ephemeral: str):
        """Streams audio from a url or query"""
        ephemeral_ = (ephemeral == 'Ephemeral')
        response = await ctx.respond(content="Processing request...", ephemeral=ephemeral_)
        
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
    async def ensure_clean_voice(self, ctx: commands.Context):
        if ctx.voice_client is None:
            if ctx.author.voice:
                await ctx.author.voice.channel.connect()
                await ctx.guild.change_voice_state(channel=ctx.author.voice.channel, self_mute=False, self_deaf=True)
            else:
                await ctx.send("You are not connected to a voice channel.")
                raise commands.CommandError("Author not connected to a voice channel.")
        elif ctx.voice_client.is_playing():
            ctx.voice_client.stop()
    
    @slash_stream.after_invoke
    @stream.after_invoke
    async def update_disconnect_timeout(self, ctx: commands.Context):
        _id = ctx.guild.id if ctx.guild else 0
        self.last_timeout[_id] = (ctx, time.time()+self.auto_disconnect_timeout)
    
    @slash_stream.error
    async def handle_slash_stream_error(self, ctx, *_):
        await ctx.respond("Something went wrong.")
    
    @stream.error
    async def handle_stream_error(self, ctx, *_):
        await ctx.send("Something went wrong.")


def setup(bot):
    bot.add_cog(Music(bot))
    bot.add_cog(MusicQueue(bot))
