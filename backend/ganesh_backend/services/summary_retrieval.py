"""Context assembly service for the conversation-checkpoint memory system.

Builds the full context window for each chat turn by prepending system
messages to the existing message array (which already contains the recent
unsummarized segment from the frontend state):

1. **Checkpoint context** (always, if checkpoints exist) — all checkpoint
   summaries for the current conversation, formatted as a single system
   message. This gives the model the "friend who remembers" feel.

2. **Cross-day context** (if relevant) — semantic search over past
   conversation-level summaries (excluding the current conversation),
   injecting the top-k most relevant ones.

3. **Pulled transcript** (on-demand) — when the user message semantically
   matches an old checkpoint summary above ``full_pull_threshold``, the
   full message segment for that checkpoint plus adjacent segments is
   pulled into the context window.

The service does NOT duplicate the recent unsummarized messages — those
are already in ``existing_messages`` from the frontend.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional, Protocol

from ganesh_backend.services.conversations import ConversationStore
from ganesh_backend.services.summary_embeddings import SummaryEmbeddingStore

logger = logging.getLogger(__name__)

MIN_CROSS_DAY_SCORE = 0.3


class ConfigProtocol(Protocol):
    def get_setting(self, key: str, default: Any = None) -> Any: ...


class ContextAssemblyService:
    """Assembles the full context window for a chat turn.

    Parameters
    ----------
    conversation_store:
        ConversationStore instance for checkpoint and message retrieval.
    summary_embedding_store:
        SummaryEmbeddingStore instance for semantic search over checkpoint
        and conversation summaries.
    config:
        Config service exposing ``get_setting`` for the
        ``conversation_memory`` config section.
    """

    def __init__(
        self,
        conversation_store: ConversationStore,
        summary_embedding_store: SummaryEmbeddingStore,
        config: ConfigProtocol,
    ) -> None:
        self._conv_store = conversation_store
        self._emb_store = summary_embedding_store
        self._config = config

    def build_context(
        self,
        user_message: str,
        conversation_id: str,
        existing_messages: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Build the full context window for a chat turn.

        Returns the messages array with system messages prepended and the
        new user message appended.
        """
        system_msgs: list[dict[str, str]] = []

        checkpoint_msg = self._build_checkpoint_context_message(conversation_id)
        if checkpoint_msg is not None:
            system_msgs.append(checkpoint_msg)

        cross_day_msg = self._build_cross_day_context_message(
            user_message, conversation_id
        )
        if cross_day_msg is not None:
            system_msgs.append(cross_day_msg)

        transcript_msg = self._build_pulled_transcript_message(
            user_message, conversation_id
        )
        if transcript_msg is not None:
            system_msgs.append(transcript_msg)

        return system_msgs + existing_messages + [
            {"role": "user", "content": user_message}
        ]

    def _build_checkpoint_context_message(
        self, conversation_id: str
    ) -> Optional[dict[str, str]]:
        """Get all checkpoint summaries for this conversation as a system message."""
        try:
            checkpoints = self._conv_store.get_checkpoints(conversation_id)
        except Exception:
            logger.exception("Failed to fetch checkpoints for %s", conversation_id)
            return None

        if not checkpoints:
            return None

        valid = [
            c for c in checkpoints
            if c.get("summary") and c["summary"].strip()
        ]
        if not valid:
            return None

        lines: list[str] = ["Conversation memory (checkpoint summaries from earlier today):", ""]
        for cp in valid:
            seq = cp["sequence_number"]
            time_str = self._format_checkpoint_time(cp.get("created_at", ""))
            lines.append(f"## Checkpoint {seq} ({time_str})")
            lines.append(cp["summary"])
            lines.append("")

        lines.append(
            "You remember these earlier parts of the conversation. Reference them "
            "naturally when relevant, as a friend would."
        )
        return {"role": "system", "content": "\n".join(lines)}

    def _build_cross_day_context_message(
        self, user_message: str, exclude_conversation_id: str
    ) -> Optional[dict[str, str]]:
        """Search past conversation summaries, inject top-k relevant ones."""
        max_injected = int(
            self._config.get_setting("conversation_memory.max_summaries_injected", 3)
        )
        try:
            results = self._emb_store.search_conversation_summaries(
                query=user_message,
                exclude_conversation_id=exclude_conversation_id,
                limit=max_injected,
            )
        except Exception:
            logger.exception("Failed cross-day conversation search")
            return None

        relevant = [r for r in results if r.score >= MIN_CROSS_DAY_SCORE]
        if not relevant:
            return None

        lines: list[str] = ["Past conversation context (from previous days):", ""]
        for r in relevant:
            date_str = self._format_conversation_date(
                r.metadata.get("created_at", "")
            )
            title = r.metadata.get("title", "Untitled")
            lines.append(
                f'## Conversation from {date_str} — "{title}" (score: {r.score:.2f})'
            )
            lines.append(r.summary)
            lines.append("")

        lines.append(
            "Use this context to provide continuity across days. Reference naturally "
            "when the user mentions related topics."
        )
        return {"role": "system", "content": "\n".join(lines)}

    def _build_pulled_transcript_message(
        self, user_message: str, conversation_id: str
    ) -> Optional[dict[str, str]]:
        """On-demand: if user message matches a checkpoint, pull that segment + adjacent."""
        threshold = float(
            self._config.get_setting("conversation_memory.full_pull_threshold", 0.85)
        )
        max_messages = int(
            self._config.get_setting("conversation_memory.max_transcript_messages", 50)
        )
        adjacent = int(
            self._config.get_setting("conversation_memory.adjacent_segments", 1)
        )

        try:
            results = self._emb_store.search_checkpoint_summaries(
                query=user_message,
                conversation_id=conversation_id,
                limit=5,
            )
        except Exception:
            logger.exception("Failed checkpoint summary search for pull")
            return None

        if not results:
            return None

        top = results[0]
        if top.score < threshold:
            return None

        match_seq = top.sequence_number
        match_cp = self._conv_store.get_checkpoint(conversation_id, match_seq)
        if match_cp is None:
            return None

        seqs_to_pull = self._collect_adjacent_seqs(match_seq, adjacent)

        all_messages: list[dict[str, Any]] = []
        for seq in seqs_to_pull:
            cp = self._conv_store.get_checkpoint(conversation_id, seq)
            if cp is None:
                continue
            segment = self._conv_store.get_messages_between(
                conversation_id,
                cp.get("start_message_id"),
                cp.get("end_message_id"),
            )
            all_messages.extend(segment)

        if not all_messages:
            return None

        if len(all_messages) > max_messages:
            all_messages = all_messages[-max_messages:]

        time_str = self._format_checkpoint_time(
            match_cp.get("created_at", "")
        )
        lines: list[str] = [
            f"Referenced earlier conversation segment "
            f"(from checkpoint {match_seq} at {time_str}):",
            "",
        ]
        for m in all_messages:
            role = m.get("role", "user").capitalize()
            content = m.get("content", "")
            lines.append(f"{role}: {content}")

        seq_range = self._format_seq_range(seqs_to_pull)
        lines.append(
            f"(from checkpoint {seq_range}, truncated to {max_messages} messages)"
        )
        return {"role": "system", "content": "\n".join(lines)}

    def _collect_adjacent_seqs(self, match_seq: int, adjacent: int) -> list[int]:
        """Collect the match sequence plus adjacent sequences (cK-N .. cK+N)."""
        seqs: list[int] = []
        for offset in range(-adjacent, adjacent + 1):
            seqs.append(match_seq + offset)
        return seqs

    @staticmethod
    def _format_seq_range(seqs: list[int]) -> Optional[str]:
        if not seqs:
            return ""
        return f"{min(seqs)} through {max(seqs)}"

    @staticmethod
    def _format_checkpoint_time(created_at: str) -> str:
        if not created_at:
            return "unknown time"
        try:
            dt = datetime.fromisoformat(created_at)
            return dt.strftime("%I:%M %p").lstrip("0")
        except (ValueError, TypeError):
            return created_at

    @staticmethod
    def _format_conversation_date(created_at: str) -> str:
        if not created_at:
            return "unknown date"
        try:
            dt = datetime.fromisoformat(created_at)
            return dt.strftime("%Y-%m-%d")
        except (ValueError, TypeError):
            return created_at


_service: Optional[ContextAssemblyService] = None


def get_context_assembly_service() -> ContextAssemblyService:
    global _service
    if _service is None:
        from ganesh_backend.routers.conversations import get_conversation_service
        from ganesh_backend.services.config import config_service
        from ganesh_backend.services.summary_embeddings import (
            get_summary_embedding_store,
        )

        _service = ContextAssemblyService(
            conversation_store=get_conversation_service(),
            summary_embedding_store=get_summary_embedding_store(),
            config=config_service,
        )
    return _service


def reset_context_assembly_service() -> None:
    global _service
    _service = None


def set_context_assembly_service(svc: ContextAssemblyService) -> None:
    global _service
    _service = svc
