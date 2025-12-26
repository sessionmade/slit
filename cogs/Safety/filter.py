import re
import json
import os
import discord
from discord.ext import commands
from datetime import datetime, timezone, timedelta

# Storage file for filters
FILTERS_FILE = "src/filters.json"

INVITE_REGEX = r"(?i)\b(?:https?:\/\/)?(?:www\.)?(?:discord\.gg|discord(?:app)?\.com\/invite)\/[A-Za-z0-9-]+(?:\S*)?"


def load_filters():
    if not os.path.exists(FILTERS_FILE):
        return {}
    with open(FILTERS_FILE, "r") as f:
        return json.load(f)


def save_filters(data):
    os.makedirs(os.path.dirname(FILTERS_FILE), exist_ok=True)
    with open(FILTERS_FILE, "w") as f:
        json.dump(data, f, indent=4)


def get_guild_filters(guild_id):
    data = load_filters()
    return data.get(str(guild_id), {"keywords": {}, "invite": None})


def save_guild_filters(guild_id, guild_data):
    data = load_filters()
    data[str(guild_id)] = guild_data
    save_filters(data)


def parse_duration(duration: str) -> int:
    if not duration:
        return 0
    match = re.match(r"^(\d+)([smhd])$", duration.strip().lower())
    if not match:
        return 0
    value, unit = int(match.group(1)), match.group(2)
    multipliers = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    return value * multipliers.get(unit, 0)


class PageModal(discord.ui.Modal, title="Go to Page"):
    page_num = discord.ui.TextInput(label="Page Number", placeholder="Enter page number...", max_length=3)

    def __init__(self, view):
        super().__init__()
        self.paginator_view = view

    async def on_submit(self, interaction: discord.Interaction):
        try:
            page = int(self.page_num.value) - 1
            if 0 <= page < len(self.paginator_view.pages):
                self.paginator_view.current_page = page
                embed = self.paginator_view.pages[page]
                embed.set_footer(text=f"Page {page + 1}/{len(self.paginator_view.pages)}")
                await interaction.response.edit_message(embed=embed)
            else:
                await interaction.response.send_message("Invalid page number", ephemeral=True)
        except ValueError:
            await interaction.response.send_message("Please enter a valid number", ephemeral=True)


class HelpPaginator(discord.ui.View):
    def __init__(self, pages, author):
        super().__init__(timeout=120)
        self.pages = pages
        self.author = author
        self.current_page = 0
        self.message = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("This isn't your menu", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="<", style=discord.ButtonStyle.secondary)
    async def prev_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page > 0:
            self.current_page -= 1
            embed = self.pages[self.current_page]
            embed.set_footer(text=f"Page {self.current_page + 1}/{len(self.pages)}")
            await interaction.response.edit_message(embed=embed)
        else:
            await interaction.response.defer()

    @discord.ui.button(label=">", style=discord.ButtonStyle.secondary)
    async def next_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page < len(self.pages) - 1:
            self.current_page += 1
            embed = self.pages[self.current_page]
            embed.set_footer(text=f"Page {self.current_page + 1}/{len(self.pages)}")
            await interaction.response.edit_message(embed=embed)
        else:
            await interaction.response.defer()

    @discord.ui.button(label="↑↓", style=discord.ButtonStyle.secondary)
    async def goto_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(PageModal(self))

    @discord.ui.button(label="✕", style=discord.ButtonStyle.secondary)
    async def close_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.message.delete()


class Filter(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def build_help_pages(self, ctx):
        prefix = "-"
        pages = []

        # Page 1: filter (main)
        e1 = discord.Embed(color=0x2b2d31)
        e1.set_author(name=self.bot.user.name, icon_url=self.bot.user.display_avatar.url)
        e1.title = "Group command: filter"
        e1.description = "AutoMod filter management commands"
        e1.add_field(
            name="\u200b",
            value=f"```Syntax: {prefix}filter\nExample: {prefix}filter```",
            inline=False
        )
        e1.add_field(name="Aliases", value="automod", inline=False)
        e1.set_thumbnail(url=self.bot.user.display_avatar.url)
        pages.append(e1)

        # Page 2: filter add
        e2 = discord.Embed(color=0x2b2d31)
        e2.set_author(name=self.bot.user.name, icon_url=self.bot.user.display_avatar.url)
        e2.title = "Command: filter add"
        e2.description = "Add a keyword to the filter list"
        e2.add_field(
            name="\u200b",
            value=f"```Syntax: {prefix}filter add <word> [--do timeout/kick/ban] [--duration 10m]\nExample: {prefix}filter add badword --do timeout --duration 15m```",
            inline=False
        )
        e2.set_thumbnail(url=self.bot.user.display_avatar.url)
        pages.append(e2)

        # Page 3: filter remove
        e3 = discord.Embed(color=0x2b2d31)
        e3.set_author(name=self.bot.user.name, icon_url=self.bot.user.display_avatar.url)
        e3.title = "Command: filter remove"
        e3.description = "Remove a keyword from the filter list"
        e3.add_field(
            name="\u200b",
            value=f"```Syntax: {prefix}filter remove <word>\nExample: {prefix}filter remove badword```",
            inline=False
        )
        e3.set_thumbnail(url=self.bot.user.display_avatar.url)
        pages.append(e3)

        # Page 4: filter list
        e4 = discord.Embed(color=0x2b2d31)
        e4.set_author(name=self.bot.user.name, icon_url=self.bot.user.display_avatar.url)
        e4.title = "Command: filter list"
        e4.description = "List all keyword filters"
        e4.add_field(
            name="\u200b",
            value=f"```Syntax: {prefix}filter list\nExample: {prefix}filter list```",
            inline=False
        )
        e4.set_thumbnail(url=self.bot.user.display_avatar.url)
        pages.append(e4)

        # Page 5: filter invite on
        e5 = discord.Embed(color=0x2b2d31)
        e5.set_author(name=self.bot.user.name, icon_url=self.bot.user.display_avatar.url)
        e5.title = "Command: filter invite on"
        e5.description = "Enable Discord invite link filtering"
        e5.add_field(
            name="\u200b",
            value=f"```Syntax: {prefix}filter invite on [--do timeout/kick/ban] [--duration 10m]\nExample: {prefix}filter invite on --do timeout --duration 30m```",
            inline=False
        )
        e5.set_thumbnail(url=self.bot.user.display_avatar.url)
        pages.append(e5)

        # Page 6: filter invite off
        e6 = discord.Embed(color=0x2b2d31)
        e6.set_author(name=self.bot.user.name, icon_url=self.bot.user.display_avatar.url)
        e6.title = "Command: filter invite off"
        e6.description = "Disable Discord invite link filtering"
        e6.add_field(
            name="\u200b",
            value=f"```Syntax: {prefix}filter invite off\nExample: {prefix}filter invite off```",
            inline=False
        )
        e6.set_thumbnail(url=self.bot.user.display_avatar.url)
        pages.append(e6)

        return pages

    @commands.Cog.listener()
    async def on_automod_action(self, execution: discord.AutoModAction):
        """Handle AutoMod actions and apply custom punishments"""
        guild = self.bot.get_guild(execution.guild_id)
        if not guild:
            return

        user = guild.get_member(execution.user_id)
        if not user:
            return

        matched_text = execution.matched_content or execution.matched_keyword
        if not matched_text:
            return

        guild_data = get_guild_filters(guild.id)
        config = None

        # Check keyword filters
        if execution.matched_keyword:
            keyword_lower = execution.matched_keyword.lower()
            if keyword_lower in guild_data.get("keywords", {}):
                config = guild_data["keywords"][keyword_lower]

        # Check invite filter
        if not config and guild_data.get("invite"):
            if re.search(INVITE_REGEX, matched_text, re.IGNORECASE):
                config = guild_data["invite"]

        if not config:
            return

        punishment = config.get("punishment", "delete")
        reason = config.get("reason", "AutoMod")
        duration = config.get("duration", "10m")

        try:
            await self.apply_punishment(guild, user, punishment, reason, duration, matched_text)
        except discord.Forbidden:
            print(f"[Filter] Missing permissions to {punishment} {user}")
        except Exception as e:
            print(f"[Filter] Error: {e}")

    async def apply_punishment(self, guild, user, punishment, reason, duration, trigger):
        if punishment == "timeout":
            seconds = parse_duration(duration)
            until = datetime.now(timezone.utc) + timedelta(seconds=seconds)
            await user.timeout(until, reason=reason)
            print(f"[Filter] Timed out {user} for {duration}")

        elif punishment == "kick":
            await user.kick(reason=reason)
            print(f"[Filter] Kicked {user}")

        elif punishment == "ban":
            await guild.ban(user, reason=reason)
            print(f"[Filter] Banned {user}")

    @commands.group(name="filter", invoke_without_command=True, aliases=["automod"])
    @commands.has_permissions(manage_guild=True)
    async def filter_group(self, ctx):
        """Filter commands with paginated help"""
        pages = self.build_help_pages(ctx)
        pages[0].set_footer(text=f"Page 1/{len(pages)}")
        view = HelpPaginator(pages, ctx.author)
        view.message = await ctx.send(embed=pages[0], view=view)

    @filter_group.command(name="add")
    @commands.has_permissions(manage_guild=True)
    async def filter_add(self, ctx, *, args: str = None):
        """Add a keyword filter"""
        if not args:
            return await ctx.deny("Usage: `filter add <word> [--do timeout/kick/ban] [--duration 10m]`")

        if "COMMUNITY" not in ctx.guild.features:
            return await ctx.deny("AutoMod requires **Community** to be enabled for this server")

        parts = args.split()
        trigger = parts[0].lower()
        punishment = "delete"
        reason = "AutoMod"
        duration = "10m"

        for i, part in enumerate(parts):
            if part == "--do" and i + 1 < len(parts):
                punishment = parts[i + 1].lower()
            elif part == "--reason" and i + 1 < len(parts):
                reason = parts[i + 1]
            elif part == "--duration" and i + 1 < len(parts):
                duration = parts[i + 1]

        guild_data = get_guild_filters(ctx.guild.id)
        if "keywords" not in guild_data:
            guild_data["keywords"] = {}

        guild_data["keywords"][trigger] = {
            "punishment": punishment,
            "reason": reason,
            "duration": duration
        }
        save_guild_filters(ctx.guild.id, guild_data)

        try:
            rules = await ctx.guild.fetch_automod_rules()
            rule = discord.utils.get(rules, name="Bot Keyword Filter")

            if rule:
                triggers = list(rule.trigger.keyword_filter or [])
                if trigger not in triggers:
                    triggers.append(trigger)
                    await rule.edit(
                        trigger=discord.AutoModTrigger(
                            type=discord.AutoModRuleTriggerType.keyword,
                            keyword_filter=triggers
                        )
                    )
            else:
                await ctx.guild.create_automod_rule(
                    name="Bot Keyword Filter",
                    event_type=discord.AutoModRuleEventType.message_send,
                    trigger=discord.AutoModTrigger(
                        type=discord.AutoModRuleTriggerType.keyword,
                        keyword_filter=[trigger]
                    ),
                    actions=[discord.AutoModRuleAction(type=discord.AutoModRuleActionType.block_message)],
                    enabled=True,
                    reason="Bot managed filter"
                )
        except Exception as e:
            return await ctx.deny(f"Failed to sync AutoMod: {e}")

        await ctx.approve(f"Filter added: `{trigger}` → {punishment}")

    @filter_group.command(name="remove")
    @commands.has_permissions(manage_guild=True)
    async def filter_remove(self, ctx, trigger: str = None):
        """Remove a keyword filter"""
        if not trigger:
            return await ctx.deny("Usage: `filter remove <word>`")

        trigger = trigger.lower()
        guild_data = get_guild_filters(ctx.guild.id)

        if trigger not in guild_data.get("keywords", {}):
            return await ctx.deny(f"No filter found for `{trigger}`")

        del guild_data["keywords"][trigger]
        save_guild_filters(ctx.guild.id, guild_data)

        try:
            rules = await ctx.guild.fetch_automod_rules()
            rule = discord.utils.get(rules, name="Bot Keyword Filter")
            if rule and rule.trigger.keyword_filter:
                triggers = list(rule.trigger.keyword_filter)
                if trigger in triggers:
                    triggers.remove(trigger)
                    if triggers:
                        await rule.edit(
                            trigger=discord.AutoModTrigger(
                                type=discord.AutoModRuleTriggerType.keyword,
                                keyword_filter=triggers
                            )
                        )
                    else:
                        await rule.delete()
        except Exception as e:
            print(f"[Filter] Error removing from AutoMod: {e}")

        await ctx.approve(f"Filter removed: `{trigger}`")

    @filter_group.command(name="list")
    @commands.has_permissions(manage_guild=True)
    async def filter_list(self, ctx):
        """List all keyword filters"""
        guild_data = get_guild_filters(ctx.guild.id)
        keywords = guild_data.get("keywords", {})

        if not keywords:
            return await ctx.deny("No filters set")

        lines = []
        for word, cfg in keywords.items():
            punishment = cfg.get("punishment", "delete")
            if punishment == "timeout":
                dur = cfg.get("duration", "10m")
                lines.append(f"`{word}` → {dur} timeout")
            else:
                lines.append(f"`{word}` → {punishment}")

        embed = discord.Embed(
            title="Keyword Filters",
            description="\n".join(lines),
            color=0x2b2d31
        )
        embed.set_footer(text=f"Total: {len(keywords)}")
        await ctx.send(embed=embed)

    @filter_group.group(name="invite", invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def filter_invite(self, ctx):
        """Invite filter commands"""
        await ctx.approve("`filter invite on [--do timeout/kick/ban]` or `filter invite off`")

    @filter_invite.command(name="on")
    @commands.has_permissions(manage_guild=True)
    async def filter_invite_on(self, ctx, *, args: str = None):
        """Enable invite filtering"""
        if "COMMUNITY" not in ctx.guild.features:
            return await ctx.deny("AutoMod requires **Community** to be enabled")

        punishment = "delete"
        duration = "10m"

        if args:
            parts = args.split()
            for i, part in enumerate(parts):
                if part == "--do" and i + 1 < len(parts):
                    punishment = parts[i + 1].lower()
                elif part == "--duration" and i + 1 < len(parts):
                    duration = parts[i + 1]

        guild_data = get_guild_filters(ctx.guild.id)
        guild_data["invite"] = {
            "punishment": punishment,
            "reason": "Invite link",
            "duration": duration
        }
        save_guild_filters(ctx.guild.id, guild_data)

        try:
            rules = await ctx.guild.fetch_automod_rules()
            rule = discord.utils.get(rules, name="Bot Invite Filter")

            if not rule:
                await ctx.guild.create_automod_rule(
                    name="Bot Invite Filter",
                    event_type=discord.AutoModRuleEventType.message_send,
                    trigger=discord.AutoModTrigger(
                        type=discord.AutoModRuleTriggerType.keyword,
                        regex_patterns=[INVITE_REGEX]
                    ),
                    actions=[discord.AutoModRuleAction(type=discord.AutoModRuleActionType.block_message)],
                    enabled=True,
                    reason="Bot managed invite filter"
                )
        except Exception as e:
            return await ctx.deny(f"Failed to sync AutoMod: {e}")

        await ctx.approve(f"Invite filter enabled → {punishment}")

    @filter_invite.command(name="off")
    @commands.has_permissions(manage_guild=True)
    async def filter_invite_off(self, ctx):
        """Disable invite filtering"""
        guild_data = get_guild_filters(ctx.guild.id)

        if "invite" not in guild_data:
            return await ctx.deny("Invite filter is already disabled")

        del guild_data["invite"]
        save_guild_filters(ctx.guild.id, guild_data)

        try:
            rules = await ctx.guild.fetch_automod_rules()
            rule = discord.utils.get(rules, name="Bot Invite Filter")
            if rule:
                await rule.delete()
        except Exception as e:
            print(f"[Filter] Error removing invite rule: {e}")

        await ctx.approve("Invite filter disabled")


async def setup(bot):
    await bot.add_cog(Filter(bot))
