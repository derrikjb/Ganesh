"""Checkpoint summary generation service.

Generates checkpoint summaries (for gap-triggered checkpoints) and
conversation-level summaries (for conversation close). Calls the LLM
with the relevant message segment, stores the summary in the
ConversationStore, and indexes it in the SummaryEmbeddingStore.

Error handling: LLM failures are logged and swallowed so checkpointing
never blocks the chat flow. Messages remain unsummarized and will be
included in the next checkpoint attempt.
"""

from __future__ import annotations

import logging
from typing import Any, Optional, Protocol

from ganesh_backend.services import llm as llm_service
from ganesh_backend.services.config import config_service
from ganesh_backend.services.conversations import ConversationStore
from ganesh_backend.services.summary_embeddings import SummaryEmbeddingStore

logger = logging.getLogger(__name__)


class ConfigProtocol(Protocol):
    def get_setting(self, key: str, default: Any = None) -> Any: ...


_CHECKPOINT_SYSTEM_PROMPT = (
    "You are a conversation checkpoint summarizer. Summarize the following "
    "segment of a conversation concisely (~{checkpoint_max} tokens) including:\n"
    "- Topics discussed in this segment\n"
    "- Key facts, decisions, and technical details\n"
    "- User's emotional state and preferences (if discernible)\n"
    "- Unresolved questions from this segment\n\n"
    "{prev_context}"
    "This summary will be used to recall this conversation segment in future "
    "turns. Write in third person. Be concise."
)

_CONVERSATION_SYSTEM_PROMPT = (
    "You are a conversation summarizer. This conversation has been divided "
    "into checkpoint segments. Below are the checkpoint summaries in order, "
    "followed by any recent messages not yet checkpointed.\n\n"
    "Produce a comprehensive conversation-level summary (~{conversation_max} tokens) that "
    "captures the full arc of the conversation: main topics, key decisions, "
    "user preferences, technical details, and unresolved items.\n\n"
    "{checkpoint_block}"
    "{recent_block}"
    "Write in third person."
)


class SummaryGenerationService:
    """Generates checkpoint and conversation-level summaries via LLM calls.

    Parameters
    ----------
    conversation_store:
        Store with checkpoint CRUD and message retrieval methods.
    summary_embedding_store:
        LanceDB store for embedding checkpoint and conversation summaries.
    config:
        Config service providing ``conversation_memory.*`` settings.
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

    def generate_checkpoint(
        self, conversation_id: str
    ) -> Optional[dict[str, Any]]:
        """Generate a checkpoint for the current unsummarized segment.

        Returns the created checkpoint dict, or ``None`` if the segment
        was too short or the LLM call failed.
        """
        latest = self._conv_store.get_latest_checkpoint(conversation_id)

        if latest is not None:
            segment = self._conv_store.get_messages_since_checkpoint(
                conversation_id, latest["sequence_number"]
            )
            prev_summary: Optional[str] = latest["summary"]
            seq_number = latest["sequence_number"] + 1
        else:
            segment = self._conv_store.get_messages_between(
                conversation_id, None, None
            )
            prev_summary = None
            seq_number = 0

        min_messages: int = self._config.get_setting(
            "conversation_memory.min_messages_for_checkpoint", 2
        )
        if len(segment) < min_messages:
            return None

        messages = self._build_checkpoint_prompt(segment, prev_summary)
        summary = self._call_llm(messages)
        if summary is None:
            return None

        start_msg_id = segment[0]["id"] if segment else None
        end_msg_id = segment[-1]["id"] if segment else None

        checkpoint_id = self._conv_store.create_checkpoint(
            conversation_id=conversation_id,
            sequence_number=seq_number,
            summary=summary,
            start_message_id=start_msg_id,
            end_message_id=end_msg_id,
        )

        try:
            self._emb_store.index_checkpoint_summary(
                checkpoint_id=checkpoint_id,
                conversation_id=conversation_id,
                sequence_number=seq_number,
                summary=summary,
                metadata={
                    "start_message_id": start_msg_id,
                    "end_message_id": end_msg_id,
                },
            )
        except Exception:
            logger.exception(
                "Failed to index checkpoint %s for conversation %s",
                checkpoint_id,
                conversation_id,
            )

        return {
            "id": checkpoint_id,
            "conversation_id": conversation_id,
            "sequence_number": seq_number,
            "summary": summary,
            "start_message_id": start_msg_id,
            "end_message_id": end_msg_id,
        }

    def generate_conversation_summary(
        self, conversation_id: str
    ) -> Optional[str]:
        """Generate a conversation-level summary on close.

        Returns the summary text, or ``None`` if the LLM call failed.
        The conversation is marked closed regardless of LLM success.
        """
        checkpoints = self._conv_store.get_checkpoints(conversation_id)
        checkpoint_summaries = [c["summary"] for c in checkpoints]

        if checkpoints:
            last_seq = checkpoints[-1]["sequence_number"]
            recent_messages = self._conv_store.get_messages_since_checkpoint(
                conversation_id, last_seq
            )
        else:
            recent_messages = self._conv_store.get_messages_between(
                conversation_id, None, None
            )

        messages = self._build_conversation_summary_prompt(
            checkpoint_summaries, recent_messages
        )
        summary = self._call_llm(messages)

        if summary is not None:
            self._conv_store.set_conversation_summary(conversation_id, summary)
            try:
                self._emb_store.index_conversation_summary(
                    conversation_id=conversation_id,
                    summary=summary,
                    metadata={},
                )
            except Exception:
                logger.exception(
                    "Failed to index conversation summary for %s",
                    conversation_id,
                )
        else:
            self._conv_store.close_conversation(conversation_id)

        return summary

    def _build_checkpoint_prompt(
        self,
        segment: list[dict[str, Any]],
        prev_summary: Optional[str],
    ) -> list[dict[str, str]]:
        """Build the LLM messages array for checkpoint summary generation."""
        if prev_summary:
            prev_context = (
                f"Previous checkpoint summary for context: {prev_summary}\n\n"
            )
        else:
            prev_context = ""

        system_content = _CHECKPOINT_SYSTEM_PROMPT.format(
            prev_context=prev_context,
            checkpoint_max=self._config.get_setting(
                "conversation_memory.checkpoint_max_tokens", 200
            ),
        )

        transcript_lines: list[str] = []
        for msg in segment:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            transcript_lines.append(f"{role.capitalize()}: {content}")
        transcript = "\n".join(transcript_lines)

        return [
            {"role": "system", "content": system_content},
            {"role": "user", "content": transcript},
        ]

    def _build_conversation_summary_prompt(
        self,
        checkpoint_summaries: list[str],
        recent_messages: list[dict[str, Any]],
    ) -> list[dict[str, str]]:
        """Build the LLM messages array for conversation-level summary."""
        if checkpoint_summaries:
            cp_lines = [
                f"## Checkpoint {i + 1}\n{s}"
                for i, s in enumerate(checkpoint_summaries)
            ]
            checkpoint_block = (
                "Checkpoint summaries:\n" + "\n\n".join(cp_lines) + "\n\n"
            )
        else:
            checkpoint_block = ""

        if recent_messages:
            msg_lines = []
            for msg in recent_messages:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                msg_lines.append(f"{role.capitalize()}: {content}")
            recent_block = (
                "Recent messages (not yet checkpointed):\n"
                + "\n".join(msg_lines)
                + "\n\n"
            )
        else:
            recent_block = ""

        system_content = _CONVERSATION_SYSTEM_PROMPT.format(
            checkpoint_block=checkpoint_block,
            recent_block=recent_block,
            conversation_max=self._config.get_setting(
                "conversation_memory.conversation_max_tokens", 500
            ),
        )

        return [
            {"role": "system", "content": system_content},
            {"role": "user", "content": "Generate the conversation summary."},
        ]

    def _call_llm(
        self, messages: list[dict[str, str]]
    ) -> Optional[str]:
        """Call the LLM and extract content text. Returns None on failure."""
        provider = self._config.get_setting(
            "conversation_memory.summary_provider", None
        )
        model = self._config.get_setting(
            "conversation_memory.summary_model", None
        )
        if provider is None:
            provider = llm_service.DEFAULT_PROVIDER
        if model is None:
            model = llm_service.DEFAULT_MODEL

        try:
            response = llm_service.chat_completion(
                messages=messages,
                provider=provider,
                model=model,
                stream=False,
            )
        except Exception:
            logger.exception("LLM call failed for summary generation")
            return None

        try:
            return str(response.choices[0].message.content)
        except (AttributeError, IndexError):
            logger.error("Malformed LLM response for summary generation")
            return None


_service: Optional[SummaryGenerationService] = None


def get_summary_service() -> SummaryGenerationService:
    global _service
    if _service is None:
        from ganesh_backend.routers.conversations import get_conversation_service
        from ganesh_backend.services.summary_embeddings import (
            get_summary_embedding_store,
        )

        _service = SummaryGenerationService(
            conversation_store=get_conversation_service(),
            summary_embedding_store=get_summary_embedding_store(),
            config=config_service,
        )
    return _service


def reset_summary_service() -> None:
    global _service
    _service = None


def set_summary_service(svc: SummaryGenerationService) -> None:
    global _service
    _service = svc
