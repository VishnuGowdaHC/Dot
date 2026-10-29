"""
Compacts memory turns into ASD-STE100 summaries using FastMCP sampling.
"""

import os
import re
from typing import Optional
from mcp.types import TextContent
from fastmcp.client.sampling import SamplingMessage, SamplingParams
from src.dot.mcp_files.mcpClient import sampling_handler

# Define the system prompt with strict ASD-STE100 constraints.
ASD_STE_SYSTEM_PROMPT = """You are a technical summarizer operating under ASD-STE100 rules.
Summarize the conversation context into clear, concise statements.

Follow these strict rules:
1. Keep every sentence under 25 words.
2. Express only one fact or action per sentence.
3. Write in the active voice.
4. Use the simple present tense.
5. Do not write introductory text, fluff, or filler phrases.
6. Organize output into these exact sections:

### User Facts & Goals
- List key user requests, constraints, and parameters.

### Actions & Tool Outcomes
- List tools executed, targets, and essential outcomes.

### Current Progress & Decisions
- List resolved items and active state.
"""


def _build_sampling_message(text_to_compact: str, previous_summary: Optional[str] = None) -> SamplingMessage:
    """Creates a typed FastMCP sampling message from the input text."""
    if previous_summary:
        content_text = (
            f"Merge the previous summary and new turns into one unified summary:\n\n"
            f"<PREVIOUS_SUMMARY>\n{previous_summary}\n</PREVIOUS_SUMMARY>\n\n"
            f"<NEW_TURNS>\n{text_to_compact}\n</NEW_TURNS>"
        )
    else:
        content_text = f"Summarize these conversation turns:\n\n{text_to_compact}"

    # Return a validated SamplingMessage instance with TextContent.
    return SamplingMessage(
        role="user",
        content=TextContent(type="text", text=content_text)
    )


def _extract_fallback_summary(text: str, previous_summary: Optional[str] = None) -> str:
    """Extracts a simple summary when sampling fails."""
    # Find user query strings in text.
    user_queries = re.findall(r"^User:\s*(.+)$", text, re.MULTILINE)
    # Find tool call records in text.
    tool_calls = re.findall(r"\[(?:Found tool|Observation from)\s*([^\]]+)\]", text)

    lines = []
    lines.append("### User Facts & Goals")
    if user_queries:
        for q in user_queries[:3]:
            # Truncate query length to conform with sentence limits.
            clean_q = q.strip()[:80]
            lines.append(f"- User requested: {clean_q}.")
    else:
        lines.append("- The user provided task instructions.")

    lines.append("\n### Actions & Tool Outcomes")
    if tool_calls:
        for t in tool_calls[:4]:
            lines.append(f"- Executed tool {t.strip()}.")
    else:
        lines.append("- Processed conversational turns.")

    lines.append("\n### Current Progress & Decisions")
    lines.append("- Context compacted to conserve token budget.")

    fallback_result = "\n".join(lines)
    if previous_summary:
        return f"{previous_summary}\n\n{fallback_result}"
    return fallback_result


class MemoryCompactor:
    """Compacts conversation history into structured ASD-STE100 summaries."""

    def __init__(self, system_prompt: Optional[str] = None):
        # Store system prompt for sampling.
        self.system_prompt = system_prompt or ASD_STE_SYSTEM_PROMPT

    async def compact(self, text_to_compact: str, previous_summary: Optional[str] = None) -> str:
        """Generates an ASD-STE100 summary through FastMCP sampling."""
        if not text_to_compact.strip():
            return previous_summary or ""

        # Construct FastMCP sampling parameters and message.
        message = _build_sampling_message(text_to_compact, previous_summary)
        params = SamplingParams(
            messages=[message],
            systemPrompt=self.system_prompt,
            temperature=0.0,
            maxTokens=600
        )

        try:
            # Request LLM generation through FastMCP sampling handler.
            summary = await sampling_handler(messages=[message], params=params, context=None)
            clean_summary = summary.strip()
            if clean_summary:
                return clean_summary
        except Exception as err:
            # Print error to terminal on sampling failure.
            print(f"[MemoryCompactor Warning] Sampling failed: {err}")

        # Return fallback summary when sampling fails.
        return _extract_fallback_summary(text_to_compact, previous_summary)
