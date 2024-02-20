import pathlib
from redbot.core import commands
import discord
import tempfile
from openai import OpenAI
import os
import json
from dotenv import load_dotenv, set_key


class WhisperToMe(commands.Cog):
    """Listen to incoming voice messages and respond with a transcription."""

    def __init__(self, bot):
        self.bot = bot
        self.language_validation_list = self._load_validation_language_dict()
        self.listening = False
        self._load_env_vars()
        self.client = self._load_open_ai_client()

    def _load_validation_language_dict(self):
        with open('ISO-639-1-language.json', 'r') as f:
            languages = json.load(f)
        return {language['code']: language['name'] for language in languages}

    def _load_env_vars(self):
        """Load environment variables."""
        load_dotenv()
        self.api_key = os.getenv("OPENAI_API_KEY", '')
        self.lang_code = os.getenv("ISO_639_1_LANGUAGE_CODE", 'en')

    def _load_open_ai_client(self):
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY is not set in the environment variables.")
        else:
            return OpenAI(api_key=self.api_key)

    async def _validate_api_key(self, ctx, client):
        """Validate the API key and provide detailed error messages."""
        try:
            models = client.models.list().data
        except Exception as e:
            await ctx.send(f"An error occurred while validating the API key:\n{e}")
            return False
        if any(model.id == "whisper-1" for model in models):
            await ctx.send("API key is valid...")
            return True
        else:
            await ctx.send(
                "API key is valid, but does not have access to the whisper-1 model.\nModify the restrictions "
                "on this key, in order to use it.")
            return False

    async def _validate_lang_code(self, ctx, lang_code):
        if lang_code in self.language_validation_list:
            return True
        else:
            await ctx.send(f"Invalid language code {lang_code} in the environment variables.")
            return False

    async def _validate_env_vars(self, ctx):
        """Validate environment variables and provide detailed error messages."""
        valid_lang_code = await self._validate_lang_code(ctx, self.lang_code)
        valid_api_key = await self._validate_api_key(ctx, self.client)
        if not valid_lang_code:
            await ctx.send("Language code is not set or is invalid.\nPlease set a valid language code before calling "
                           "`!start` again.")
            return False
        if not valid_api_key:
            await ctx.send("API key is not set or is invalid.\nPlease set a valid API key before calling `!start` "
                           "again.")
            return False
        return True

    async def _should_ignore_message(self, message):
        return not self.listening or message.author.bot or not message.flags.voice

    async def _process_voice_message(self, message):
        try:
            with tempfile.NamedTemporaryFile(suffix=".ogg", delete=True) as temp_file:
                # voice messages only have a single attachment, containing the ogg file
                await message.attachments[0].save(fp=pathlib.WindowsPath(tempfile.gettempdir()+temp_file.name))
                transcript = self._transcribe_voice_message(temp_file)
                await message.reply(transcript.text)
        except Exception as e:
            await message.channel.send(f"Error processing voice message:\n{str(e)}")

    def _transcribe_voice_message(self, temp_file):
        with open(temp_file.name, "rb") as file:
            return self.client.audio.transcriptions.create(file=file, model="whisper-1",
                                                           language=self.lang_code,
                                                           response_format="json")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if await self._should_ignore_message(message):
            return

        await self._process_voice_message(message)

    async def _check_listening_status(self, ctx, status):
        if self.listening == status:
            await ctx.send(f"I'm already {'listening' if status else 'not listening'} to messages.\nCommand ignored.")
            return True
        return False

    async def _toggle_listening(self, status, ctx):
        self.listening = status
        status_string = "Started" if status else "Stopped"
        await ctx.send(f"{status_string} listening to all messages.")

    @commands.admin()
    @commands.command()
    async def start(self, ctx):
        """Start listening to incoming voice messages"""
        if not await self._validate_env_vars(ctx) or await self._check_listening_status(ctx, True):
            return
        await self._toggle_listening(True, ctx)

    @commands.admin()
    @commands.command()
    async def stop(self, ctx):
        """Stop listening to incoming voice messages"""
        if await self._check_listening_status(ctx, False):
            return
        await self._toggle_listening(False, ctx)

    @commands.admin()
    @commands.command()
    async def set_lang(self, ctx, lang_code: str):
        """Set the transcript language to ISO-639-1 language code."""
        lowercase_lang_code = lang_code.lower()
        if lowercase_lang_code in self.language_validation_list:
            # os.putenv only works for the current process, so we need to use set_key from the dotenv library
            set_key(".env", "ISO_639_1_LANGUAGE_CODE", lowercase_lang_code)
            self.lang_code = lowercase_lang_code
            await ctx.send(f"Language set to {lang_code}.\nUse the `!start` command to begin listening!")
        else:
            await ctx.send(f"Invalid language code.\nPlease provide a valid ISO-639-1 language code.")

    @commands.admin()
    @commands.command()
    async def set_api_key(self, ctx, key: str):
        """Set the OpenAI API key to use for transcriptions."""
        valid_api_key = await self._validate_api_key(ctx, OpenAI(api_key=key))
        if valid_api_key:
            set_key(".env", "OPENAI_API_KEY", key)
            self.client = OpenAI(api_key=key)
            await ctx.send("API key set.\nUse the `!start` command to begin listening!")
        else:
            await ctx.send("API key not set due to errors.\nPlease try again.")

