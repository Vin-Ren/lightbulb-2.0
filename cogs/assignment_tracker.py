import asyncio
from datetime import datetime, timedelta, timezone
import json
from typing import Literal

import traceback

import discord
from discord.ext import commands, tasks
import humanize
import humanize.lists

from bot import Bot


SAVE_FILENAME = "assignments.json"
DATETIME_FORMAT = "%d-%mT%H:%M%z"


def timedelta_to_human(td: timedelta) -> str:
    """Convert a timedelta to a human-readable string like '2 weeks 3 days 5 hours 10 minutes 30 seconds left'."""
    weeks, remainder = divmod(td.total_seconds(), 604800)  # 1 week = 604800 seconds
    days, remainder = divmod(remainder, 86400)   # 1 day = 86400 seconds
    hours, remainder = divmod(remainder, 3600)   # 1 hour = 3600 seconds
    minutes, seconds = divmod(remainder, 60)     # 1 minute = 60 seconds

    # Helper function to handle pluralization
    def format_unit(value, unit):
        if value == 1:
            return f"{int(value)} {unit}"  # Singular (e.g., "1 day")
        elif value > 1:
            return f"{int(value)} {unit}s"  # Plural (e.g., "2 days")
        return None  # Skip if 0

    # Dynamically construct the output
    parts = filter(None, [
        format_unit(weeks, "week"),
        format_unit(days, "day"),
        format_unit(hours, "hour"),
        format_unit(minutes, "minute"),
        format_unit(seconds, "second")
    ])

    return " ".join(parts) + " left"


# Helper function to format assignments
def format_assignment(assignment, status_emoji, now: datetime = datetime.now(tz=timezone.utc), completed=True):
    deadline_str = assignment.deadline.strftime("%A, %d %B %Y at %I:%M %p")
    time_left = timedelta_to_human(assignment.deadline - now)

    text = (
        f"📂 **Subject:** {humanize.natural_list(assignment.groups)}\n"
        f"⏳ **Deadline:** {deadline_str}\n"
    )
    if status_emoji!="🕒":
        text+=f"⚡ **{time_left} remaining!**"
    elif completed:
        text+=f"✅ **Completed**"
    else:
        text+=f"🚨 **Missed Deadline**"
    if assignment.link:
        text += f"\n🔗 **[Resource]({assignment.link})**"
    return f"{status_emoji} **{assignment.name} (#{assignment.id})**\n{text}\n"


def get_toggle_message(feature_name: str, is_enabled: bool):
    status = "✅ Enabled" if is_enabled else "❌ Disabled"
    color = discord.Color.green() if is_enabled else discord.Color.red()

    embed = discord.Embed(
        title=f"🔧 {feature_name} Toggle",
        description=f"Current Status: **{status}**\nUse the command again to toggle.",
        color=color
    )

    return embed


class Assignment:
    def __init__(self, _id: str, name: str, groups: str, deadline: datetime, link: str):
        self.id = str(_id)
        self.name = name
        self.groups = groups
        self.deadline = deadline
        self.link = link
    
    def __str__(self):
        return f"[#{self.id}] {','.join(self.groups)} - {self.name}. Deadline: {self.deadline.strftime('%a %H:%M, %d %b %y')}"

    def get_relative_date(self):
        # TODO: fix
        return humanize.naturaltime(self.deadline)
    
    def get_embed(self):
        embed = discord.Embed(
            title=f"📌 Assignment: {self.name} (#{self.id})",  # ID now looks cleaner
            color=discord.Color.blue()  # Change color if needed
        )

        # Assigned Groups (Handles empty case)
        assigned_groups = ", ".join(self.groups) if self.groups else "*No groups assigned*"
        embed.add_field(name="📂 **Assigned Groups**", value=assigned_groups, inline=False)

        # Deadline Formatting
        time_left = timedelta_to_human(self.deadline - datetime.now(tz=timezone.utc))
        deadline_str = self.deadline.strftime("%A, %d %B %Y at %I:%M %p")  # Example: Monday, 10 March 2025 at 11:59 PM
        embed.add_field(name="⏳ **Deadline**", value=f"🕒 {deadline_str}\n⚡ **{time_left} remaining!**", inline=False)

        # Optional Link (Only added if present)
        if self.link:
            embed.add_field(name="🔗 **Assignment Link**", value=f"[Click here]({self.link})", inline=False)

        # Footer with an Icon
        embed.set_footer(text="⚡ Stay on top of your assignments!", icon_url="https://cdn-icons-png.flaticon.com/512/1828/1828640.png")

        return embed
    
    @classmethod
    def from_dict(cls, data: dict):
        return cls(data['id'], data['name'], data['groups'], datetime.fromisoformat(data['deadline']), data['link'])
    
    def to_dict(self):
        return {'id': self.id, 'name': self.name, 'groups': self.groups, 'deadline': self.deadline.isoformat(), 'link': self.link}


class ServerAssignmentManager:
    def __init__(self, server_id: str, announcer_channel_id: str, tracked_since: datetime = None):
        self.tracked_since = tracked_since if tracked_since else datetime.now()
        self.server_id = server_id
        self.announcer_channel_id = announcer_channel_id
        self.dashboard_message_id = ""
        self.assignments: dict[str, Assignment] = dict()
        self.past_assignments: dict[str, Assignment] = dict()
        self.groups: set[str] = set()
        self.subscriptions: dict[str, set[str]] = dict() # {user: [groups]}
        self.subscribers: dict[str, set[str]] = dict() # {group: [users]}
        self.group_assignments: dict[str, set[str]] = dict() # {group: [assigments]}
        self.user_checklist: dict[str, set[str]] = dict() # {user: [assignments]}
        self.last_assignment_id = 0
        self.disable_dashboard = True
    
    @classmethod
    def from_dict(cls, data: dict):
        obj = cls(data['server_id'], data['announcer_channel_id'], datetime.fromisoformat(data['tracked_since']))
        obj.dashboard_message_id = data['dashboard_message_id']
        obj.assignments = {_id: Assignment.from_dict(entry) for _id, entry in data['assignments'].items()}
        obj.past_assignments = {_id: Assignment.from_dict(entry) for _id, entry in data['past_assignments'].items()}
        obj.groups = set(data['groups'])
        obj.subscriptions = {user: set(entry) for user, entry in data['subscriptions'].items()}
        obj.subscribers = {group: set(entry) for group, entry in data['subscribers'].items()}
        obj.group_assignments = {group: set(entry) for group, entry in data['group_assignments'].items()}
        obj.user_checklist = {user: set(entry) for user, entry in data['user_checklist'].items()}
        obj.last_assignment_id = data['last_assignment_id']
        obj.disable_dashboard = data['disable_dashboard']
        return obj
    
    def to_dict(self):
        return {
            'tracked_since': self.tracked_since.isoformat(),
            'server_id': self.server_id,
            'announcer_channel_id': self.announcer_channel_id,
            'dashboard_message_id': self.dashboard_message_id,
            'assignments': {_id: assignment.to_dict() for _id, assignment in self.assignments.items()},
            'past_assignments': {_id: assignment.to_dict() for _id, assignment in self.past_assignments.items()},
            'groups': list(self.groups),
            'subscriptions': {user: list(groups) for user, groups in self.subscriptions.items()},
            'subscribers': {group: list(users) for group, users in self.subscribers.items()},
            'group_assignments': {group: list(assignment_id) for group, assignment_id in self.group_assignments.items()},
            'user_checklist': {user: list(assignment_id) for user, assignment_id in self.user_checklist.items()},
            'last_assignment_id': self.last_assignment_id,
            'disable_dashboard': self.disable_dashboard
        }
    
    def create_group(self, group_name: str):
        group_name = group_name.upper()
        if group_name in self.groups:
            return False
        self.groups.add(group_name)
        self.subscribers[group_name] = set()
        self.group_assignments[group_name] = set()
        return True
    
    def delete_group(self, group_name: str):
        group_name = group_name.upper()
        if group_name not in self.groups:
            return False
        
        self.groups.remove(group_name)
        self.subscribers.pop(group_name)
        
        for user in self.subscriptions.keys():
            if group_name in self.subscriptions[user]:
                self.subscriptions[user].remove(group_name)
        
        for assignment_id in self.group_assignments[group_name]:
            self.assignments[assignment_id].groups.remove(group_name)
        return True
    
    def get_subscribed(self, user_id: str):
        return self.subscriptions.get(user_id, set())
    
    def subscribe(self, user_id: str, group_name: str):
        group_name = group_name.upper()
        if group_name not in self.groups:
            return False
        if user_id in self.subscribers[group_name]:
            return False
        
        self.subscribers[group_name].add(user_id)
        
        if self.subscriptions.get(user_id) == None:
            self.subscriptions[user_id] = set()
        self.subscriptions[user_id].add(group_name)
        return True
    
    def unsubscribe(self, user_id: str, group_name: str):
        group_name = group_name.upper()
        if group_name not in self.groups:
            return False
        if user_id not in self.subscriptions:
            return False
        self.subscriptions[user_id].remove(group_name)
        self.subscribers[group_name].remove(user_id)
        return True

    def get_all_assignments(self):
        return sorted([assignment for assignment in self.assignments.values()], key=lambda e: e.deadline)
    
    def get_personal_assignments(self, user_id: str, include_completed: bool = True):
        assignment_ids = set()
        for group in self.subscriptions.get(user_id,[]):
            assignment_ids.update(self.group_assignments[group])
        if not include_completed:
            assignment_ids-=self.user_checklist.get(user_id, set())
        return sorted([self.assignments[_id] for _id in assignment_ids], key=lambda e: e.deadline)

    def checklist_assignment(self, user_id: str, assignment_id: str):
        user_id = str(user_id)
        assignment_id = str(assignment_id)
        if assignment_id not in self.assignments:
            return False
        self.user_checklist[user_id] = self.user_checklist.get(user_id, set())
        if assignment_id in self.user_checklist[user_id]:
            return False
        self.user_checklist[user_id].add(assignment_id)
        return True

    def unchecklist_assignment(self, user_id: str, assignment_id: str):
        user_id = str(user_id)
        assignment_id = str(assignment_id)
        self.user_checklist[user_id] = self.user_checklist.get(user_id, set())
        if assignment_id not in self.user_checklist[user_id]:
            return False
        self.user_checklist[user_id].remove(assignment_id)
        return True
    
    def create_assignment(self, name: str, groups: str, deadline: str, link: str):
        groups = groups.upper().split(',')
        self.last_assignment_id+=1
        assignment = Assignment(_id=self.last_assignment_id, name=name, groups=groups, deadline=datetime.strptime(deadline, DATETIME_FORMAT), link=link)
        # assume this assignment's deadline is within this year
        assignment.deadline = assignment.deadline.replace(year=datetime.now().year) 
        if len(assignment.link) and not assignment.link.startswith('http'):
            assignment = 'https://'+assignment
        for group in groups:
            self.group_assignments[group].add(assignment.id)
        self.assignments[assignment.id] = assignment
        return assignment
        # self.assignments.sort(key=lambda assignment: assignment.deadline) # Sorts by deadline
    
    def edit_assignment(self, assignment_id: str, field_name: Literal['name', 'deadline', 'groups', 'link'], value: str):
        if assignment_id not in self.assignments:
            return False
        assignment = self.assignments[assignment_id]
        if field_name == 'name':
            assignment.name = value
        elif field_name == 'deadline':
            newDeadline = datetime.strptime(value, DATETIME_FORMAT)
            newDeadline = newDeadline.replace(year=datetime.now().year)
            assignment.deadline = newDeadline
        elif field_name == 'groups':
            groups = value.upper().split(',')
            for group in self.assignments[assignment_id].groups:
                self.group_assignments[group].remove(assignment_id)
            for group in groups:
                self.group_assignments[group].add(assignment.id)
        elif field_name == 'link':
            if not value.startswith('http'):
                value = 'https://'+value
            assignment.link = value
        else:
            return False
        return True
    
    def delete_assignment(self, assignment_id: str):
        if assignment_id not in self.assignments:
            return
        for group in self.assignments[assignment_id].groups:
            self.group_assignments[group].remove(assignment_id)
        return self.assignments.pop(assignment_id)

    def archive_assignment(self, assignment_id: str):
        if assignment_id not in self.assignments:
            return False
        assignment = self.assignments[assignment_id]
        self.delete_assignment(assignment_id)
        self.past_assignments[assignment_id]=assignment
    
    def get_all_assignments_embed(self):
        now = datetime.now(tz=timezone.utc)

        # Categorize assignments
        active_assignments = list(self.assignments.values())  # Assignments still due
        past_assignments = list(self.past_assignments.values())  # Assignments past deadline

        # Determine urgency color (based on most urgent active assignment)
        most_urgent_time = timedelta.max if active_assignments else timedelta(days=1000)
        for assignment in active_assignments:
            time_remaining = assignment.deadline - now
            if time_remaining < most_urgent_time:
                most_urgent_time = time_remaining

        embed_color = (
            discord.Color.red() if most_urgent_time <= timedelta(hours=24) else
            discord.Color.orange() if most_urgent_time <= timedelta(days=3) else
            discord.Color.green()
        )

        # Create embed
        embed = discord.Embed(
            title="📚 All Assignments Overview",
            description="Here's the status of all assignments!",
            color=embed_color
        )

        # Add active assignments
        if active_assignments:
            embed.add_field(
                name="📌 **Active Assignments**",
                value="\n".join(format_assignment(a, "📌", now) for a in active_assignments),
                inline=False
            )

        # Add past assignments
        if past_assignments:
            embed.add_field(
                name="🕒 **Past Assignments**",
                value="\n".join(format_assignment(a, "🕒", completed=False) for a in past_assignments),
                inline=False
            )

        # Footer
        embed.set_footer(text="⚡ Stay organized and submit on time!", icon_url="https://cdn-icons-png.flaticon.com/512/1828/1828640.png")

        return embed

    def get_personal_assignments_embed(self, user_id: str, include_completed=False):
        user_id = str(user_id)
        now = datetime.now(tz=timezone.utc)  

        # Assignments categorization
        active_assignments = []
        completed_assignments = []
        past_assignments = list(self.past_assignments.values())  # Already completed & past deadline

        # Split active & completed
        for assignment in self.get_personal_assignments(user_id, include_completed=include_completed):
            if str(assignment.id) in self.user_checklist.get(user_id, set()):
                completed_assignments.append(assignment)
            else:
                active_assignments.append(assignment)

        # Determine urgency color
        most_urgent_time = timedelta.max if active_assignments else timedelta(days=1000)
        for assignment in active_assignments:
            time_remaining = assignment.deadline - now
            if time_remaining < most_urgent_time:
                most_urgent_time = time_remaining

        embed_color = (
            discord.Color.red() if most_urgent_time <= timedelta(hours=24) else
            discord.Color.orange() if most_urgent_time <= timedelta(days=3) else
            discord.Color.green()
        )

        # Create embed
        embed = discord.Embed(
            title="📚 Assignments Overview",
            description="Here's your assignment breakdown! ⚡",
            color=embed_color
        )

        # Add active assignments
        if active_assignments:
            embed.add_field(name="📌 **Active Assignments**", value="\n".join(format_assignment(a, "📌", now) for a in active_assignments), inline=False)

        # Add completed assignments
        if include_completed and completed_assignments:
            embed.add_field(name="✅ **Completed Assignments**", value="\n".join(format_assignment(a, "✅", now) for a in completed_assignments), inline=False)

        # Add past assignments
        if past_assignments:
            embed.add_field(name="🕒 **Past Assignments**", value="\n".join(format_assignment(a, "🕒", completed=True) for a in past_assignments), inline=False)

        # Footer
        embed.set_footer(text="⚡ Stay organized and submit on time!", icon_url="https://cdn-icons-png.flaticon.com/512/1828/1828640.png")

        return embed

    
    def get_dashboard_message(self):
        assignments_sorted_by_deadline = sorted([e for e in self.assignments.values()], key=lambda e:e.deadline)
        dashboard_message = "## 📚 **Active Assignments**"
        critical_time = False
        for assignment in assignments_sorted_by_deadline:
            timeleft = assignment.deadline-datetime.now(tz=timezone.utc)
            timeleft_str = timedelta_to_human(timeleft)
            if (timeleft<timedelta(days=1)):
                timeleft_str = f"⚠️ **{timeleft_str[:-5]} LEFT!** "
                critical_time = True
            current_section = [f"📝 **Assignment {assignment.name}**",
                               f"📂 *Subject:* {humanize.lists.natural_list(assignment.groups)}",
                               f"⏳ *Deadline:* {assignment.deadline.strftime('%A, %d %B %Y at %I:%M %p')}",
                               f"⏲ *Time Left:* {timeleft_str}"]
            current_section_str = '\n'.join(current_section)
            dashboard_message+='\n\n═══════════════════════\n'+current_section_str

        if critical_time:
            dashboard_message+="\n\n\n⚠️ **Note:** Assignments with less than **1 day** left are marked as ⚠️ **URGENT!**"
        return dashboard_message

    def toggle_dashboard(self):
        self.disable_dashboard^=1


class AssignmentTracker(commands.Cog):
    def __init__(self, bot_: Bot):
        self.bot = bot_
        self.assignments_by_server: dict[str, ServerAssignmentManager] = {}
        self.load()
    
    @commands.Cog.listener('on_ready')
    async def _init_tasks(self):
        self.autosave_data.start()
        self.auto_archive_assignments.start()
        self.refresh_dashboard.start()
        self.synchronize_dashboard.start()
    
    @tasks.loop(minutes=15)
    async def autosave_data(self):
        self.save()
    
    @tasks.loop(minutes=30)
    async def auto_archive_assignments(self):
        # print(f"Archiving now... {datetime.now().isoformat()}")
        for manager in self.assignments_by_server.values():
            archivable_ids = []
            for assignment in manager.assignments.values():
                if assignment.deadline.timestamp() < datetime.now().timestamp():
                    archivable_ids.append(assignment.id)
            
            # print("archiving", archivable_ids, "for", manager.server_id)
            for _id in archivable_ids:
                manager.archive_assignment(_id)
        self.save()
    
    @tasks.loop(hours=24)
    async def refresh_dashboard(self):
        # print(f"Refreshing dashboard... {datetime.now().isoformat()}")
        try:
            for manager in self.assignments_by_server.values():
                try:
                    if manager.disable_dashboard:
                        continue
                    channel = self.bot.get_channel(int(manager.announcer_channel_id))
                    if channel is None:
                        continue
                    if manager.dashboard_message_id!="":
                        message = await channel.fetch_message(int(manager.dashboard_message_id))
                        if message is not None:
                            await message.delete()
                except (discord.errors.NotFound, ValueError):
                    pass
        except RuntimeError:
            traceback.print_exc()
    
    @tasks.loop(seconds=5)
    async def synchronize_dashboard(self):
        # print(f"Synchronizing dashboard... {datetime.now().isoformat()}")
        try:
            for manager in self.assignments_by_server.values():
                try:
                    if manager.disable_dashboard:
                        continue
                    channel = self.bot.get_channel(int(manager.announcer_channel_id))
                    if channel is None:
                        continue
                    message = await channel.fetch_message(int(manager.dashboard_message_id))
                    if message is not None:
                        await message.edit(content=manager.get_dashboard_message())
                        # await message.edit(embed=manager.get_assignments_embed())
                except (discord.errors.NotFound, ValueError):
                    manager.dashboard_message_id = ""
                    await self.fix_dashboard_message(manager.server_id)
        except RuntimeError:
            traceback.print_exc()
    
    async def fix_dashboard_message(self, server_id: str):
        manager = self.get_manager(server_id)
        if manager.disable_dashboard and manager.dashboard_message_id:
            channel = self.bot.get_channel(int(manager.announcer_channel_id))
            if channel is None:
                return
            if manager.dashboard_message_id != "":
                try:
                    message = await channel.fetch_message(int(manager.dashboard_message_id))
                    if message is not None:
                        await message.delete()
                except:
                    pass
        elif not manager.disable_dashboard and not manager.dashboard_message_id:
            channel = self.bot.get_channel(int(manager.announcer_channel_id))
            if channel is None:
                return
            msg = await channel.send(content=manager.get_dashboard_message())
            manager.dashboard_message_id = msg.id
    
    def load(self):
        try: 
            with open(SAVE_FILENAME, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # print(f"{data=}")
                self.assignments_by_server = {server_id: ServerAssignmentManager.from_dict(entry) for server_id, entry in data.items()}
                assert(list(self.assignments_by_server.values())[0].groups.__contains__('ALIN'))
        except:
            pass
    
    def save(self):
        try: 
            with open(SAVE_FILENAME, 'w', encoding='utf-8') as f:
                data = {server_id: manager.to_dict() for server_id, manager in self.assignments_by_server.items()}
                json.dump(data, f, indent=4)
        except:
            pass
    
    def get_manager(self, guild_id: str):
        return self.assignments_by_server[str(guild_id)]
    
    @staticmethod
    def has_been_setup():
        async def predicate(ctx: commands.Context):
            return str(ctx.guild.id) in ctx.cog.assignments_by_server
        return commands.check(predicate)
    
    @commands.command(aliases=['trackerchannel', 'setup'])
    async def bind_tracker_announcer_channel(self, ctx: commands.Context, channel: discord.TextChannel = None):
        """Setup and sets a tracker channel for dashboard and reminders."""
        if channel==None:
            channel = ctx.channel
        if str(ctx.guild.id) not in self.assignments_by_server:
            self.assignments_by_server[str(ctx.guild.id)] = ServerAssignmentManager(ctx.guild.id, channel.id)
            await ctx.send(f"Successfully setup tracker and set <#{channel.id}> as an announcer channel.")
        else:
            self.assignments_by_server[str(ctx.guild.id)].announcer_channel_id=channel.id
            await ctx.send(f"Successfully set <#{channel.id}> as an announcer channel.")
    
    @commands.command(aliases=['listgroups'])
    @has_been_setup()
    async def list_groups(self, ctx: commands.Context):
        """Lists all group"""
        manager = self.get_manager(ctx.guild.id)
        groups_str = "\n".join([str(idx+1)+". "+str(group) for idx, group in enumerate(manager.groups)])
        await ctx.send(f"Groups:\n{groups_str}")
    
    @commands.command(aliases=['creategroup'])
    @has_been_setup()
    async def create_group(self, ctx: commands.Context, group_name: str):
        """Creates a group"""
        if ',' in group_name:
            return await ctx.send("Group names must not contain commas.")
        manager = self.get_manager(ctx.guild.id)
        if manager.create_group(group_name):
            return await ctx.send(f"Successfully created group<{group_name.upper()}>")
        await ctx.send(f"Group<{group_name.upper()}> already exists.")
    
    @commands.command(aliases=['deletegroup'])
    @has_been_setup()
    async def delete_group(self, ctx: commands.Context, group_name: str):
        """Deletes a group, this action is irreversible."""
        manager = self.get_manager(ctx.guild.id)
        if manager.delete_group(group_name):
            return await ctx.send(f"Successfully removed group<{group_name.upper()}>")
        await ctx.send(f"Group<{group_name.upper()}> does not exist.")
    
    @commands.command(aliases=['getsubscribed'])
    @has_been_setup()
    async def get_subscribed(self, ctx: commands.Context):
        """Gets the groups you are currently subscribed to."""
        manager = self.get_manager(ctx.guild.id)
        subscriptions = manager.get_subscribed(ctx.author.id)
        await ctx.send(f"You are subscribed to: {humanize.natural_list(subscriptions) if subscriptions else 'No one'}.")
    
    @commands.command(aliases=['subscribe'])
    @has_been_setup()
    async def subscribe_group(self, ctx: commands.Context, *, group_names: str):
        """Unsubscribe from a set of groups, seperated by space"""
        manager = self.get_manager(ctx.guild.id)
        groups = [e for e in group_names.upper().split(' ') if len(e)>0]
        successful = []
        for group in groups:
            if manager.subscribe(str(ctx.author.id), group):
                successful.append(group.upper())
        await ctx.send(f"Successfully subscribed to groups: {humanize.natural_list(successful)}.")
    
    @commands.command(aliases=['unsubscribe'])
    @has_been_setup()
    async def unsubscribe_group(self, ctx: commands.Context, *, group_names: str):
        """Unsubscribe from a set of groups, seperated by space"""
        manager = self.get_manager(ctx.guild.id)
        groups = [e for e in group_names.upper().split(' ') if len(e)>0]
        successful = []
        for group in groups:
            if manager.unsubscribe(str(ctx.author.id), group):
                successful.append(group.upper())
        await ctx.send(f"Successfully unsubscribed from groups: {humanize.lists(successful)}.")
    
    @commands.command(aliases=['listall', 'listallassign'])
    @has_been_setup()
    async def list_all_assignments(self, ctx: commands.Context):
        """Lists all assignments, visible to everyone."""
        manager = self.get_manager(ctx.guild.id)
        msg = await ctx.send(embed=manager.get_all_assignments_embed())
        for _ in range(10):
            await asyncio.sleep(1)
            await msg.edit(embed=manager.get_all_assignments_embed())
    
    @commands.command(aliases=['listmine', 'listmyassign'])
    @has_been_setup()
    async def list_personal_assignments(self, ctx: commands.Context, modifier: Literal['all', ''] = ''):
        """Lists your assignments, visible to everyone."""
        manager = self.get_manager(ctx.guild.id)
        msg = await ctx.send(embed=manager.get_personal_assignments_embed(ctx.author.id, include_completed=modifier=='all'))
        for _ in range(10):
            await asyncio.sleep(1)
            await msg.edit(embed=manager.get_personal_assignments_embed(ctx.author.id, include_completed=modifier=='all'))
    
    @commands.slash_command(name='listmine')
    @discord.option("mode", choices=["Todo", "All"], default="Todo", description="View only todo or view all of your assignments", required=False)
    @has_been_setup()
    async def list_personal_assignments_slash(self, ctx: discord.ApplicationContext, mode: str = "Todo"):
        """Lists your assignments, visible only to yourself."""
        manager = self.get_manager(ctx.guild.id)
        response = await ctx.respond(embed=manager.get_personal_assignments_embed(ctx.author.id, mode=='All'), ephemeral=True)
        for _ in range(10):
            await asyncio.sleep(1)
            await response.edit(embed=manager.get_personal_assignments_embed(ctx.author.id, include_completed=mode=='all'))
    
    @commands.command(aliases=['completed', 'done'])
    @has_been_setup()
    async def checklist_assignment(self, ctx: commands.Context, assignment_id: str):
        """Marks an assignment as done."""
        manager = self.get_manager(ctx.guild.id)
        if manager.checklist_assignment(ctx.author.id, assignment_id):
            return await ctx.send(f"Nicely done <@{ctx.author.id}>! :fire: :fire: :fire:")
        await ctx.send(f"No-uh, Can't do that.")
    
    @commands.slash_command(name='markasdone')
    @has_been_setup()
    async def checklist_assignment_slash(self, ctx: discord.ApplicationContext, assignment_id: str):
        """Marks an assignment as done. Visible only to you."""
        manager = self.get_manager(ctx.guild.id)
        if manager.checklist_assignment(ctx.author.id, assignment_id):
            return await ctx.respond(f"Nicely done <@{ctx.author.id}>! :fire: :fire: :fire:", ephemeral=True)
        await ctx.respond(f"No-uh, Can't do that.", ephemeral=True)
    
    @commands.command(aliases=['incompleted', 'incomplete', 'undone'])
    @has_been_setup()
    async def unchecklist_assignment(self, ctx: commands.Context, assignment_id: str):
        """Unchecklist an assignment by its id."""
        manager = self.get_manager(ctx.guild.id)
        if manager.unchecklist_assignment(ctx.author.id, assignment_id):
            return await ctx.send(f"Bruh, ok tho. -1 aura")
        await ctx.send(f"What are you trying to do?")
    
    @commands.slash_command(name='undone', aliases=['markasundone', 'markasincomplete'])
    @has_been_setup()
    async def unchecklist_assignment_slash(self, ctx: discord.ApplicationContext, assignment_id: str):
        """Unchecklist an assignment by its id. Visible only to yourself."""
        manager = self.get_manager(ctx.guild.id)
        if manager.unchecklist_assignment(ctx.author.id, assignment_id):
            return await ctx.respond(f"Bruh, ok tho. -1 aura", ephemeral=True)
        await ctx.respond(f"What are you trying to do?", ephemeral=True)
    
    @commands.command(aliases=['getassignment', 'getdetail', 'details'])
    @has_been_setup()
    async def get_assignment(self, ctx: commands.Context, assignment_id: str):
        """Gets an assignment's details."""
        manager = self.get_manager(ctx.guild.id)
        assignment = manager.assignments.get(assignment_id, None)
        if assignment is None:
            return await ctx.send("That assignment does not exists.")
        await ctx.send(embed=assignment.get_embed())
    
    @commands.command(aliases=['createassignment', 'add', 'create'])
    @has_been_setup()
    async def add_assignment(self, ctx: commands.Context, name: str, groups: str = "", deadline: str = "", link: str = ""):
        """Creates an assignment with given attributes. 
        Every attribute is seperated by space, every group is seperated by commas, 
        and the deadline format is: "%d-%mT%H:%M%z". 
        Example of a correctly formatted deadline for 17.00 at 20th february is '20-02T17:00+0700'.
        """
        manager = self.get_manager(ctx.guild.id)
        assignment = manager.create_assignment(name, groups, deadline, link)
        await ctx.send(f"Successfully created Assignment#{assignment.id}:\n" + str(assignment))
    
    @commands.command(aliases=['edit'])
    @has_been_setup()
    async def edit_assignment(self, ctx: commands.Context, assignment_id: str, field: Literal['name', 'deadline', 'groups', 'link'], value: str):
        """Edits an assignment's fields' value. Editable fields: name, deadline, groups, and link."""
        manager = self.get_manager(ctx.guild.id)
        if manager.edit_assignment(assignment_id, field, value):
            await ctx.send(f"Successfully edited Assignment#{assignment_id}!\n")
            return await ctx.send(embed=manager.assignments[assignment_id].get_embed())
        await ctx.send(f"Failed to delete assignment")
    
    @commands.command(aliases=['deleteassignment', 'delete'])
    @has_been_setup()
    async def delete_assignment(self, ctx: commands.Context, assignment_id: str):
        """Deletes an assignment. This action cannot be undone."""
        manager = self.get_manager(ctx.guild.id)
        deleted_assignment = manager.delete_assignment(assignment_id)
        if deleted_assignment is not None:
            return await ctx.send(f"Successfully deleted Assignment#{assignment_id}!")
        await ctx.send(f"Failed to delete assignment.")
    
    @commands.command(aliases=['archiveassignment', 'archive'])
    @has_been_setup()
    async def archive_assignment(self, ctx: commands.Context, assignment_id: str):
        """Archiving an assignment manually. Assignments gets archived automatically after its deadline."""
        manager = self.get_manager(ctx.guild.id)
        if manager.archive_assignment(assignment_id):
            return await ctx.send(f"Successfully archived Assignment#{assignment_id}!")
        await ctx.send(f"Failed to archive assignment.")
    
    @commands.command(aliases=['toggledashboard'])
    @has_been_setup()
    async def toggle_dashboard_message(self, ctx: commands.Context):
        """Toggles dashboard message on and off. This is off by default."""
        manager = self.get_manager(ctx.guild.id)
        await self.fix_dashboard_message(ctx.guild.id)
        manager.toggle_dashboard()
        await ctx.send(embed=get_toggle_message("Dashboard message", not manager.disable_dashboard))
    
    @commands.command(aliases=['forcesave'])
    @has_been_setup()
    @commands.is_owner()
    async def force_save(self, ctx: commands.Context):
        "Forcefully execute save immediately."
        self.save()
        return await ctx.send("Successfully saved data.")
    
    # @bind_tracker_announcer_channel.after_invoke
    # @create_group.after_invoke
    # @delete_group.after_invoke
    # @subscribe_group.after_invoke
    # @checklist_assignment.after_invoke
    # @unchecklist_assignment.after_invoke
    # @add_assignment.after_invoke
    # @edit_assignment.after_invoke
    # @delete_assignment.after_invoke
    # @archive_assignment.after_invoke
    # async def save_after_action(self, ctx: commands.Context):
    #     self.save()
    
    @bind_tracker_announcer_channel.error
    @create_group.error
    @delete_group.error
    @subscribe_group.error
    @unsubscribe_group.error
    @checklist_assignment.error
    @unchecklist_assignment.error
    @get_assignment.error
    @add_assignment.error
    @edit_assignment.error
    @delete_assignment.error
    @archive_assignment.error
    @toggle_dashboard_message.error
    @force_save.error
    async def error_handler(self, ctx: commands.Context, error: discord.DiscordException):
        print(error, type(error))
        if isinstance(error, discord.ext.commands.errors.CheckFailure):
            await ctx.send("You have to setup an assignment tracker before doing that!\nrun `~trackerchannel` on a channel you would like to set as a reminder channel.")
        else:
            await ctx.send(f"Caught error: {str(error)}.\nError type: {type(error)}\nLog:\n```{traceback.format_exc()}```")
            traceback.print_exc()


def setup(bot):
    bot.add_cog(AssignmentTracker(bot))
