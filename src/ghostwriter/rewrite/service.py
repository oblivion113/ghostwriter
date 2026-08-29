from __future__ import annotations

from dataclasses import dataclass

from ghostwriter.model import Draft

from .pi_rpc import PiRpcSession
from .placeholders import AttachmentProtector, PlaceholderIntegrityError


@dataclass(frozen=True, slots=True)
class RewriteOptions:
    translate: bool = True
    tidy: bool = True
    source_language: str = "auto-detect"
    target_language: str = "English"
    provider: str = ""
    model: str = ""

    def validate(self) -> None:
        if not self.translate and not self.tidy:
            raise ValueError("Enable translation, tidying, or both")
        if self.translate and not self.target_language.strip():
            raise ValueError("A target language is required for translation")


class RewriteSession:
    def __init__(self, draft: Draft, options: RewriteOptions) -> None:
        options.validate()
        self.options = options
        self.protector = AttachmentProtector(draft.text, draft.attachments)
        self.rpc = PiRpcSession(provider=options.provider, model=options.model)

    def _initial_prompt(self, text: str) -> str:
        options = self.options
        tasks: list[str] = []
        if options.translate:
            source = options.source_language.strip() or "auto-detect"
            tasks.append(
                f"Translate faithfully from {source} into {options.target_language.strip()}."
            )
        else:
            tasks.append("Keep the original language unchanged.")
        if options.tidy:
            tasks.append(
                "Correct transcription, spelling, grammar, punctuation, and obvious wording errors. "
                "Organize the draft into clear paragraphs and add concise Markdown headings only when "
                "they genuinely improve readability. Preserve meaning, detail, tone, and instructions."
            )
        else:
            tasks.append("Do not reorganize or stylistically rewrite beyond what fluent translation requires.")

        instructions = "\n".join(f"- {task}" for task in tasks)
        return f"""Transform the draft under these requirements:
{instructions}
- Return the entire transformed draft and nothing else.
- Preserve every __GW_*_ATTACHMENT_####__ token byte-for-byte, exactly once, near the same semantic context.

DRAFT START
{self.protector.protect(text)}
DRAFT END"""

    @staticmethod
    def _revision_prompt(protected_text: str, feedback: str) -> str:
        return f"""Revise the current candidate using this feedback:
{feedback.strip()}

Return the entire revised draft and nothing else. Preserve every attachment placeholder exactly.

CURRENT CANDIDATE START
{protected_text}
CURRENT CANDIDATE END"""

    async def _restore_with_repair(self, result: str) -> str:
        try:
            return self.protector.restore(result)
        except PlaceholderIntegrityError as first_error:
            repair = await self.rpc.prompt(
                "Your previous answer corrupted one or more immutable attachment placeholders. "
                "Reissue the complete transformed draft, using the original source and previous answer "
                "in this conversation. Every __GW_*_ATTACHMENT_####__ token from the original source "
                "must appear byte-for-byte exactly once. Return only the corrected draft."
            )
            try:
                return self.protector.restore(repair)
            except PlaceholderIntegrityError as second_error:
                raise PlaceholderIntegrityError(
                    f"Attachment integrity failed after one automatic repair: {second_error}"
                ) from first_error

    async def transform(self, text: str) -> str:
        result = await self.rpc.prompt(self._initial_prompt(text))
        return await self._restore_with_repair(result)

    async def revise(self, current_text: str, feedback: str) -> str:
        if not feedback.strip():
            raise ValueError("Revision feedback cannot be empty")
        protected = self.protector.protect(current_text)
        result = await self.rpc.prompt(self._revision_prompt(protected, feedback))
        return await self._restore_with_repair(result)

    async def close(self) -> None:
        await self.rpc.close()
