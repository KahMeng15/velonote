import asyncio
import google.generativeai as genai
from app.config import get_settings
genai.configure(api_key=get_settings().GEMINI_API_KEY)
async def main():
    model = genai.GenerativeModel("gemini-1.5-flash")
    res = await model.generate_content_async("Say hi", stream=True)
    async for chunk in res:
        print(chunk.text)
asyncio.run(main())
