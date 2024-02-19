from .whispertome import WhisperToMe


async def setup(bot):
    await bot.add_cog(WhisperToMe(bot))