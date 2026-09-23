"""Owner 1: implement structured OpenAI output here.

Use an explicitly configured available model; timeout, bounded output and retries.
Accept an injected client for offline tests. Check refusals, invalid ids and schema.
Record token usage via the platform's accounting contract before live integration.
Never silently replace failed live calls with the scaffold response.
Reference: https://developers.openai.com/api/docs/guides/structured-outputs
"""
