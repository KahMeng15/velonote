"""Chat/Q&A endpoints with conversation threading and AI response modes"""

import asyncio
import json
import logging
import time

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, field_validator
from sqlalchemy import Integer, cast, func
from sqlalchemy.orm import Session

from app.models.db import ChatMessage, Resource, Subject, SubjectGroup, User
from app.processing.ai_client import AIClient
from app.utils.auth import get_current_user
from app.utils.db import generate_conversation_id, generate_random_id, get_db
from app.utils.quotas import (
    check_quota_conversations,
    enforce_quota_messages,
    get_user_conversation_count,
    get_user_tier_config,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])


# ─────────────────────────────────────────────────────────────────────────────
# Pydantic Models
# ─────────────────────────────────────────────────────────────────────────────


class ChatRequest(BaseModel):
    resource_id: str | None = None
    subject_id: str | None = None
    group_id: str | None = None
    exercise_id: str | None = None
    message: str
    ai_mode: str = "elaborate"
    output_format: str = "sentence"
    conversation_id: str | None = None
    auto_detect_conversation: bool = True  # Auto-detect if this is a conversation continuation
    reply_to_message_id: str | None = None  # Reply to a specific message in conversation


class ChatMessageResponse(BaseModel):
    id: str
    message: str
    response: str
    sources: list = []
    detailed_sources: list = []
    created_at: str
    resource_id: str | None = None
    subject_id: str | None = None
    group_id: str | None = None
    exercise_id: str | None = None
    ai_mode: str | None = None
    output_format: str | None = None
    ai_model: str | None = None
    conversation_id: str | None = None
    conversation_title: str | None = None
    reply_to_message_id: str | None = None
    timings: dict | None = None
    rating: int | None = None
    rating_comment: str | None = None

    @field_validator("id", "conversation_id", "reply_to_message_id", mode="before")
    @classmethod
    def coerce_to_str(cls, v):
        if v is None:
            return v
        return str(v)


class ConversationSummary(BaseModel):
    conversation_id: str
    title: str
    message_count: int
    last_message_at: str
    resource_id: str | None = None
    subject_id: str | None = None
    group_id: str | None = None
    exercise_id: str | None = None
    scope_type: str | None = None
    is_pinned: bool = False
    is_favourite: bool = False

    @field_validator("conversation_id", mode="before")
    @classmethod
    def coerce_to_str(cls, v):
        if v is None:
            return v
        return str(v)


class ChatResponse(BaseModel):
    message: str
    response: str
    sources: list = []
    timings: dict | None = None
    ai_mode: str | None = None
    output_format: str | None = None
    ai_model: str | None = None
    detailed_sources: list | None = []
    conversation_id: str | None = None
    conversation_title: str | None = None
    reply_to_message_id: str | None = None

    @field_validator("conversation_id", "reply_to_message_id", mode="before")
    @classmethod
    def coerce_to_str(cls, v):
        if v is None:
            return v
        return str(v)


# ─────────────────────────────────────────────────────────────────────────────
# AI Mode Definitions and Prompt Builder
# ─────────────────────────────────────────────────────────────────────────────

AI_MODES = {
    "quick": {
        "label": "Quick",
        "icon": "ph-lightning",
        "description": "Use less processing to get answer",
    },
    "simple": {
        "label": "Simple",
        "icon": "ph-text-a-underline",
        "description": "Answer in simple terms",
    },
    "normal": {
        "label": "Normal",
        "icon": "ph-stack",
        "description": "A balanced response with standard detail",
    },
    "elaborate": {
        "label": "Elaborate",
        "icon": "ph-lightbulb",
        "description": "Provide thorough explanation",
    },
    "eli5": {"label": "ELI5", "icon": "ph-smiley", "description": "Explain like I'm 5"},
}

OUTPUT_FORMATS = {
    "sentence": "Single paragraph response",
    "pointform": "Bullet point format",
    "numbered_list": "Numbered list format",
    "table": "Table format",
}

_BASE_GUARD = (
    "CRITICAL: Answer ONLY using the provided context. "
    'If the answer is NOT found in the context, respond with EXACTLY AND ONLY: "I am unable to find any information based on your question." '
    "Do NOT make up facts, hallucinate information, or guess. "
    "Never provide information outside the provided context."
)


def build_mode_prompt(
    context: str,
    question: str,
    mode: str,
    output_format: str = "sentence",
    is_web_search: bool = False,
    conversation_context: str = "",
) -> str:
    """Return the full system prompt based on AI mode and output format."""
    if question.strip().lower() in {"hi", "hello", "how are you", "how are you?"}:
        return f"""You are a friendly assistant. Respond warmly.
CRITICAL: You MUST output your response using the following XML format:
<reasoning>
Internal thoughts
</reasoning>
<FINAL_ANSWER>
Hello! How can I help you today?
</FINAL_ANSWER>
Question: '{question}'"""

    # Base mode instructions with STRICTER constraints
    mode_instructions = {
        "quick": "CRITICAL TONE: Extract the most important facts concisely. Do not add fluff.",
        "simple": "CRITICAL TONE: Explain using extremely simple, plain English. Avoid all technical jargon. Imagine explaining this to someone who has never touched a computer.",
        "normal": "CRITICAL TONE: Provide a balanced, clear, and informative response.",
        "elaborate": "CRITICAL TONE: Provide a thorough, detailed, and well-structured explanation.",
        "eli5": "CRITICAL TONE: Explain this EXACTLY as if you are talking to a 5-year-old child! You MUST invent a fun, everyday analogy (like toys, animals, or food) to explain the concept. Use extremely simple words.",
    }

    # Output format instructions
    output_instructions = {
        "sentence": "CRITICAL OUTPUT FORMAT: You MUST respond using complete sentences in standard paragraph format.",
        "pointform": "CRITICAL OUTPUT FORMAT: Please utilize a Markdown bulleted list to organize your points, but you may use normal introductory sentences before the list.",
        "numbered_list": "CRITICAL OUTPUT FORMAT: Please utilize a Markdown numbered list to organize your points, but you may use normal introductory sentences before the list.",
        "table": "CRITICAL OUTPUT FORMAT: Please utilize a Markdown table for structured data, but you MUST use normal sentences and bullet points outside the table to explain things naturally.",
        "mix": "CRITICAL OUTPUT FORMAT: You MUST use a mix of normal sentences, bullet points, and tables where appropriate to explain the concepts thoroughly. IMPORTANT: You MUST place at least two blank newlines before and after any Markdown table or list so they render correctly.",
    }

    mode_inst = mode_instructions.get(mode, mode_instructions["elaborate"])
    output_inst = output_instructions.get(output_format, output_instructions["sentence"])

    guard = _BASE_GUARD
    if mode == "eli5":
        guard = (
            "CRITICAL: Base your factual answer on the provided context blocks. "
            "You may invent simple, everyday analogies to explain the concepts, but the core facts must come from the context. "
            'If the factual answer is NOT found in the context, respond in <FINAL_ANSWER> with EXACTLY AND ONLY: "Sorry, I am unable to find any answers for your question based on the context."'
        )
    elif is_web_search:
        guard = (
            "CRITICAL: Answer using ONLY the web search snippets provided. "
            "Do NOT add external knowledge. "
            'If the answer is NOT found in snippets, respond in <FINAL_ANSWER> with EXACTLY AND ONLY: "Sorry, I am unable to find any answers for your question based on the context." '
            "Never hallucinate or guess."
        )
    else:
        guard = (
            "CRITICAL: Answer ONLY using the provided context blocks (e.g. [Source 1]: ...). "
            'If the answer is NOT found in the context, respond in <FINAL_ANSWER> with EXACTLY AND ONLY: "Sorry, I am unable to find any answers for your question based on the context." '
            "Do NOT make up facts, hallucinate information, or guess. "
            "Never provide information outside the provided context."
        )

    prompt = f"""{mode_inst}

{guard}

{output_inst}

CRITICAL:
You MUST output your response using the exact XML structure below. Do not include any other text before or after.

<reasoning>
[Your internal thoughts, constraint checks, and task analysis here]
</reasoning>
<FINAL_ANSWER>
[Your polished final answer in the requested output format here]
</FINAL_ANSWER>

INSTRUCTIONS FOR <reasoning>:
1. Analyze the user's question.
2. Scan the provided context blocks. Does the context actually contain the answer? (State YES or NO)
3. If NO: You MUST stop and output exactly "Sorry, I am unable to find any answers for your question based on the context." in the <FINAL_ANSWER> block.
4. If YES: Plan your answer format and tone.

RULES FOR <FINAL_ANSWER>:
- NO introductory phrases like "Based on...", "Let me explain...", "Here's what..."
- Follow the requested output format EXACTLY. If a table is requested, you must output a markdown table.
- PARAPHRASE the context in your own words—do NOT copy-paste source text
- Do NOT include author names or dates in the answer
- ALWAYS cite the specific source you used by inserting [1], [2], etc. inside your text where appropriate.
- You MUST wrap your citations in square brackets exactly like this: [1] or [1][2]. Do NOT use bare numbers.
- Synthesize information from MULTIPLE sources when possible to provide a comprehensive answer, citing all of them.
- Do NOT make up your own citations. ONLY use the [Source X] numbers provided in the context blocks.
- If you found the answer, provide IT and NOTHING ELSE. Do NOT append apologies to a valid answer.
- Never add information outside the provided context
- Check facts twice before responding
"""

    if conversation_context:
        prompt += f"""
<previous_conversation>
{conversation_context}
</previous_conversation>
"""

    prompt += f"""
<context>
{context}
</context>

<question>
{question}
</question>

Respond with the exact XML format now. Ensure your <FINAL_ANSWER> strictly follows the "{output_format}" format, and remember to follow your tone instructions: {mode_inst}"""

    return prompt


async def classify_query(client: AIClient, question: str) -> str:
    """Classify the user intent to avoid unnecessary retrieval or off-topic web searches."""
    prompt = (
        "Classify this user query into strictly one of three categories:\n"
        "1. CONVERSATIONAL: Simple greetings, praise, thanks, goodbyes, or small talk (e.g. 'hello', 'thanks', 'how are you').\n"
        "2. OFF_TOPIC: Requests completely unrelated to computer science, programming, or general academic study (e.g. asking for recipes, writing poems, pop culture, politics, 'who is donald trump').\n"
        "3. INFORMATIONAL_DOMAIN: Questions asking for facts, explanations, summaries, or knowledge related to computer science, study resources, or general educational topics.\n\n"
        "Reply with EXACTLY ONE WORD: CONVERSATIONAL, OFF_TOPIC, or INFORMATIONAL_DOMAIN."
    )
    try:
        res = await asyncio.wait_for(
            client.answer_question(question=question, context="", system_prompt=prompt), timeout=3.0
        )
        res_upper = res.strip().upper()
        if "CONVERSATIONAL" in res_upper:
            return "CONVERSATIONAL"
        if "OFF_TOPIC" in res_upper:
            return "OFF_TOPIC"
        return "INFORMATIONAL_DOMAIN"
    except Exception:
        return "INFORMATIONAL_DOMAIN"  # Default to domain if classification fails


async def is_conversation_continuation(
    client: AIClient, current_question: str, last_question: str | None, last_answer: str | None
) -> bool:
    """Determine if the current question is a follow-up/continuation of the last conversation.

    Returns True if the question appears to be directly related to the last exchange.
    Examples:
    - Last: "What is photosynthesis?" → Current: "How does it work?" → True
    - Last: "Explain gravity" → Current: "Tell me about physics" → False (likely new topic)
    """
    if not last_question or not last_answer:
        return False  # No previous context = new conversation

    prompt = f"""Determine if the CURRENT question is a direct follow-up or continuation of the LAST Q&A exchange.

LAST QUESTION: {last_question}
LAST ANSWER (preview): {last_answer[:200]}...

CURRENT QUESTION: {current_question}

Is the CURRENT question a direct follow-up/continuation? Answer with EXACTLY ONE WORD: YES or NO.

Examples of YES:
- Last: "What is photosynthesis?" → Current: "How does it work?"
- Last: "Explain gravity" → Current: "Can you give more examples?"
- Last: "What's the capital of France?" → Current: "What about Germany?"

Examples of NO:
- Last: "What is photosynthesis?" → Current: "Tell me a joke"
- Last: "Explain photosynthesis" → Current: "Explain gravity instead"
- Last: "What's the weather?" → Current: "Unrelated question about cooking"
"""

    try:
        res = await asyncio.wait_for(
            client.answer_question(question=current_question, context="", system_prompt=prompt),
            timeout=3.0,
        )
        res_upper = res.strip().upper()
        return "YES" in res_upper
    except Exception:
        return False  # Default to new conversation if detection fails


def build_conversation_context(messages: list[ChatMessage], max_messages: int = 3) -> str:
    """Build formatted context from previous messages in the conversation.

    Returns a formatted string with the last N messages to include as context for the AI.
    """
    if not messages:
        return ""

    # Get the last N messages (most recent)
    recent_messages = messages[-max_messages:]

    context_parts = ["Previous conversation context:"]
    for i, msg in enumerate(recent_messages, 1):
        context_parts.append(f"\n[Message {i}]")
        context_parts.append(f"Q: {msg.message}")
        context_parts.append(f"A: {msg.response[:300]}...")  # Truncate long responses

    return "\n".join(context_parts)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def generate_conversation_title(first_question: str) -> str:
    """Derive a clean, readable conversation title from the first question (max 8 words)."""
    title = first_question.strip()
    if title.endswith("?"):
        title = title[:-1].strip()
    if title:
        title = title[0].upper() + title[1:]

    words = title.split()
    if len(words) > 8:
        title = " ".join(words[:8]) + "…"

    if len(title) > 80:
        truncated = title[:77]
        last_space = truncated.rfind(" ")
        title = (truncated[:last_space] if last_space > 50 else truncated) + "…"
    return title or "New Conversation"


async def web_search(query: str, timeout: float = 10.0) -> tuple:
    """Quick web search using ddgs with relevance filtering. Returns (snippet, sources_list, error_status).
    sources_list: list of {"url": url, "title": title, "text_preview": snippet, "relevance_score": %}
    error_status: None = success, 'timeout' = slow/taking too long, 'unavailable' = error (DDG down)
    """
    try:
        import asyncio

        from ddgs import DDGS

        def calculate_relevance(query_str: str, title: str, body: str) -> float:
            """Calculate realistic relevance score (0-100) based on semantic matching."""
            import re

            query_lower = query_str.lower()
            title_lower = title.lower()
            body_lower = body.lower()

            # Extract important query terms (>2 chars, not stop words) using regex to strip punctuation
            raw_query_words = re.findall(r"\b\w+\b", query_lower)
            query_words = [
                w
                for w in raw_query_words
                if len(w) > 2
                and w
                not in {
                    "what",
                    "this",
                    "that",
                    "with",
                    "from",
                    "into",
                    "have",
                    "been",
                    "does",
                    "is",
                    "a",
                    "an",
                    "the",
                }
            ]

            if not query_words:
                return 0.0

            score = 0.0

            # 1. Title relevance (60% weight) - very important
            title_matches = sum(1 for word in query_words if word in title_lower)
            title_score = (title_matches / len(query_words)) * 100 if query_words else 0
            score += title_score * 0.60

            # 2. Keyword density in body (20% weight)
            body_words = re.findall(r"\b\w+\b", body_lower)
            if body_words:
                keyword_count = sum(1 for word in body_words if word in query_words)
                density = keyword_count / len(body_words)
                # Non-linear: high density rewards are capped
                density_score = min(density * 150, 100)
                score += density_score * 0.35

            # 3. Phrase matching bonus (25% weight) - if keywords appear together
            phrase_bonus = 0
            for i in range(len(query_words) - 1):
                phrase = f"{query_words[i]} {query_words[i + 1]}"
                if phrase in body_lower or phrase in title_lower:
                    phrase_bonus += 15
            phrase_bonus = min(phrase_bonus, 100)
            score += phrase_bonus * 0.25

            # Cap at 100% and round
            return min(score, 100.0)

        def run_search():
            try:
                ddgs_instance = DDGS(timeout=5)
                return list(ddgs_instance.text(query, max_results=8))  # Get more to filter
            except Exception as e:
                print(f"[chat] DDGS error: {e}")
                return []

        try:
            results = await asyncio.wait_for(asyncio.to_thread(run_search), timeout=timeout)
        except TimeoutError:
            print(f"[chat] Web search timed out after {timeout}s")
            return "", [], "timeout"

        sources_list = []
        for r in results:
            body = r.get("body", "").strip()
            url = r.get("href", "")
            title = r.get("title", "")
            if body:
                # Calculate relevance score
                relevance = calculate_relevance(query, title, body)

                # Filter out low relevance results (< 50% with new algorithm)
                if relevance < 50.0:
                    print(
                        f"[chat] Skipping low-relevance result: {title[:50]}... (score: {relevance:.1f}%)"
                    )
                    continue

                print(f"[chat] Result: {title[:50]}... (relevance: {relevance:.1f}%)")

                # Store detailed source info with relevance
                sources_list.append(
                    {
                        "url": url,
                        "title": title,
                        "text_preview": body[:150] + "..." if len(body) > 150 else body,
                        "relevance_score": round(relevance, 1),
                    }
                )

        # Sort by relevance score descending
        sources_list.sort(key=lambda x: x["relevance_score"], reverse=True)

        print(f"[chat] DDGS retrieved {len(sources_list)} relevant snippets (relevance >= 20%)")
        if sources_list:
            # Reconstruct snippets from sorted sources
            snippets = [s["text_preview"].replace("...", "").strip() for s in sources_list[:5]]
            combined = "\n\n".join(snippets)
            return combined, sources_list[:5], None

        print("[chat] No relevant results found from DDGS")
        return "", [], None
    except Exception as e:
        import traceback

        print(f"[chat] Web search failed with Exception: {type(e).__name__}: {e}")
        traceback.print_exc()
        return "", [], "unavailable"


# ─────────────────────────────────────────────────────────────────────────────
# Citation Injection
# ─────────────────────────────────────────────────────────────────────────────


def inject_citations(response: str, detailed_sources: list[dict]) -> str:
    """
    Intelligently inject [1], [2], etc. citations into the response text.

    This function matches detailed_sources to relevant parts of the response
    and injects citation markers at the end of sentences (not in the middle).

    Args:
        response: AI-generated response text
        detailed_sources: List of source dictionaries with text_preview, score, etc.

    Returns:
        Response text with [1], [2], etc. citations injected
    """
    if not detailed_sources or not response:
        return response

    import re

    # Split response keeping the whitespace separators using a capture group
    # This preserves newlines and spacing perfectly.
    parts = re.split(r"((?<=[.!?])\s+)", response.strip())

    # parts looks like: [sentence1, whitespace1, sentence2, whitespace2, ...]
    sentences = parts[0::2]
    separators = parts[1::2]

    # Map each source to its best matching sentence
    sentence_citations = {}  # {sentence_index: citation_number}
    used_sources = set()

    for src_idx, source in enumerate(detailed_sources[:10]):  # Limit to 10 sources
        if src_idx in used_sources:
            continue

        citation_num = src_idx + 1
        source_preview = source.get("text_preview", "").lower()

        if not source_preview or len(source_preview) < 3:
            continue

        # Find the sentence with best keyword overlap with this source
        best_sentence_idx = -1
        best_overlap = 0

        for sent_idx, sentence in enumerate(sentences):
            if sent_idx in sentence_citations:
                continue  # Already cited this sentence

            sentence_lower = sentence.lower()

            # Extract key terms (words > 3 chars) from source, excluding common words
            key_terms = [
                w
                for w in re.findall(r"\b\w{3,}\b", source_preview)
                if w
                not in {
                    "the",
                    "and",
                    "for",
                    "are",
                    "was",
                    "were",
                    "been",
                    "have",
                    "that",
                    "this",
                    "with",
                    "from",
                    "into",
                    "can",
                    "your",
                    "will",
                    "also",
                }
            ]

            if not key_terms:
                continue

            # Count how many key terms appear in the sentence
            overlap = sum(1 for term in key_terms if term in sentence_lower)

            # Require at least 40% of key terms to match
            match_percentage = (overlap / len(key_terms)) * 100 if key_terms else 0

            if match_percentage >= 40 and overlap > best_overlap:
                best_overlap = overlap
                best_sentence_idx = sent_idx

        # If we found a matching sentence, add citation to it
        if best_sentence_idx >= 0 and best_overlap > 0:
            sentence_citations[best_sentence_idx] = citation_num
            used_sources.add(src_idx)

    # Rebuild response with citations placed at the end of sentences
    cited_parts = []
    for sent_idx, sentence in enumerate(sentences):
        # Don't inject citation if the sentence looks like a markdown table row (starts/ends with |)
        is_table_row = bool(re.search(r"^\s*\|.*\|\s*$", sentence, re.MULTILINE))

        if sent_idx in sentence_citations and not is_table_row:
            citation_num = sentence_citations[sent_idx]

            if sentence and sentence[-1] in ".!?":
                sentence = sentence[:-1] + f" [{citation_num}]{sentence[-1]}"
            else:
                sentence = sentence + f" [{citation_num}]"

        cited_parts.append(sentence)
        if sent_idx < len(separators):
            cited_parts.append(separators[sent_idx])

    return "".join(cited_parts)


# ─────────────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/ask", response_model=dict)
async def ask_question(
    request: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Ask a question as a background task."""

    # Enforce tier quotas
    enforce_quota_messages(current_user, db)

    # Check conversation quota if creating a new conversation
    if not request.conversation_id and request.auto_detect_conversation:
        if not check_quota_conversations(current_user, db):
            tier_config = get_user_tier_config(current_user, db)
            current = get_user_conversation_count(current_user, db)
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Conversation quota exceeded. Your {current_user.tier.upper()} tier allows {tier_config.max_conversations} conversations. You have {current}.",
            )

    task_id = f"chat_{current_user.id}_{int(time.time())}"
    from app.utils.tasks import TaskManager

    TaskManager.submit_task(
        task_id,
        "chat_response",
        current_user.id,
        message=request.message,
        resource_id=request.resource_id,
        subject_id=request.subject_id,
        group_id=request.group_id,
        exercise_id=request.exercise_id,
        ai_mode=request.ai_mode,
        output_format=request.output_format,
        conversation_id=request.conversation_id,
        auto_detect_conversation=request.auto_detect_conversation,
        reply_to_message_id=request.reply_to_message_id,
    )

    return {"task_id": task_id, "status": "pending"}


async def ask_question_logic(**kwargs) -> dict:
    """Core logic for asking a question, moved from the endpoint for background task support."""
    from app.utils.db import SessionLocal

    db = SessionLocal()
    try:
        user_id = kwargs.get("user_id")
        message = kwargs.get("message")
        resource_id = kwargs.get("resource_id")
        subject_id = kwargs.get("subject_id")
        group_id = kwargs.get("group_id")
        exercise_id = kwargs.get("exercise_id")
        ai_mode = kwargs.get("ai_mode", "elaborate")
        output_format = kwargs.get("output_format", "sentence")
        conversation_id = kwargs.get("conversation_id")
        auto_detect_conversation = kwargs.get("auto_detect_conversation", True)
        reply_to_message_id = kwargs.get("reply_to_message_id")

        current_user = db.query(User).filter(User.id == user_id).first()
        if not current_user:
            raise ValueError("User not found")

        t_start = time.time()
        step_times = {f"step{i}": 0.0 for i in range(1, 10)}
        target_resource_ids = []
        sources = []

        # Identical logic to previous endpoint follows...
        if resource_id:
            resource = (
                db.query(Resource)
                .filter(Resource.id == resource_id, Resource.user_id == user_id)
                .first()
            )
            if resource:
                target_resource_ids = [resource_id]
                sources = [resource.title]

        elif subject_id:
            subject = (
                db.query(Subject)
                .filter(Subject.id == subject_id, Subject.user_id == user_id)
                .first()
            )
            if subject:
                resources = db.query(Resource).filter(Resource.subject_id == subject.id).all()
                target_resource_ids = [l.id for l in resources]
                sources = [l.title for l in resources]

        elif group_id:
            group = (
                db.query(SubjectGroup)
                .filter(SubjectGroup.id == group_id, SubjectGroup.user_id == user_id)
                .first()
            )
            if group:
                subjects = db.query(Subject).filter(Subject.group_id == group.id).all()
                for s in subjects:
                    resources = db.query(Resource).filter(Resource.subject_id == s.id).all()
                    target_resource_ids.extend([l.id for l in resources])
                    sources.extend([l.title for l in resources])
        else:
            resources = db.query(Resource).filter(Resource.user_id == user_id).all()
            target_resource_ids = [l.id for l in resources]
            sources = [l.title for l in resources]

        step_times["step1"] = round((time.time() - t_start) * 1000.0, 2)
        retrieval_ms = (time.time() - t_start) * 1000.0

        t_step2_start = time.time()
        ai_client = AIClient(current_user, db=db, category="chat")

        conv_id = conversation_id
        conversation_context = ""

        if auto_detect_conversation and not conversation_id:
            recent_messages = (
                db.query(ChatMessage)
                .filter(ChatMessage.user_id == user_id, ChatMessage.conversation_id.isnot(None))
                .order_by(ChatMessage.created_at.desc())
                .limit(1)
                .all()
            )

            if recent_messages:
                last_msg = recent_messages[0]
                try:
                    is_continuation = await is_conversation_continuation(
                        client=ai_client,
                        current_question=message,
                        last_question=last_msg.message,
                        last_answer=last_msg.response,
                    )

                    if is_continuation:
                        conv_id = last_msg.conversation_id
                        earlier_messages = (
                            db.query(ChatMessage)
                            .filter(
                                ChatMessage.conversation_id == conv_id,
                                ChatMessage.user_id == user_id,
                            )
                            .order_by(ChatMessage.created_at.desc())
                            .limit(2)
                            .all()
                        )

                        if earlier_messages:
                            conversation_context = build_conversation_context(earlier_messages)
                    else:
                        conv_id = generate_conversation_id(db)
                except Exception:
                    conv_id = generate_conversation_id(db)

        if not conv_id:
            conv_id = generate_conversation_id(db)

        chat_msg_id = generate_random_id(db, ChatMessage)
        chat_msg = ChatMessage(
            id=chat_msg_id,
            user_id=user_id,
            resource_id=resource_id,
            subject_id=subject_id,
            group_id=group_id,
            exercise_id=exercise_id,
            message=message,
            response="",
            sources="[]",
            conversation_id=conv_id,
            conversation_title="",
        )
        db.add(chat_msg)
        db.commit()

        step_times["step2"] = round((time.time() - t_step2_start) * 1000.0, 2)
        t_step3_start = time.time()

        intent = await classify_query(ai_client, message)
        step_times["step3"] = round((time.time() - t_step3_start) * 1000.0, 2)

        context = ""
        snippet_sources = []
        detailed_sources = []

        if intent == "CONVERSATIONAL":
            context = "User is just making conversation."
            prompt = f"""You are a friendly study assistant. Respond warmly to the user.
CRITICAL: You MUST output your response using the exact XML structure below:
<reasoning>
Internal thoughts about the appropriate conversational response.
</reasoning>
<FINAL_ANSWER>
Your friendly response here
</FINAL_ANSWER>
Question: {message}"""
        elif intent == "OFF_TOPIC":
            context = "User asking off-topic."
            prompt = """You MUST output EXACTLY AND ONLY this XML structure:
<reasoning>
The user asked a completely unrelated or off-topic question.
</reasoning>
<FINAL_ANSWER>
Sorry, I am here to help you study better and smarter with your resources. I am unable to answer questions unrelated to your studies or computer science!
</FINAL_ANSWER>"""
        else:
            t_step4_start = time.time()
            if target_resource_ids:
                try:
                    from app.processing.embeddings import retrieve_relevant_chunks

                    raw_chunks = retrieve_relevant_chunks(
                        query=message, resource_ids=target_resource_ids, db=db, top_k=5
                    )
                    # Filter for confident chunks (score >= 15.0)
                    chunks = [c for c in raw_chunks if c["score"] >= 15.0]

                    if chunks:
                        context = ""
                        for idx, chunk in enumerate(chunks):
                            if len(context) + len(chunk["text"]) > 3000:
                                break
                            context += f"[Source {idx + 1}]: {chunk['text']}\n\n"
                            detailed_sources.append(
                                {
                                    "text_preview": chunk["text"][:150],
                                    "position": chunk["position"],
                                    "score": chunk["score"],
                                    "resource_id": chunk["resource_id"],
                                }
                            )
                        # snippet_sources isn't used directly here for DB, wait, it might be.
                except Exception as e:
                    import logging

                    logging.getLogger(__name__).error(f"Error retrieving chunks: {e}")

            step_times["step4"] = round((time.time() - t_step4_start) * 1000.0, 2)

            time.time()
            step_times["step5"] = 0.0

            t_step6_start = time.time()
            has_web = any(s.get("is_web") for s in detailed_sources)
            prompt = build_mode_prompt(
                context or "No info",
                message,
                ai_mode,
                output_format,
                is_web_search=has_web,
                conversation_context=conversation_context,
            )
            step_times["step6"] = round((time.time() - t_step6_start) * 1000.0, 2)

        t_model_start = time.time()
        t_step7_start = time.time()

        ai_model_info = f"{ai_client.provider.upper()}"
        if ai_client.ai_model_name:
            ai_model_info += f" ({ai_client.ai_model_name})"

        if intent in ["CONVERSATIONAL", "OFF_TOPIC"]:
            raw_response = await ai_client.answer_question(
                question=message, context=context, system_prompt=prompt
            )
        else:
            needs_web_search = False
            if not context:
                needs_web_search = True
            else:
                raw_response = await ai_client.answer_question(
                    question=message, context=context, system_prompt=prompt
                )

                # Check if AI rejected the context in CoT or Final Answer
                import re

                reasoning_match = re.search(
                    r"<reasoning>(.*?)</reasoning>", raw_response, flags=re.DOTALL | re.IGNORECASE
                )
                if reasoning_match:
                    reasoning_text = reasoning_match.group(1).upper()
                    has_no = bool(re.search(r"\bNO\b", reasoning_text))
                    has_yes = bool(re.search(r"\bYES\b", reasoning_text))
                    if has_no and not has_yes:
                        needs_web_search = True

                if not needs_web_search:
                    final_answer_match = re.search(
                        r"<FINAL_ANSWER>\s*(.*?)\s*(?:</FINAL_ANSWER>|$)",
                        raw_response,
                        flags=re.DOTALL | re.IGNORECASE,
                    )
                    if final_answer_match:
                        ans = final_answer_match.group(1).strip().lower()
                        if (
                            "sorry" in ans
                            or "unable to find" in ans
                            or "no mention" in ans
                            or "not found" in ans
                        ):
                            needs_web_search = True

            if needs_web_search:
                t_web_start = time.time()
                web_snippet, web_sources, _web_error = await web_search(message, timeout=10.0)
                step_times["step5"] = round((time.time() - t_web_start) * 1000.0, 2)

                if web_snippet:
                    context = ""
                    detailed_sources.clear()
                    for idx, s in enumerate(web_sources):
                        context += f"[Source {idx + 1}]: {s.get('text_preview', '')}\n\n"
                        detailed_sources.append(
                            {
                                "text_preview": s.get("text_preview", ""),
                                "is_web": True,
                                "url": s.get("url", ""),
                                "title": s.get("title", "Web Source"),
                            }
                        )

                    has_web = True
                    prompt = build_mode_prompt(
                        context,
                        message,
                        ai_mode,
                        output_format,
                        is_web_search=has_web,
                        conversation_context=conversation_context,
                    )
                    raw_response = await ai_client.answer_question(
                        question=message, context=context, system_prompt=prompt
                    )
                else:
                    response_text = "Sorry, I am unable to find any answers for your question based on your resources or the web."
                    raw_response = f"<FINAL_ANSWER>\n{response_text}\n</FINAL_ANSWER>"

        # Parse the XML response to extract only the FINAL_ANSWER
        import re

        final_answer_match = re.search(
            r"<FINAL_ANSWER>\s*(.*?)\s*(?:</FINAL_ANSWER>|$)",
            raw_response,
            flags=re.DOTALL | re.IGNORECASE,
        )
        if final_answer_match:
            response = final_answer_match.group(1).strip()
        else:
            # Fallback if the model didn't use the tags
            response = raw_response.strip()
            # If it included reasoning but no final answer end tag, try to split
            if "<reasoning>" in response and "</reasoning>" in response:
                response = response.split("</reasoning>")[-1].strip()
                # Strip dangling <FINAL_ANSWER> tag just in case
                response = re.sub(r"^<FINAL_ANSWER>\s*", "", response, flags=re.IGNORECASE)

        # Fix markdown table formatting by ensuring blank lines before and after tables
        # First, remove leading indentation from markdown table rows to prevent them from rendering as code blocks
        response = re.sub(r"^[ \t]+(\|.*\|)", r"\1", response, flags=re.MULTILINE)

        # Then, only trigger spacing injection if there is exactly one newline between text and the table.
        response = re.sub(r"([^|\s])([ \t]*\n[ \t]*)(\|.*\|)", r"\1\n\n\3", response)
        response = re.sub(r"(\|.*\|)([ \t]*\n[ \t]*)([^|\s])", r"\1\n\n\3", response)

        model_ms = (time.time() - t_model_start) * 1000.0
        step_times["step7"] = round((time.time() - t_step7_start) * 1000.0, 2)
        step_times.pop("step8", None)

        t_step9_start = time.time()
        existing_msg = db.query(ChatMessage).filter(ChatMessage.conversation_id == conv_id).first()
        if existing_msg and existing_msg.conversation_title:
            conv_title = existing_msg.conversation_title
        else:
            try:
                title_prompt = 'You MUST output EXACTLY AND ONLY this JSON format: {"reasoning": "brief reasoning here", "final_answer": "Short 3-5 word title"}\nGenerate a descriptive topic title (e.g., \'Concept of Inheritance\') for the conversation starting with this message. DO NOT simply repeat the user\'s question.'
                title_prompt += f"\nMessage: {message}"
                conv_title_raw = await ai_client.answer_question(
                    question=message, context="", system_prompt=title_prompt
                )
                conv_title = conv_title_raw.strip()
                if conv_title.startswith('"') and conv_title.endswith('"'):
                    conv_title = conv_title[1:-1]

                if (
                    not conv_title
                    or len(conv_title) > 100
                    or "reasoning" in conv_title.lower()
                    or "{" in conv_title
                ):
                    conv_title = generate_conversation_title(message)
            except Exception:
                conv_title = generate_conversation_title(message)
        step_times["step9"] = round((time.time() - t_step9_start) * 1000.0, 2)
        total_ms = (time.time() - t_start) * 1000.0

        timings_dict = {
            "retrieval_ms": round(retrieval_ms, 2),
            "model_ms": round(model_ms, 2),
            "total_ms": round(total_ms, 2),
            "step_times": step_times,
        }

        chat_msg = db.query(ChatMessage).filter(ChatMessage.id == chat_msg_id).first()
        if chat_msg:
            chat_msg.response = response
            chat_msg.sources = json.dumps(snippet_sources)
            chat_msg.conversation_title = conv_title
            chat_msg.ai_mode = ai_mode
            chat_msg.output_format = output_format
            chat_msg.ai_model = ai_model_info
            chat_msg.reply_to_message_id = reply_to_message_id
            chat_msg.detailed_sources_json = (
                json.dumps(detailed_sources) if detailed_sources else None
            )
            chat_msg.timings_json = json.dumps(timings_dict)
            db.commit()

        return {
            "id": chat_msg_id,
            "message": message,
            "response": response,
            "sources": snippet_sources,
            "ai_mode": ai_mode,
            "output_format": output_format,
            "ai_model": ai_model_info,
            "detailed_sources": detailed_sources,
            "conversation_id": conv_id,
            "conversation_title": conv_title,
            "timings": timings_dict,
        }
    finally:
        db.close()


@router.get("/conversations", response_model=list[ConversationSummary])
async def get_conversations(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """List all conversations (grouped by conversation_id) for the current user."""
    rows = (
        db.query(
            ChatMessage.conversation_id,
            func.max(ChatMessage.conversation_title).label("title"),
            func.count(ChatMessage.id).label("message_count"),
            func.max(ChatMessage.created_at).label("last_message_at"),
            func.max(ChatMessage.resource_id).label("resource_id"),
            func.max(ChatMessage.subject_id).label("subject_id"),
            func.max(ChatMessage.group_id).label("group_id"),
            func.max(cast(ChatMessage.is_pinned, Integer)).label("is_pinned"),
            func.max(cast(ChatMessage.is_favourite, Integer)).label("is_favourite"),
        )
        .filter(
            ChatMessage.user_id == current_user.id,
            ChatMessage.conversation_id.isnot(None),
        )
        .group_by(ChatMessage.conversation_id)
        .order_by(
            func.max(cast(ChatMessage.is_pinned, Integer)).desc(),
            func.max(ChatMessage.created_at).desc(),
        )
        .all()
    )

    result = []
    for row in rows:
        scope_type = (
            "resource"
            if row.resource_id
            else ("subject" if row.subject_id else ("group" if row.group_id else None))
        )
        result.append(
            ConversationSummary(
                conversation_id=row.conversation_id,
                title=row.title or "Untitled Conversation",
                message_count=row.message_count,
                last_message_at=row.last_message_at.isoformat(),
                resource_id=row.resource_id,
                subject_id=row.subject_id,
                group_id=row.group_id,
                scope_type=scope_type,
                is_pinned=bool(row.is_pinned),
                is_favourite=bool(row.is_favourite),
            )
        )

    return result


@router.get("/exercise/{exercise_id}/conversations", response_model=list[ConversationSummary])
async def get_exercise_conversations(
    exercise_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List conversations for a specific exercise."""
    rows = (
        db.query(
            ChatMessage.conversation_id,
            func.max(ChatMessage.conversation_title).label("title"),
            func.count(ChatMessage.id).label("message_count"),
            func.max(ChatMessage.created_at).label("last_message_at"),
        )
        .filter(
            ChatMessage.user_id == current_user.id,
            ChatMessage.conversation_id.isnot(None),
            ChatMessage.exercise_id == exercise_id,
        )
        .group_by(ChatMessage.conversation_id)
        .order_by(func.max(ChatMessage.created_at).desc())
        .all()
    )

    result = []
    for row in rows:
        result.append(
            ConversationSummary(
                conversation_id=row.conversation_id,
                title=row.title or "Untitled Conversation",
                message_count=row.message_count,
                last_message_at=row.last_message_at.isoformat(),
                exercise_id=exercise_id,
                scope_type="exercise",
            )
        )

    return result


@router.get("/conversations/{conversation_id}/messages", response_model=list[ChatMessageResponse])
async def get_conversation_messages(
    conversation_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get all messages in a specific conversation, ordered chronologically."""
    messages = (
        db.query(ChatMessage)
        .filter(
            ChatMessage.user_id == current_user.id,
            ChatMessage.conversation_id == conversation_id,
        )
        .order_by(ChatMessage.created_at.asc())
        .all()
    )

    if not messages:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    return [
        ChatMessageResponse(
            id=m.id,
            message=m.message,
            response=m.response,
            sources=json.loads(m.sources) if m.sources else [],
            detailed_sources=json.loads(m.detailed_sources_json) if m.detailed_sources_json else [],
            created_at=m.created_at.isoformat(),
            resource_id=m.resource_id,
            subject_id=m.subject_id,
            group_id=m.group_id,
            ai_mode=m.ai_mode,
            ai_model=m.ai_model,
            conversation_id=m.conversation_id,
            conversation_title=m.conversation_title,
            reply_to_message_id=m.reply_to_message_id,
            output_format=m.output_format,
            timings=json.loads(m.timings_json) if m.timings_json else None,
            rating=m.rating,
            rating_comment=m.rating_comment,
        )
        for m in messages
    ]


@router.get("/history", response_model=list[ChatMessageResponse])
async def get_all_chat_history(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Get all chat history for current user (individual messages)."""
    messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.user_id == current_user.id)
        .order_by(ChatMessage.created_at.desc())
        .all()
    )

    return [
        ChatMessageResponse(
            id=m.id,
            message=m.message,
            response=m.response,
            sources=json.loads(m.sources) if m.sources else [],
            detailed_sources=json.loads(m.detailed_sources_json) if m.detailed_sources_json else [],
            created_at=m.created_at.isoformat(),
            resource_id=m.resource_id,
            subject_id=m.subject_id,
            group_id=m.group_id,
            ai_mode=m.ai_mode,
            ai_model=m.ai_model,
            conversation_id=m.conversation_id,
            conversation_title=m.conversation_title,
            reply_to_message_id=m.reply_to_message_id,
            output_format=m.output_format,
            timings=json.loads(m.timings_json) if m.timings_json else None,
            rating=m.rating,
            rating_comment=m.rating_comment,
        )
        for m in messages
    ]


@router.get("/history/{resource_id}", response_model=list[ChatMessageResponse])
async def get_note_chat_history(
    resource_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Get chat history for a specific resource."""
    resource = (
        db.query(Resource)
        .filter(Resource.id == resource_id, Resource.user_id == current_user.id)
        .first()
    )

    if not resource:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")

    messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.user_id == current_user.id, ChatMessage.resource_id == resource_id)
        .order_by(ChatMessage.created_at.desc())
        .all()
    )

    return [
        ChatMessageResponse(
            id=m.id,
            message=m.message,
            response=m.response,
            sources=json.loads(m.sources) if m.sources else [],
            detailed_sources=json.loads(m.detailed_sources_json) if m.detailed_sources_json else [],
            created_at=m.created_at.isoformat(),
            resource_id=m.resource_id,
            subject_id=m.subject_id,
            group_id=m.group_id,
            ai_mode=m.ai_mode,
            reply_to_message_id=m.reply_to_message_id,
            output_format=m.output_format,
            timings=json.loads(m.timings_json) if m.timings_json else None,
            rating=m.rating,
            rating_comment=m.rating_comment,
        )
        for m in messages
    ]


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete an entire conversation."""
    db.query(ChatMessage).filter(
        ChatMessage.conversation_id == conversation_id, ChatMessage.user_id == current_user.id
    ).delete()
    db.commit()


@router.put("/conversations/{conversation_id}/pin")
async def toggle_pin_conversation(
    conversation_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Toggle the pinned state of a conversation."""
    messages = (
        db.query(ChatMessage)
        .filter(
            ChatMessage.conversation_id == conversation_id, ChatMessage.user_id == current_user.id
        )
        .all()
    )
    if not messages:
        raise HTTPException(status_code=404, detail="Conversation not found")

    new_state = not messages[0].is_pinned
    for msg in messages:
        msg.is_pinned = new_state
    db.commit()
    return {"is_pinned": new_state}


@router.put("/conversations/{conversation_id}/favourite")
async def toggle_favourite_conversation(
    conversation_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Toggle the favourite state of a conversation."""
    messages = (
        db.query(ChatMessage)
        .filter(
            ChatMessage.conversation_id == conversation_id, ChatMessage.user_id == current_user.id
        )
        .all()
    )
    if not messages:
        raise HTTPException(status_code=404, detail="Conversation not found")

    new_state = not messages[0].is_favourite
    for msg in messages:
        msg.is_favourite = new_state
    db.commit()
    return {"is_favourite": new_state}


@router.put("/conversations/{conversation_id}/title")
async def update_conversation_title(
    conversation_id: str,
    payload: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update the title of a conversation."""
    title = payload.get("title")
    if not title:
        raise HTTPException(status_code=400, detail="Title is required")

    messages = (
        db.query(ChatMessage)
        .filter(
            ChatMessage.conversation_id == conversation_id, ChatMessage.user_id == current_user.id
        )
        .all()
    )
    if not messages:
        raise HTTPException(status_code=404, detail="Conversation not found")

    for msg in messages:
        msg.conversation_title = title
    db.commit()
    return {"title": title}


@router.delete("/{message_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_chat_message(
    message_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Delete a specific chat message."""
    msg = (
        db.query(ChatMessage)
        .filter(ChatMessage.id == message_id, ChatMessage.user_id == current_user.id)
        .first()
    )
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")

    db.delete(msg)
    db.commit()
    return None


@router.put("/{message_id}/rate")
async def rate_chat_message(
    message_id: str,
    payload: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update the rating of a specific chat message (0-5 stars)."""
    rating = payload.get("rating")
    comment = payload.get("comment")

    if rating is not None and (not isinstance(rating, (int, float)) or rating < 0 or rating > 5):
        raise HTTPException(status_code=400, detail="Valid rating (0-5) is required")

    msg = (
        db.query(ChatMessage)
        .filter(ChatMessage.id == message_id, ChatMessage.user_id == current_user.id)
        .first()
    )

    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")

    if rating is None and comment is None:
        raise HTTPException(status_code=400, detail="Must provide rating or comment")

    if rating is not None:
        msg.rating = int(rating)
    if comment is not None:
        msg.rating_comment = comment

    db.commit()
    return {"rating": msg.rating, "rating_comment": msg.rating_comment}


@router.get("/debug_cv")
def debug_cv(conv_id: str, db: Session = Depends(get_db)):
    msgs = (
        db.query(ChatMessage)
        .filter(ChatMessage.conversation_id == conv_id)
        .order_by(ChatMessage.created_at)
        .all()
    )
    res = []
    for msg in msgs:
        res.append(
            {
                "message": msg.message,
                "mode": msg.ai_mode,
                "format": msg.output_format,
                "response": msg.response,
            }
        )
    return res
