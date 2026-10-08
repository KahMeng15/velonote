from app.config import get_settings
s = get_settings()
print(s.GLOBAL_AI_TIER1_PROVIDER)
print(s.GLOBAL_AI_TIER2_PROVIDER)
print(s.GLOBAL_AI_TIER3_PROVIDER)
print(getattr(s, 'GEMINI_API_KEY', None))
