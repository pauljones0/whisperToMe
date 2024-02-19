import pathlib
from redbot.core import commands
import discord
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
        self.client = self._load_open_ai_client()
        self.lang_code = self._load_lang_code()

    def _load_validation_language_dict(self):
        with open('ISO-639-1-language.json', 'r') as f:
            languages = json.load(f)
        return {language['code']: language['name'] for language in languages}

    def create_env_if_needed_and_load(self):
        if not os.path.isfile('.env'):
            with open('.env', 'w') as f:
                pass
        load_dotenv()

    def _load_lang_code(self):
        self.create_env_if_needed_and_load()
        lang_code = os.getenv("ISO_639_1_LANGUAGE_CODE")
        if lang_code is None:
            with open('.env', 'a') as f:
                f.write(f'ISO_639_1_LANGUAGE_CODE={lang_code}\n')
            load_dotenv()
        return lang_code

    def _load_open_ai_client(self):
        self.create_env_if_needed_and_load()
        api_key = os.getenv("OPENAI_API_KEY")
        if api_key is None:
            with open('.env', 'a') as f:
                f.write(f'OPENAI_API_KEY={api_key}\n')
            load_dotenv()
            return api_key
        else:
            return OpenAI(api_key=api_key)

    async def _validate_api_key(self, ctx, client):
        try:
            temporary_client = client
            if temporary_client is None:
                await ctx.send("No API key set in the environment variables.")
                return False
            else:
                models = temporary_client.models.list().data
                if any(model.id == "whisper-1" for model in models):
                    await ctx.send("API key is valid...")
                    return True
                else:
                    await ctx.send(
                        "API key is valid, but does not have access to the whisper-1 model.\nModify the restrictions "
                        "on this key, in order to use it.")
                    return False
        except Exception as e:
            await ctx.send(f"An unexpected error occurred:\n{e}")
            return False

    async def _validate_lang_code(self, ctx, lang_code):
        if lang_code is None:
            await ctx.send(f"No language code set in the environment variables.")
            return False
        elif lang_code in self.language_validation_list:
            return True
        else:
            await ctx.send(f"Invalid language code {lang_code} in the environment variables.")
            return False

    @commands.admin()
    @commands.command()
    async def start(self, ctx):
        """Start listening to incoming voice messages"""
        valid_lang_code = await self._validate_lang_code(ctx, self.lang_code)
        if valid_lang_code:
            valid_api_key = await self._validate_api_key(ctx, self.client)
            if valid_api_key:
                await ctx.send("Both environment variables are set and valid.")
            else:
                await ctx.send("API key is not set or is invalid.\nPlease set a valid API key before calling `!start` "
                               "again.")
                return
        else:
            await ctx.send("Language code is not set or is invalid.\nPlease set a valid language code before calling "
                           "`!start` again.")
            return
        if self.listening:
            await ctx.send("I'm already listening to messages.\nStart command ignored.")
        else:
            self.listening = True
            await ctx.send(f"Started listening to all messages.")

    @commands.admin()
    @commands.command()
    async def stop(self, ctx):
        """Stop listening to incoming voice messages"""
        if self.listening:
            self.listening = False
            await ctx.send("Stopped listening to messages.")
        else:
            await ctx.send(f"Wasn't listening to messages.\nStop command ignored.")

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
            # os.putenv only works for the current process, so we need to use set_key from the dotenv library
            set_key(".env", "OPENAI_API_KEY", key)
            self.client = OpenAI(api_key=key)
            await ctx.send("API key set.\nUse the `!start` command to begin listening!")
        else:
            await ctx.send("API key not set due to errors.\nPlease try again.")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        deafened = not self.listening
        is_a_bot = message.author.bot
        is_not_a_voice_message = not message.flags.voice

        if deafened or is_a_bot or is_not_a_voice_message:
            return  # Don't transcribe if it's a message from a bot, not a voice message or if the bot is deafened
        for attachment in message.attachments:
            if attachment.is_voice_message():
                try:
                    #using attachment.bytes should be possible, I've checked and it's an ogg file, but openai api rejects it, so using save, use, delete file for now
                    await attachment.save(fp=pathlib.WindowsPath("./voice_message.ogg"))
                    with open("voice_message.ogg", "rb") as file:
                        transcript = self.client.audio.transcriptions.create(file=file, model="whisper-1",
                                                                             language=self.lang_code,
                                                                             response_format="json")
                    await message.reply(transcript.text)
                except Exception as e:
                    await message.channel.send(f"Error processing voice message:\n{str(e)}")
                finally:
                    if os.path.exists("voice_message.ogg"):
                        os.remove("voice_message.ogg")
