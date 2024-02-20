import pathlib
from redbot.core import commands
import discord
import tempfile
from openai import OpenAI
import os
import json
from dotenv import load_dotenv, set_key

OPENAI_API_KEY = 'OPENAI_API_KEY'
ISO_639_1_LANGUAGE_CODE = 'ISO_639_1_LANGUAGE_CODE'


class WhisperToMe(commands.Cog):
    """A red discord bot cog that transcribes voice messages using the OpenAI API."""

    def __init__(self, bot, *args, **kwargs):
        """A cog that transcribes voice messages using the OpenAI API."""
        super().__init__(*args, **kwargs)
        self.bot = bot
        self.language_validation_list = self._load_validation_language_dict()
        self.listening = False
        self.lang_code = None
        self.api_key = None
        self._load_env_vars()
        self.client = self._load_open_ai_client()

    def _load_validation_language_dict(self):
        """Loads a dictionary of ISO-639-1 language codes from a JSON file."""
        with open('ISO-639-1-language.json', 'r') as f:
            languages = json.load(f)
        return {language['code']: language['name'] for language in languages}

    def _load_env_vars(self):
        """Loads OpenAI API key and language code from environment variables."""
        load_dotenv()
        self.api_key = os.getenv(OPENAI_API_KEY, '')
        self.lang_code = os.getenv(ISO_639_1_LANGUAGE_CODE, 'en')

    def _load_open_ai_client(self):
        """Initializes an OpenAI client with the API key."""
        if not self.api_key:
            raise ValueError(f"{OPENAI_API_KEY} is not set in the environment variables.")
        else:
            return OpenAI(api_key=self.api_key)

    async def _validate_api_key(self, ctx, client):
        """Validates the OpenAI API key and checks access to the 'whisper-1' model."""
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
        """Validates the ISO-639-1 language code."""
        if lang_code in self.language_validation_list:
            return True
        else:
            await ctx.send(f"Invalid language code {lang_code} in the environment variables.")
            return False

    def _generate_error_message(self, entity, command):
        """Generates an error message for invalid environment variables."""
        return (f"{entity} is not set or is invalid.\nPlease use the command `{command}` to set the {entity.lower()}" +
                "before calling `!start` again.")

    async def _validate_env_vars(self, ctx):
        """Validates the OpenAI API key and the ISO-639-1 language code."""
        valid_lang_code = await self._validate_lang_code(ctx, self.lang_code)
        valid_api_key = await self._validate_api_key(ctx, self.client)
        if not valid_lang_code:
            await ctx.send(self._generate_error_message("Language code", "!set_lang <language code>"))
            return False
        if not valid_api_key:
            await ctx.send(self._generate_error_message("API key", "!set_api_key <OpenAI api key>"))
            return False
        return True

    async def _should_ignore_message(self, message):
        """Determines if a message should be ignored based on certain conditions."""
        return not self.listening or message.author.bot or not message.flags.voice

    async def _process_voice_message(self, message):
        """Processes a voice message by transcribing it using the OpenAI API."""

        try:
            fd, path = tempfile.mkstemp(suffix=".ogg")
            try:
                with os.fdopen(fd, 'wb') as _:
                    await message.attachments[0].save(fp=pathlib.Path(path))
                with open(path, 'rb') as file:
                    transcript = self._transcribe_voice_message(file)
                    await message.reply(transcript.text)
            finally:
                os.remove(path)
        except Exception as e:
            await message.channel.send(f"Error processing voice message:\n{str(e)}")

    def _transcribe_voice_message(self, temp_file):
        """Transcribes a voice message using the OpenAI API."""
        with open(temp_file.name, "rb") as file:
            return self.client.audio.transcriptions.create(file=file, model="whisper-1",
                                                           language=self.lang_code,
                                                           response_format="json")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Processes incoming messages if they meet certain criteria."""
        should_ignore = await self._should_ignore_message(message)
        if should_ignore:
            return

        await self._process_voice_message(message)

    async def _check_listening_status(self, ctx, status):
        """Checks if the bots current listening status matches the desired status."""
        if self.listening == status:
            await ctx.send(f"I'm already {'listening' if status else 'not listening'} to messages.\nCommand ignored.")
            return True
        return False

    async def _toggle_listening(self, status, ctx):
        """Toggles the bots listening status and notifies the user."""
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
        """Sets the language for transcriptions."""
        lowercase_lang_code = lang_code.lower()
        if lowercase_lang_code in self.language_validation_list:
            # os.putenv() only works for the current process, so we need to use set_key from the dotenv library
            set_key(".env", "ISO_639_1_LANGUAGE_CODE", lowercase_lang_code)
            self.lang_code = lowercase_lang_code
            await ctx.send(f"Language set to {lang_code}.\nUse the `!start` command to begin listening!")
        else:
            await ctx.send(f"Invalid language code.\nPlease provide a valid ISO-639-1 language code.")

    @commands.admin()
    @commands.command()
    async def set_api_key(self, ctx, key: str):
        """Sets the OpenAI API key for transcriptions."""
        valid_api_key = await self._validate_api_key(ctx, OpenAI(api_key=key))
        if valid_api_key:
            set_key(".env", "OPENAI_API_KEY", key)
            self.client = OpenAI(api_key=key)
            await ctx.send("API key set.\nUse the `!start` command to begin listening!")
        else:
            await ctx.send("API key not set due to errors.\nPlease try again.")
