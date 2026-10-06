"""AI client for LLM interactions"""

import asyncio
import logging
import re
from collections.abc import Awaitable, Callable
from typing import TypeVar

import httpx
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.db import User

logger = logging.getLogger(__name__)
settings = get_settings()
T = TypeVar("T")


class AITier:
    """Configuration for an AI tier"""

    def __init__(
        self,
        provider: str,
        model_name: str,
        api_key: str,
        reasoning_level: str,
        base_url: str | None = None,
    ):
        self.provider = provider
        self.model_name = model_name
        self.api_key = api_key
        self.reasoning_level = reasoning_level
        self.base_url = base_url
        self.model = None  # For Gemini/HF clients


class AIClient:
    """Unified AI client with 3-tier fallback system (Gemini -> Gemini -> Ollama)"""

    def __init__(self, user: User | None = None, db: Session | None = None):
        self.user = user
        self.db = db
        self.request_timeout_seconds = 240
        self.max_retries = 2  # Retries per tier
        self.retry_base_delay_seconds = 1.0
        self.last_successful_tier: AITier | None = None

        # 1. Start with 3-tier defaults from .env settings
        self.tiers: list[AITier] = [
            AITier(
                provider=settings.GLOBAL_AI_TIER1_PROVIDER,
                model_name=settings.GLOBAL_AI_TIER1_MODEL,
                api_key=settings.GLOBAL_AI_TIER1_API_KEY,
                reasoning_level=settings.GLOBAL_AI_TIER1_REASONING_LEVEL,
                base_url=settings.GLOBAL_AI_TIER1_BASE_URL or settings.OLLAMA_BASE_URL,
            ),
            AITier(
                provider=settings.GLOBAL_AI_TIER2_PROVIDER,
                model_name=settings.GLOBAL_AI_TIER2_MODEL,
                api_key=settings.GLOBAL_AI_TIER2_API_KEY,
                reasoning_level=settings.GLOBAL_AI_TIER2_REASONING_LEVEL,
                base_url=settings.GLOBAL_AI_TIER2_BASE_URL or settings.OLLAMA_BASE_URL,
            ),
            AITier(
                provider=settings.GLOBAL_AI_TIER3_PROVIDER,
                model_name=settings.GLOBAL_AI_TIER3_MODEL,
                api_key=settings.GLOBAL_AI_TIER3_API_KEY,
                reasoning_level=settings.GLOBAL_AI_TIER3_REASONING_LEVEL,
                base_url=settings.GLOBAL_AI_TIER3_BASE_URL or settings.OLLAMA_BASE_URL,
            ),
        ]

        # Append optional Tier 4 if configured
        if settings.GLOBAL_AI_TIER4_PROVIDER:
            self.tiers.append(
                AITier(
                    provider=settings.GLOBAL_AI_TIER4_PROVIDER,
                    model_name=settings.GLOBAL_AI_TIER4_MODEL,
                    api_key=settings.GLOBAL_AI_TIER4_API_KEY,
                    reasoning_level=settings.GLOBAL_AI_TIER4_REASONING_LEVEL,
                    base_url=settings.GLOBAL_AI_TIER4_BASE_URL,
                )
            )

        # 3. User-specific override (Legacy/Personal)
        # If user has a personal provider configured and is NOT using global config,
        # we treat it as an additional Tier 0 (top priority).
        if user and not user.use_global_ai_config and user.ai_provider:
            logger.info(f"Applying User-specific AI override: {user.ai_provider} ({user.ai_model})")
            user_tier = AITier(
                provider=user.ai_provider,
                model_name=user.ai_model or settings.GLOBAL_AI_TIER1_MODEL,
                api_key=settings.GLOBAL_AI_TIER1_API_KEY,
                reasoning_level="medium",
                base_url=user.ai_base_url,
            )
            self.tiers.insert(0, user_tier)

        self._init_tiers()

    @property
    def provider(self) -> str:
        tier = self.last_successful_tier or (self.tiers[0] if self.tiers else None)
        return tier.provider if tier else "unknown"

    @provider.setter
    def provider(self, value: str):
        if self.tiers:
            self.tiers[0].provider = value

    @property
    def gemini_key(self) -> str | None:
        tier = self.last_successful_tier or (self.tiers[0] if self.tiers else None)
        return tier.api_key if tier and tier.provider == "gemini" else None

    @gemini_key.setter
    def gemini_key(self, value: str):
        if self.tiers and self.tiers[0].provider == "gemini":
            self.tiers[0].api_key = value

    @property
    def ai_model_name(self) -> str:
        tier = self.last_successful_tier or (self.tiers[0] if self.tiers else None)
        return tier.model_name if tier else "default"

    @ai_model_name.setter
    def ai_model_name(self, value: str):
        if self.tiers:
            self.tiers[0].model_name = value

    def _init_gemini(self):
        """Legacy re-initialization for Tier 1 if it's Gemini"""
        if self.tiers and self.tiers[0].provider == "gemini":
            self._init_gemini_tier(self.tiers[0])

    def _init_tiers(self):
        """Initialize clients for each tier"""
        for tier in self.tiers:
            if tier.provider == "gemini":
                self._init_gemini_tier(tier)
            elif tier.provider == "huggingface":
                self._init_huggingface_tier(tier)
            elif tier.provider == "groq":
                self._init_groq_tier(tier)

    def _init_gemini_tier(self, tier: AITier):
        try:
            import google.generativeai as genai

            if not tier.api_key:
                logger.warning(f"!!! No API key provided for Gemini tier ({tier.model_name}) !!!")
                return

            # Diagnostic: Show first and last 2 chars to help user verify without leaking secret
            key_preview = (
                f"{tier.api_key[:2]}...{tier.api_key[-2:]}"
                if len(tier.api_key) > 4
                else tier.api_key
            )
            logger.info(
                f"INIT: Configuring Gemini ({tier.model_name}) with key: [{key_preview}] (len: {len(tier.api_key)})"
            )

            genai.configure(api_key=tier.api_key)
            tier.model = genai.GenerativeModel(tier.model_name)
        except Exception as e:
            logger.error(f"Failed to init Gemini tier ({tier.model_name}): {e}")

    def _init_huggingface_tier(self, tier: AITier):
        try:
            from huggingface_hub import InferenceClient

            if not tier.api_key:
                return
            tier.model = InferenceClient(api_key=tier.api_key)
        except Exception as e:
            logger.error(f"Failed to init HuggingFace tier ({tier.model_name}): {e}")

    def _init_groq_tier(self, tier: AITier):
        try:
            import groq
            if not tier.api_key:
                return
            tier.model = "lazy_init"
        except Exception as e:
            logger.error(f"Failed to init Groq tier ({tier.model_name}): {e}")

    async def _with_retries_and_timeout(
        self, operation_name: str, operation: Callable[[], Awaitable[T]]
    ) -> T:
        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                return await asyncio.wait_for(operation(), timeout=self.request_timeout_seconds)
            except Exception as exc:
                last_error = exc
                logger.warning(f"{operation_name} attempt {attempt} failed: {exc}")
                if attempt < self.max_retries:
                    await asyncio.sleep(self.retry_base_delay_seconds * (2 ** (attempt - 1)))
        raise last_error or RuntimeError(f"{operation_name} failed")

    async def _call_ollama(
        self, tier: AITier, prompt: str, system_instruction: str | None = None
    ) -> str:
        """Call local Ollama server"""
        if not tier.base_url:
            raise ValueError("Ollama base URL not configured")

        url = f"{tier.base_url.rstrip('/')}/api/generate"
        logger.info(f"OLLAMA: Calling {url} with model {tier.model_name}")
        temp = 0.2 if tier.reasoning_level == "low" else 0.7
        payload = {
            "model": tier.model_name,
            "prompt": prompt,
            "system": system_instruction,
            "stream": False,
            "options": {"temperature": temp},
        }

        try:
            async with httpx.AsyncClient(timeout=self.request_timeout_seconds) as client:
                response = await client.post(url, json=payload)
                if response.status_code != 200:
                    logger.error(
                        f"OLLAMA ERROR: Server returned status {response.status_code}: {response.text}"
                    )
                response.raise_for_status()
                data = response.json()
                return data.get("response", "")
        except Exception as e:
            logger.error(f"OLLAMA CRITICAL ERROR: {e!s}")
            raise

    def _extract_polished_answer(self, text: str) -> str:
        """Surgically extract the final answer from reasoning/meta-talk."""
        if not text:
            return ""

        # 0. Try strict JSON parse first (Chat enforces JSON schema)
        import json

        try:
            # Look for JSON block within markdown
            json_match = re.search(
                r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL | re.IGNORECASE
            )
            if json_match:
                parsed = json.loads(json_match.group(1))
                if "final_answer" in parsed:
                    return str(parsed["final_answer"]).strip()
                elif "title" in parsed:
                    return str(parsed["title"]).strip()

            # Fallback: Look for the outermost curly braces anywhere in the text
            brace_match = re.search(r"(\{.*\})", text, flags=re.DOTALL)
            if brace_match:
                parsed = json.loads(brace_match.group(1))
                if "final_answer" in parsed:
                    return str(parsed["final_answer"]).strip()
                elif "title" in parsed:
                    return str(parsed["title"]).strip()

            # Legacy fallback for perfectly formatted clean text without braces
            clean_text = text.strip()
            parsed = json.loads(clean_text)
            if isinstance(parsed, list):
                return json.dumps(parsed)
            if "final_answer" in parsed:
                return str(parsed["final_answer"]).strip()
            elif "title" in parsed:
                return str(parsed["title"]).strip()
        except Exception:
            pass

        # Try to extract a JSON array directly if the above failed
        try:
            end = text.rfind("]")
            if end != -1:
                count = 0
                for i in range(end, -1, -1):
                    if text[i] == "]":
                        count += 1
                    elif text[i] == "[":
                        count -= 1
                        if count == 0:
                            parsed = json.loads(text[i : end + 1])
                            if isinstance(parsed, list):
                                return json.dumps(parsed)
        except Exception:
            pass

        # 1. Clean explicit tags
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
        text = re.sub(r"<\|channel\|>thought.*?<channel\|>", "", text, flags=re.DOTALL)
        text = re.sub(r"<\|thought\|>.*?</\|thought\|>", "", text, flags=re.DOTALL)
        text = text.replace("<think>", "").replace("</think>", "")
        text = (
            text.replace("<|channel|>thought", "")
            .replace("<channel|>", "")
            .replace("<|thought|>", "")
            .replace("</|thought|>", "")
        )

        # 2. Extract strictly bounded XML answer first
        xml_match = re.search(
            r"<FINAL_ANSWER>(.*?)</FINAL_ANSWER>", text, flags=re.DOTALL | re.IGNORECASE
        )
        if xml_match:
            candidate = xml_match.group(1).strip()
            if len(candidate) > 5:
                return candidate

        # 2.5 Extract strictly bounded ===START=== and ===END=== markers if present
        if "===START===" in text or "===END===" in text:
            candidate = None
            if "===START===" in text and "===END===" in text:
                # Find the pair of ===START=== and ===END=== that contains the most content
                best_candidate = None
                start_idx = 0
                while True:
                    start_pos = text.find("===START===", start_idx)
                    if start_pos == -1:
                        break
                    end_pos = text.find("===END===", start_pos + 11)
                    if end_pos == -1:
                        break
                    cand = text[start_pos + 11 : end_pos].strip()
                    if best_candidate is None or len(cand) > len(best_candidate):
                        best_candidate = cand
                    start_idx = start_pos + 11
                if best_candidate is not None:
                    candidate = best_candidate

            if candidate is None:
                # Fallback if we only have one of them or the pair extraction failed
                if "===START===" in text:
                    # Look for the longest segment after any ===START===
                    for part in reversed(text.split("===START===")):
                        part_stripped = part.strip()
                        if len(part_stripped) > 50:
                            candidate = part_stripped
                            break
                    if candidate is None:
                        # If all segments are small, just take the last one
                        candidate = text.split("===START===")[-1].strip()
                else:
                    candidate = text.split("===END===", 1)[0].strip()

            # Clean up potential leading/trailing markdown code blocks
            if candidate.startswith("```markdown"):
                candidate = candidate[11:].strip()
            elif candidate.startswith("```"):
                candidate = candidate[3:].strip()
            if candidate.endswith("```"):
                candidate = candidate[:-3].strip()
            return candidate

        # 3. Fallback extraction markers (strongest signal)
        for marker in [
            "FINAL_ANSWER:",
            "FINAL ANSWER:",
            "===START===",
            "Final Answer:",
            "Answer:",
            "ANSWER:",
        ]:
            if marker in text:
                parts = text.split(marker)
                if len(parts) > 1:
                    candidate = parts[-1].strip()
                    if len(candidate) > 5:
                        return candidate

        # 4. Detect and skip reasoning blocks (Look from bottom up)
        if "Context:" in text[:400] or "Question:" in text[:400] or "Wait," in text[:200]:
            lines = text.split("\n")
            meta_keywords = [
                "Context:",
                "Question:",
                "Constraint:",
                "Task:",
                "Wait,",
                "Actually,",
                "Let me",
                "Draft",
                "Final Check",
                "Check constraints",
                "Let's check",
                "Final version:",
            ]

            for i in range(len(lines) - 1, -1, -1):
                clean = lines[i].strip()
                if not clean:
                    continue
                is_meta = any(k in clean for k in meta_keywords)
                if (
                    not is_meta
                    and len(clean) > 25
                    and clean[0].isupper()
                    and not clean.endswith(":")
                ):
                    start_idx = i
                    while start_idx > 0:
                        prev = lines[start_idx - 1].strip()
                        if not prev:
                            start_idx -= 1
                            continue
                        if any(k in prev for k in meta_keywords):
                            break
                        start_idx -= 1
                    return "\n".join(lines[start_idx:]).strip()

        return text.strip()

    async def _generate_with_tier(
        self,
        tier: AITier,
        prompt: str,
        max_tokens: int,
        system_instruction: str | None = None,
        raw_output: bool = False,
    ) -> str:
        """Helper to generate text using a specific tier"""
        # Validation
        if tier.provider == "gemini" and not tier.model:
            raise ValueError(f"Gemini model not initialized for {tier.model_name}")

        # Reasoning handling
        is_reasoning = tier.reasoning_level == "high"
        if tier.provider == "gemini" and is_reasoning:
            instr = f"\nREASONING DEPTH: {tier.reasoning_level.upper()}\n"
            modified_prompt = (
                prompt.replace("===START===", instr + "===START===")
                if "===START===" in prompt
                else instr + prompt
            )
        else:
            modified_prompt = prompt

        if tier.provider == "gemini":
            import google.generativeai as genai

            logger.info(f"== AI REQUEST (Gemini - {tier.model_name}) ==\nSystem: {system_instruction}\nPrompt (first 1000 chars): {modified_prompt[:1000]}...\n")

            # CRITICAL: Re-configure with THIS tier's key to prevent leakage from other tiers
            if tier.api_key:
                genai.configure(api_key=tier.api_key)

            cfg = genai.types.GenerationConfig(max_output_tokens=max_tokens, temperature=0.7)
            active_model = (
                genai.GenerativeModel(tier.model.model_name, system_instruction=system_instruction)
                if system_instruction
                else tier.model
            )

            async def _gemini_call():
                def _sync_stream():
                    response = active_model.generate_content(
                        modified_prompt, generation_config=cfg, stream=True
                    )
                    full_text = ""
                    for chunk in response:
                        if chunk.text:
                            full_text += chunk.text
                            logger.info(chunk.text, extra={"stream_token": True})
                    return full_text
                return await asyncio.to_thread(_sync_stream)

            res = await self._with_retries_and_timeout(f"gemini_{tier.model_name}", _gemini_call)
            
            self.last_successful_tier = tier
            logger.info("\n")
            logger.info(
                f"SUCCESS: Generation completed using Tier {tier.provider} ({tier.model_name})"
            )
            
            return res if raw_output else self._extract_polished_answer(res)

        elif tier.provider == "ollama":
            logger.info(f"== AI REQUEST (Ollama - {tier.model_name}) ==\nSystem: {system_instruction}\nPrompt (first 1000 chars): {modified_prompt[:1000]}...\n")

            async def _ollama_call():
                return await self._call_ollama(tier, modified_prompt, system_instruction)

            res = await self._with_retries_and_timeout(f"ollama_{tier.model_name}", _ollama_call)
            logger.info(f"== AI RESPONSE (Ollama - {tier.model_name}) ==\n{res[:1000]}...\n")
            self.last_successful_tier = tier
            logger.info(
                f"SUCCESS: Generation completed using Tier {tier.provider} ({tier.model_name})"
            )
            return res if raw_output else self._extract_polished_answer(res)

        elif tier.provider == "huggingface":
            if not tier.model:
                raise ValueError(f"Huggingface model not initialized for {tier.model_name}")

            async def _hf_call():
                return tier.model.text_generation(
                    modified_prompt,
                    max_new_tokens=max_tokens,
                    system_instruction=system_instruction,
                )

            res = await self._with_retries_and_timeout(f"hf_{tier.model_name}", _hf_call)
            self.last_successful_tier = tier
            return res if raw_output else self._extract_polished_answer(res)

        elif tier.provider == "groq":
            if not tier.model:
                raise ValueError(f"Groq model not initialized for {tier.model_name}")
            logger.info(f"== AI REQUEST (Groq - {tier.model_name}) ==\nSystem: {system_instruction}\nPrompt (first 1000 chars): {modified_prompt[:1000]}...\n")

            async def _groq_call():
                from groq import AsyncGroq
                client = AsyncGroq(api_key=tier.api_key)
                try:
                    messages = []
                    if system_instruction:
                        messages.append({"role": "system", "content": system_instruction})
                    messages.append({"role": "user", "content": modified_prompt})

                    # Cap max_tokens to avoid exceeding Groq free-tier TPM limits.
                    # 6000 is safe for most tasks; the 8192 hard limit is per-request.
                    safe_max_tokens = min(max_tokens, 6000)

                    res = await client.chat.completions.create(
                        model=tier.model_name,
                        messages=messages,
                        max_tokens=safe_max_tokens,
                        temperature=0.7,
                        stream=True,
                    )
                    full_text = ""
                    async for chunk in res:
                        if chunk.choices and chunk.choices[0].delta.content:
                            text_chunk = chunk.choices[0].delta.content
                            full_text += text_chunk
                            logger.info(text_chunk, extra={"stream_token": True})
                    return full_text
                finally:
                    await client.close()

            res = await self._with_retries_and_timeout(f"groq_{tier.model_name}", _groq_call)
            
            self.last_successful_tier = tier
            logger.info("\n")
            logger.info(
                f"SUCCESS: Generation completed using Tier {tier.provider} ({tier.model_name})"
            )
            return res if raw_output else self._extract_polished_answer(res)

        raise ValueError(f"Generation fell through for provider: {tier.provider}")

    async def generate_text(
        self,
        prompt: str,
        max_tokens: int = 500,
        system_instruction: str | None = None,
        raw_output: bool = False,
        require_reasoning: bool = False,
    ) -> str:
        """Unary generation with task-specific fallback logic."""
        last_error = None

        tiers_to_use = self.tiers
        if require_reasoning:
            high_reasoning_tiers = [t for t in self.tiers if t.reasoning_level.lower() == "high"]
            if high_reasoning_tiers:
                tiers_to_use = high_reasoning_tiers

        for i, tier in enumerate(tiers_to_use):
            try:
                logger.info(
                    f"Attempting generation with Tier {i + 1} ({tier.provider}: {tier.model_name})"
                )
                return await self._generate_with_tier(
                    tier, prompt, max_tokens, system_instruction, raw_output
                )
            except Exception as e:
                err_str = str(e)
                # 413 from Groq means the prompt is too large for the free TPM limit.
                # No point retrying — skip immediately to next tier.
                if tier.provider == "groq" and ("413" in err_str or "rate_limit_exceeded" in err_str or "Request too large" in err_str):
                    logger.warning(f"Tier {i + 1} (groq) skipped: prompt too large for free TPM limit, falling through to next tier")
                else:
                    logger.error(f"Tier {i + 1} ({tier.provider}) failed: {e}")
                last_error = e
                continue  # Try next tier

        logger.error("All AI tiers failed to generate text.")
        raise Exception(f"All AI tiers failed. Last error: {last_error}")

    async def stream_text(
        self, 
        prompt: str, 
        max_tokens: int = 500, 
        system_instruction: str | None = None,
        require_reasoning: bool = False,
    ):
        """Stream generation with task-specific fallback logic."""
        last_error = None

        tiers_to_use = self.tiers
        if require_reasoning:
            high_reasoning_tiers = [t for t in self.tiers if t.reasoning_level.lower() == "high"]
            if high_reasoning_tiers:
                tiers_to_use = high_reasoning_tiers

        for i, tier in enumerate(tiers_to_use):
            try:
                logger.info(
                    f"Attempting stream with Tier {i + 1} ({tier.provider}: {tier.model_name})"
                )

                # Special handling for streaming-capable providers
                if tier.provider == "gemini":
                    if not tier.model:
                        raise ValueError("Gemini model not initialized")

                    is_reasoning = (
                        "gemma-4" in tier.model_name.lower() or tier.reasoning_level == "high"
                    )
                    if is_reasoning:
                        instr = f"\nREASONING DEPTH: {tier.reasoning_level.upper()}\n"
                        modified_prompt = (
                            prompt.replace("===START===", instr + "===START===")
                            if "===START===" in prompt
                            else instr + prompt
                        )
                    else:
                        modified_prompt = prompt

                    import google.generativeai as genai

                    # CRITICAL: Re-configure with THIS tier's key to prevent leakage from other tiers
                    if tier.api_key:
                        genai.configure(api_key=tier.api_key)

                    cfg = genai.types.GenerationConfig(
                        max_output_tokens=max_tokens, temperature=0.7
                    )
                    active_model = (
                        genai.GenerativeModel(
                            tier.model.model_name, system_instruction=system_instruction
                        )
                        if system_instruction
                        else tier.model
                    )

                    async def _gemini_stream():
                        return await asyncio.to_thread(
                            active_model.generate_content,
                            modified_prompt,
                            generation_config=cfg,
                            stream=True,
                        )

                    response_stream = await self._with_retries_and_timeout(
                        f"Tier{i + 1}_gemini_stream", _gemini_stream
                    )
                    all_parts = []
                    for chunk in response_stream:
                        if chunk.candidates and chunk.candidates[0].content.parts:
                            for part in chunk.candidates[0].content.parts:
                                if hasattr(part, "text"):
                                    all_parts.append(part.text)

                    self.last_successful_tier = tier
                    yield self._extract_polished_answer("".join(all_parts))
                    return  # Success!

                elif tier.provider == "groq":
                    if not tier.model:
                        raise ValueError("Groq model not initialized")

                    is_reasoning = (
                        "versatile" in tier.model_name.lower() or tier.reasoning_level == "high"
                    )
                    if is_reasoning:
                        instr = f"\nREASONING DEPTH: {tier.reasoning_level.upper()}\n"
                        modified_prompt = (
                            prompt.replace("===START===", instr + "===START===")
                            if "===START===" in prompt
                            else instr + prompt
                        )
                    else:
                        modified_prompt = prompt

                    async def _groq_stream():
                        from groq import AsyncGroq
                        client = AsyncGroq(api_key=tier.api_key)
                        try:
                            messages = []
                            if system_instruction:
                                messages.append({"role": "system", "content": system_instruction})
                            messages.append({"role": "user", "content": modified_prompt})

                            # Cap max_tokens to avoid exceeding Groq free-tier TPM limits.
                            safe_max_tokens = min(max_tokens, 6000)

                            stream = await client.chat.completions.create(
                                model=tier.model_name,
                                messages=messages,
                                max_tokens=safe_max_tokens,
                                temperature=0.7,
                                stream=True,
                            )
                            
                            all_parts = []
                            async for chunk in stream:
                                if (
                                    chunk.choices
                                    and len(chunk.choices) > 0
                                    and chunk.choices[0].delta.content is not None
                                ):
                                    all_parts.append(chunk.choices[0].delta.content)
                            return all_parts
                        finally:
                            await client.close()

                    all_parts = await self._with_retries_and_timeout(
                        f"Tier{i + 1}_groq_stream", _groq_stream
                    )

                    self.last_successful_tier = tier
                    yield self._extract_polished_answer("".join(all_parts))
                    return  # Success!

                else:
                    # For non-streaming or fallback, use the tier-specific unary call
                    res = await self._generate_with_tier(
                        tier, prompt, max_tokens, system_instruction
                    )
                    if res:
                        yield res
                        return
                    else:
                        raise ValueError("Empty response from tier")

            except Exception as e:
                logger.error(f"Tier {i + 1} stream failed: {e}")
                last_error = e
                continue

        raise Exception(f"All AI tiers failed. Last error: {last_error}")

    async def answer_question(
        self,
        context: str,
        question: str,
        system_prompt: str | None = None,
        require_reasoning: bool = False,
    ) -> str:
        if system_prompt:
            return await self.generate_text(
                prompt=question, max_tokens=8192, system_instruction=system_prompt, raw_output=True, require_reasoning=require_reasoning
            )
        prompt = f"Context:\n{context}\n\nQuestion:\n{question}\n\nAnswer:"
        return await self.generate_text(prompt, max_tokens=8192, raw_output=True)

    async def generate_summary(
        self,
        content: str,
        mode: str = "elaborate",
        output_format: str = "sentence",
        processing_method: str = "whole",
        split_level: str = "h2",
        custom_prompt: str | None = None,
        progress_callback: Callable[[int], None] | None = None,
    ) -> str:
        """
        Generate a summary using parallel chunked processing via SummaryPipeline.
        """
        from app.processing.summary_pipeline import SummaryPipeline

        pipeline = SummaryPipeline(self)
        return await pipeline.generate_summary(
            content,
            mode,
            output_format,
            processing_method=processing_method,
            split_level=split_level,
            custom_prompt=custom_prompt,
            progress_callback=progress_callback,
        )


def get_ai_client(user: User | None = None, db: Session | None = None) -> AIClient:
    return AIClient(user=user, db=db)
