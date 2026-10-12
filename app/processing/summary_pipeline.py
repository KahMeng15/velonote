import asyncio
import logging
import re
from collections.abc import Callable

logger = logging.getLogger(__name__)


class SummaryPipeline:
    """
    Advanced pipeline for generating summaries using parallel chunking and streaming.
    Mirrors the 'smart_pipeline' logic but optimized for summarization.
    """

    # Target size for each chunk (characters)
    # Summaries can afford slightly larger chunks than note polish
    _CHUNK_SIZE = 4000

    def __init__(self, ai_client):
        self.ai_client = ai_client

    async def generate_summary(
        self,
        content: str,
        mode: str = "elaborate",
        output_format: str = "sentence",
        processing_method: str = "whole",
        split_level: str = "h2",
        custom_prompt: str | None = None,
        progress_callback: Callable[[int, str | None, str | None], None] | None = None,
    ) -> str:
        """
        Orchestrates the chunking, parallel processing, and assembly of a summary.
        """
        logger.info(
            f"SummaryPipeline.generate_summary started. Method: {processing_method}, Mode: {mode}, Format: {output_format}"
        )
        if not content:
            return ""

        # Determine chunks based on method
        if processing_method == "section":
            logger.info(f"Using SECTIONAL processing with split level: {split_level}")
            raw_chunks = self._split_by_sections(content, split_level)
            # raw_chunks is List[dict] with {"header": str, "content": str}
            actual_mode = mode
        else:
            logger.info("Using WHOLE note chunking...")
            raw_chunks = [{"header": "", "content": c} for c in self._split_into_chunks(content)]
            actual_mode = mode

        num_chunks = len(raw_chunks)
        logger.info(f"Content prepared into {num_chunks} segments.")

        if num_chunks == 1:
            logger.info("Processing single segment summary...")
            header = raw_chunks[0]["header"]
            content = raw_chunks[0]["content"]
            res = await self._summarize_chunk(
                0, content, actual_mode, output_format, is_first=True, custom_prompt=custom_prompt
            )
            if header:
                res = f"{header}\n\n{res}"
            if progress_callback:
                progress_callback(100, "Complete", res)
            return res

        logger.info(f"Generating summary with {num_chunks} segments (parallel, limit=2)...")

        # Limit concurrency to avoid rate limits on reasoning models
        semaphore = asyncio.Semaphore(2)
        completed_chunks = 0

        async def _bounded_summarize(idx, chunk_data, is_first):
            nonlocal completed_chunks
            logger.info(f"Segment {idx + 1}: Waiting for semaphore...")
            async with semaphore:
                logger.info(f"Segment {idx + 1}: Semaphore acquired. Starting AI call.")
                try:
                    header = chunk_data["header"]
                    content = chunk_data["content"]

                    if not content.strip():
                        return f"{header}\n\n[No content to summarize]" if header else ""

                    # Add a per-chunk timeout of 180 seconds to prevent total hang
                    result = await asyncio.wait_for(
                        self._summarize_chunk(
                            idx,
                            content,
                            actual_mode,
                            output_format,
                            is_first=is_first,
                            custom_prompt=custom_prompt,
                        ),
                        timeout=180.0,
                    )

                    if header:
                        result = f"{header}\n\n{result}"

                    completed_chunks += 1
                    logger.info(
                        f"Segment {idx + 1}: Complete. Total completed: {completed_chunks}/{num_chunks}"
                    )
                    return result
                except TimeoutError:
                    logger.error(f"Segment {idx + 1}: TIMEOUT during AI processing.")
                    return f"\n[Summary of section {idx + 1} timed out]\n"
                except Exception as e:
                    logger.error(f"Segment {idx + 1}: Unexpected error: {e}", exc_info=True)
                    if "All AI tiers failed" in str(e):
                        raise e
                    return f"\n[Error summarizing section {idx + 1}]\n"

        tasks = [_bounded_summarize(i, chunk, i == 0) for i, chunk in enumerate(raw_chunks)]

        # We process in order for streaming updates
        summarized_chunks = [None] * num_chunks
        separator = (
            "\n\n"
            if output_format in ["pointform", "numbered_list", "table"]
            or processing_method == "section"
            else " "
        )

        for i, task in enumerate(tasks):
            result = await task
            summarized_chunks[i] = result

            if progress_callback:
                progress = 10 + int(((i + 1) / num_chunks) * 85)
                # Join only what we have so far
                partial_summary = separator.join(
                    [c for c in summarized_chunks if c is not None]
                ).strip()
                progress_callback(
                    progress, f"Summarizing section {i + 1} of {num_chunks}...", partial_summary
                )

        # Final assembly (should already be done in the loop above)
        final_summary = separator.join([c for c in summarized_chunks if c]).strip()

        # Final cleanup pass if multiple chunks were joined
        if num_chunks > 1:
            final_summary = self._final_cleanup(final_summary)

        if progress_callback:
            progress_callback(100, "Complete", final_summary)
        return final_summary

    def _split_by_sections(self, text: str, split_level: str) -> list[dict]:
        """Split text into logical sections based on the requested markdown header level."""
        level_map = {"h1": 1, "h2": 2, "h3": 3}
        target_level = level_map.get(split_level.lower(), 2)

        # Pattern to match headers like #, ##, ###
        pattern = f"^#{{1,{target_level}}}\\s+"

        lines = text.split("\n")
        sections = []
        current_header = ""
        current_content = []

        for line in lines:
            if re.match(pattern, line):
                if current_content or current_header:
                    sections.append(
                        {"header": current_header, "content": "\n".join(current_content).strip()}
                    )
                    current_content = []
                current_header = line
            else:
                current_content.append(line)

        if current_content or current_header:
            sections.append(
                {"header": current_header, "content": "\n".join(current_content).strip()}
            )

        return [s for s in sections if s["header"].strip() or s["content"].strip()]

    def _split_into_chunks(self, text: str) -> list[str]:
        """Split text into chunks at markdown heading boundaries or paragraph breaks."""
        lines = text.split("\n")
        chunks = []
        current_chunk = []
        current_size = 0

        for line in lines:
            current_chunk.append(line)
            current_size += len(line) + 1

            # Split if chunk is large enough AND we hit a heading or empty line
            if current_size >= self._CHUNK_SIZE and (
                re.match(r"^#{1,4}\s", line) or not line.strip()
            ):
                chunks.append("\n".join(current_chunk).strip())
                current_chunk = []
                current_size = 0

        if current_chunk:
            chunks.append("\n".join(current_chunk).strip())

        return [c for c in chunks if c]

    async def _summarize_chunk(
        self,
        idx: int,
        chunk: str,
        mode: str,
        output_format: str,
        is_first: bool,
        custom_prompt: str | None = None,
    ) -> str:
        """Summarize a single chunk using streaming and markers."""

        # Dynamic instruction based on mode and format
        format_instruction = ""
        if output_format == "pointform":
            format_instruction = "Use concise bullet points (start with '- ')."
        elif output_format == "numbered_list":
            format_instruction = "Use a numbered list."
        elif output_format == "table":
            format_instruction = "Summarize the key information in a Markdown table."
        elif output_format != "none":
            format_instruction = "Use clear, professional sentences."

        mode_instruction = ""
        if mode == "quick":
            mode_instruction = "Provide a very brief high-level overview (1-2 paragraphs max)."
        elif mode == "simple":
            mode_instruction = "Explain in simple terms as if for a beginner."
        elif mode == "eli5":
            mode_instruction = "Explain like I'm five. Use very simple analogies."
        elif mode != "none":  # elaborate
            mode_instruction = (
                "Provide a detailed, comprehensive summary covering all key technical points."
            )

        instructions = []
        if mode_instruction:
            instructions.append(f"- Mode: {mode_instruction}")
        if format_instruction:
            instructions.append(f"- Format: {format_instruction}")
        if custom_prompt:
            instructions.append(f"- Custom Instruction: {custom_prompt}")

        instructions_text = "\n".join(instructions)

        prompt = f"""Task: Summarize the following note segment.

INSTRUCTIONS:
{instructions_text}

START WITH THE MARKER ===START===
END WITH THE MARKER ===END===
NO PREAMBLE: Output ONLY the summary between the markers.
NO REASONING: Do not explain your process.

INPUT SEGMENT:
{chunk}

SUMMARY:
===START===
"""
        try:
            full_text = ""
            async for text_segment in self.ai_client.stream_text(prompt, max_tokens=1500, require_reasoning=True):
                full_text += text_segment

            if not full_text:
                return ""

            # Extract content between markers
            content = full_text.strip()
            if "===START===" in content:
                content = content.split("===START===")[-1]
            if "===END===" in content:
                content = content.split("===END===")[0]

            content = content.strip()

            # Basic cleanup of AI artifacts
            content = self._scrub_artifacts(content)

            return content

        except Exception as e:
            logger.error(f"Error summarizing chunk {idx}: {e}")
            raise e

    def _scrub_artifacts(self, text: str) -> str:
        """Remove common AI-generated reasoning artifacts or markers."""
        lines = text.split("\n")
        cleaned = []
        REASONING_PATTERNS = [
            r"^\s*[\*\-]\s*Rule \d+:",
            r"^\s*[\*\-]\s*Segment \d+:",
            r"^\s*[\*\-]\s*Summary of",
            r"^\s*Here is the",
            r"^\s*===",
        ]

        for line in lines:
            if any(re.match(p, line, re.IGNORECASE) for p in REASONING_PATTERNS):
                continue
            cleaned.append(line)

        result = "\n".join(cleaned).strip()

        # Remove backtick wrapping
        if result.startswith("```"):
            result = re.sub(r"^```[a-z]*\n?", "", result)
            result = re.sub(r"\n?```$", "", result)

        return result.strip()

    def _final_cleanup(self, text: str) -> str:
        """Post-assembly cleanup for multi-chunk summaries."""
        # Remove repeated H1s if they were accidentally generated
        lines = text.split("\n")
        cleaned = []
        seen_h1 = False
        for line in lines:
            if re.match(r"^#\s+", line) and not re.match(r"^##", line):
                if seen_h1:
                    continue  # Skip secondary H1s
                seen_h1 = True
            cleaned.append(line)
        return "\n".join(cleaned).strip()
