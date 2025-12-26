import discord
import discord_ios
from discord.ext import commands
from pathlib import Path
from datetime import datetime
import json
from src.config import Config
from src.tools.context import CustomContext
import aiomysql


class SlitBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.all()
        super().__init__(
            command_prefix=self.get_prefix,
            intents=intents,
            help_command=None,
            owner_ids={717111914848714803, 1285277569113133161, 1019668815728103526, 1198547933746962495}
        )
        self.uptime = None
        self.db_pool = None
        self.prefixes = {"guilds": {}, "users": {}}

    async def get_prefix(self, message):
        """Get the prefix for a user - checks for custom prefix first, then default"""
        if not message.guild:
            return Config.PREFIX

        # Get user's custom premium prefix from DB (if present)
        if self.db_pool:
            try:
                async with self.db_pool.acquire() as conn:
                    async with conn.cursor(aiomysql.DictCursor) as cur:
                        await cur.execute(
                            "SELECT prefix FROM premium_prefixes WHERE user_id = %s",
                            (message.author.id,)
                        )
                        result = await cur.fetchone()
                        if result:
                            return commands.when_mentioned_or(result['prefix'], Config.PREFIX)(self, message)
            except Exception as e:
                print(f"Error getting custom prefix: {e}")

        # Load prefixes from in-memory store
        try:
            guild_prefix = self.prefixes.get('guilds', {}).get(str(message.guild.id))
            user_self = self.prefixes.get('users', {}).get(str(message.author.id))
        except Exception:
            guild_prefix = None
            user_self = None

        prefixes = []
        if user_self:
            prefixes.append(user_self)
        if guild_prefix:
            prefixes.append(guild_prefix)

        prefixes.append(Config.PREFIX)
        return commands.when_mentioned_or(*prefixes)(self, message)

    async def get_context(self, message, *, cls=None):
        """Override to use CustomContext"""
        return await super().get_context(message, cls=cls or CustomContext)

    async def setup_hook(self):
        """Setup hook for bot initialization"""
        self.uptime = datetime.now()

        # Initialize database connection pool
        try:
            self.db_pool = await aiomysql.create_pool(
                host=Config.DB_HOST,
                port=Config.DB_PORT,
                user=Config.DB_USER,
                password=Config.DB_PASSWORD,
                db=Config.DB_NAME,
                autocommit=True
            )
            print("✅ Database connection pool created")
        except Exception as e:
            print(f"❌ Failed to create database pool: {e}")

        # Load prefixes.json into memory
        try:
            prefixes_path = Path(__file__).parent.parent / 'src' / 'prefixes.json'
            if prefixes_path.exists():
                try:
                    self.prefixes = json.loads(prefixes_path.read_text(encoding='utf-8'))
                    if 'guilds' not in self.prefixes:
                        self.prefixes.setdefault('guilds', {})
                    if 'users' not in self.prefixes:
                        self.prefixes.setdefault('users', {})
                except Exception as e:
                    print(f"⚠️ Failed to parse prefixes.json: {e}")
                    self.prefixes = {"guilds": {}, "users": {}}
            else:
                self.prefixes = {"guilds": {}, "users": {}}
        except Exception as e:
            print(f"⚠️ Failed to load prefixes: {e}")

        # Auto-load all cogs
        await self.load_cogs()
        print(f'✅ {self.user} is ready!')

    async def close(self):
        """Cleanup when bot shuts down"""
        if self.db_pool:
            self.db_pool.close()
            await self.db_pool.wait_closed()
        await super().close()

    async def on_ready(self):
        """Called when the bot is ready"""
        print(f"\n{'='*50}")
        print(f"🔥 Flare Bot is now online!")
        print(f"📝 Logged in as: {self.user.name}")
        print(f"🆔 Bot ID: {self.user.id}")
        print(f"🌐 Connected to {len(self.guilds)} guilds")
        print(f"👥 Serving {len(self.users)} users")
        print(f"{'='*50}\n")

    async def on_guild_remove(self, guild: discord.Guild):
        """Called when bot leaves a guild"""
        print(f"⚠️  Removed from guild: {guild.name} (ID: {guild.id})")

    async def on_message(self, message):
        """Process commands from messages"""
        if message.author.bot:
            return
        await self.process_commands(message)

    async def on_command_error(self, ctx, error):
        """Handle command errors"""
        if isinstance(error, commands.CommandNotFound):
            cmd = ctx.invoked_with
            # Only respond if the command is exactly 'h' followed by a subcommand
            if cmd.lower() == 'h':
                # Get the rest of the message after the prefix and 'h'
                msg_content = ctx.message.content
                parts = msg_content.split(maxsplit=2)
                if len(parts) >= 2:
                    # parts[0] is prefix+h, parts[1] is the command they're looking for
                    lookup_cmd = parts[1] if len(parts) > 1 else ""
                    await ctx.warn(f"yo twin i didnt add `{ctx.prefix}{lookup_cmd}` just yet, go make a suggestion in our [support server](https://discord.gg/9H6NqBszzR)")
            return
        raise error

    async def load_cogs(self):
        """Automatically load all cogs from the cogs directory and subdirectories"""
        cogs_path = Path(__file__).parent.parent / 'cogs'

        if not cogs_path.exists():
            print("⚠️  Cogs directory not found!")
            return

        loaded = 0
        failed = 0

        # Load cogs from main cogs directory
        for file in cogs_path.glob('*.py'):
            if file.name.startswith('_'):
                continue
            cog_name = f'cogs.{file.stem}'
            try:
                await self.load_extension(cog_name)
                print(f"✅ Loaded {cog_name}")
                loaded += 1
            except Exception as e:
                print(f"❌ Failed to load {cog_name}: {e}")
                failed += 1

        # Load cogs from subdirectories
        for subfolder in cogs_path.iterdir():
            if subfolder.is_dir() and not subfolder.name.startswith('_'):
                for file in subfolder.glob('*.py'):
                    if file.name.startswith('_'):
                        continue
                    cog_name = f'cogs.{subfolder.name}.{file.stem}'
                    try:
                        await self.load_extension(cog_name)
                        print(f"✅ Loaded {cog_name}")
                        loaded += 1
                    except Exception as e:
                        print(f"❌ Failed to load {cog_name}: {e}")
                        failed += 1

        print(f"\n📦 Cogs loaded: {loaded} | Failed: {failed}")


bot = SlitBot()


def run():
    """Run the bot"""
    bot.run(Config.BOT_TOKEN)
