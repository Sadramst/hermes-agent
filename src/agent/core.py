"""Coordinate skills, memory, documents, and model completions."""

from __future__ import annotations

from dataclasses import dataclass

from agent import __version__
from agent.context import CONTEXT_PASSAGES, context_block, passage_label
from services.chroma import ChromaClient, ChromaError
from services.chunking import OVERLAP_CHARS, chunk_id, chunk_text, content_hash
from services.documents import (
    MAX_LIMIT,
    MAX_QUERY_CHARS,
    check_document_id,
    check_document_text,
    check_limit,
    check_query,
    check_source,
)
from services.embedder import HASH_NAME, EmbeddingError, build_embedder
from services.model import MAX_PROMPT_CHARS
from services.rerank import fuse
from agent.decisions.packs import ACTIVE_PACKS
from agent.decisions.guardrails import PACK as GUARD_PACK
from agent.decisions.guardrails import held_reply, record_screen, screen
from agent.decisions.supervisor import PACK as SUPERVISOR_PACK
from agent.decisions.supervisor import completion_evidence, completion_steps
from agent.decisions.supervisor import judge as judge_step
from agent.decisions.supervisor import STOP_TEXT, loop_evidence, loop_steps, record_step
from agent.decisions.model_router import PACK as ROUTER_PACK
from agent.decisions.model_router import judge as judge_route
from agent.decisions.model_router import record_route
from agent.decisions.memory_gate import PACK as MEMORY_PACK
from agent.decisions.memory_gate import judge as judge_memory
from agent.decisions.memory_gate import record_memory
from agent.decisions.tool_gate import PACK as TOOL_PACK
from agent.decisions.tool_gate import hold_for
from agent.decisions.tool_gate import judge as judge_tools
from agent.decisions.tool_gate import logged_names, record_tools
from agent.decisions.passage_filter import PACK as PASSAGE_PACK
from agent.decisions.passage_filter import (
    judge,
    passage_rows,
    record_passages,
    shown_ids,
    visible_matches,
)
from agent.decisions.skill_suggestion import (
    PACK,
    record_suggestion,
    suggest,
    suggestion_block,
)
from agent.prompt import assemble_completion_prompt
from agent.tools import MAX_STEPS, TOOL_ARGUMENTS, ToolCall, ToolResult, run_calls
from services.jev import JevClient, JevError
from services.grok import GrokClient, GrokError
from services.model import ModelClient, ModelNotConfigured, check_prompt
from skills.loader import Skill, SkillLoader
from memory.store import MemoryStore
from utils.logging import configure_logging
from utils.settings import Settings

# Neighbors fetched per requested result, so the keyword fusion and the passage filter can reorder.
FETCH_FACTOR = 2


class MemoryIndexOff(ValueError):
    """Raised when memory search is asked for while HERMES_MEMORY_INDEX is off."""


class HermesAgent:
    """In-process agent facade used by the API and the CLI."""

    def __init__(
        self,
        settings: Settings,
        chroma_client: ChromaClient | None = None,
        model_client: ModelClient | None = None,
        jev_client: object | None = None,
        grok_client: object | None = None,
        embedder: object | None = None,
        memory_chroma: object | None = None,
    ) -> None:
        self.settings = settings
        self.log = configure_logging(settings.log_level)
        self.memory = MemoryStore(settings.memory_dir)
        self.skills = SkillLoader(settings.skills_dir)
        self.embedder = embedder if embedder is not None else build_embedder(settings)
        dimension = getattr(self.embedder, "dimension", None)
        self.chroma = chroma_client or ChromaClient(
            settings.chroma_host,
            settings.chroma_port,
            settings.chroma_auth_token,
            collection=settings.documents_collection,
            dimension=dimension,
        )
        self.memory_chroma = memory_chroma
        bind = getattr(self.chroma, "bound_to", None)
        if self.memory_chroma is None and settings.memory_index and callable(bind):
            self.memory_chroma = bind(settings.memory_collection, dimension)
        self.model = model_client if model_client is not None else _model_client(settings)
        self.jev = jev_client if jev_client is not None else _jev_client(settings)
        self.grok = grok_client if grok_client is not None else _grok_client(settings)
        self.log.info(
            "agent.ready env=%s chroma=%s:%s jev_mode=%s",
            settings.hermes_env,
            settings.chroma_host,
            settings.chroma_port,
            settings.jev_mode,
        )

    def list_skills(self) -> list[Skill]:
        skills = self.skills.load()
        self.log.info("skills.loaded count=%s env=%s", len(skills), self.settings.hermes_env)
        return skills

    def remember(self, key: str, value: str) -> bool:
        self.memory.check(key)
        verdict = _memory_gate(
            mode=self.settings.jev_mode,
            client=self.jev,
            model=self.settings.jev_model,
            key=key,
            value=value,
        )
        keep = verdict is None or verdict.keep
        if keep:
            self.memory.write(key, value)
            self.log.info("memory.write key=%s env=%s", key, self.settings.hermes_env)
            self._index_memory(key, value)
        if verdict is not None:
            record_memory(
                mode=self.settings.jev_mode,
                model=verdict.model,
                memory_key=key,
                kind=verdict.kind,
                answers=verdict.answers,
                reason=verdict.reason,
                persisted=keep,
                enforced=self.settings.jev_mode == "soft",
            )
        return keep

    def delegate_to_grok(self, task: str) -> str:
        """Post one task. The result is the handoff id."""
        send = getattr(self.grok, "send", None)
        if not callable(send):
            raise GrokError()
        handoff_id = send(task)
        if not isinstance(handoff_id, str) or not handoff_id:
            raise GrokError()
        self.log.info("grok.handoff id=%s env=%s", handoff_id, self.settings.hermes_env)
        return handoff_id

    def recall(self, key: str) -> str:
        self.log.info("memory.read key=%s env=%s", key, self.settings.hermes_env)
        return self.memory.read(key)

    def health(self) -> dict[str, object]:
        reachable = self.chroma.heartbeat()
        self.log.debug("chroma.heartbeat reachable=%s env=%s", reachable, self.settings.hermes_env)
        return _health_payload(self.settings, reachable)

    def save_document(self, doc_id: str, text: str, source: str = "") -> dict[str, object]:
        """Chunk, embed, and store one document. Unchanged text is not embedded again."""
        checked_id = check_document_id(doc_id)
        checked_text = check_document_text(text)
        checked_source = check_source(source)
        chunks = chunk_text(checked_text)
        digest = content_hash(checked_text)
        collection = self.settings.documents_collection
        if self._unchanged(self.chroma, "doc_id", checked_id, digest, len(chunks), checked_source):
            self.log.info("documents.unchanged id=%s env=%s", checked_id, self.settings.hermes_env)
            return {"id": checked_id, "collection": collection, "chunks": len(chunks), "unchanged": True}
        vectors = self.embedder.embed_passages(chunks)
        metadatas: list[dict[str, str | int]] = []
        for index in range(len(chunks)):
            metadata: dict[str, str | int] = {
                "doc_id": checked_id,
                "chunk": index,
                "chunks": len(chunks),
                "doc_sha256": digest,
                "embedder": self._embedder_name(),
            }
            if checked_source:
                metadata["source"] = checked_source
            metadatas.append(metadata)
        self.chroma.delete_source("doc_id", checked_id)
        self.chroma.upsert_chunks(
            [chunk_id(checked_id, index) for index in range(len(chunks))],
            chunks,
            vectors,
            metadatas,
        )
        self.log.info(
            "documents.write id=%s chunks=%s env=%s",
            checked_id,
            len(chunks),
            self.settings.hermes_env,
        )
        return {"id": checked_id, "collection": collection, "chunks": len(chunks), "unchanged": False}

    def search_documents(self, query: str, limit: int = 5) -> dict[str, object]:
        """Return saved passages for a query string, best first.

        Hermes fetches extra neighbors, reorders them with a keyword ranking,
        then applies the passage pack. Shadow logs which matches reach the
        helping level and still returns the top neighbors. Soft returns only
        those matches. A Jev error returns the top neighbors. Mode off does not call Jev.
        """
        checked_query = check_query(query)
        checked_limit = check_limit(limit)
        fetch = min(MAX_LIMIT, checked_limit * FETCH_FACTOR)
        matches = self.chroma.query_documents(self.embedder.embed_query(checked_query), fetch)
        visible = _passage_filter(
            mode=self.settings.jev_mode,
            client=self.jev,
            model=self.settings.jev_model,
            query=checked_query,
            matches=fuse(checked_query, matches),
        )[:checked_limit]
        self.log.info(
            "documents.search matches=%s env=%s",
            len(visible),
            self.settings.hermes_env,
        )
        return {"collection": self.settings.documents_collection, "matches": visible}

    def search_memory(self, query: str, limit: int = 5) -> dict[str, object]:
        """Return memory records whose text is close to the query. The files stay the source of truth."""
        if self.memory_chroma is None:
            raise MemoryIndexOff("Memory search is off")
        checked_query = check_query(query)
        checked_limit = check_limit(limit)
        matches = self.memory_chroma.query_documents(
            self.embedder.embed_query(checked_query),
            min(MAX_LIMIT, checked_limit * FETCH_FACTOR),
        )
        records: list[dict[str, object]] = []
        seen: set[str] = set()
        for match in fuse(checked_query, matches):
            key = match.get("source_id", match.get("id"))
            if not isinstance(key, str) or key in seen:
                continue
            seen.add(key)
            records.append({"key": key, "text": match.get("text", ""), "distance": match.get("distance")})
            if len(records) == checked_limit:
                break
        self.log.info("memory.search matches=%s env=%s", len(records), self.settings.hermes_env)
        return {"collection": self.settings.memory_collection, "matches": records}

    def reindex_memory(self) -> dict[str, int]:
        """Index every stored memory file. Safe to repeat."""
        if self.memory_chroma is None:
            raise MemoryIndexOff("Memory search is off")
        indexed = 0
        for key in self.memory.keys():
            if self._index_memory(key, self.memory.read(key)):
                indexed += 1
        return {"indexed": indexed}

    def migrate_documents(self, source_collection: str) -> dict[str, int]:
        """Copy documents from an older collection into the active one, embedding them again.

        Whole-document rows copy exactly. Chunked rows are rejoined at their overlap.
        Rows whose id is not a valid document id are skipped.
        """
        if source_collection == self.settings.documents_collection:
            raise ValueError("The source collection is the active collection")
        bind = getattr(self.chroma, "bound_to", None)
        if not callable(bind):
            raise ValueError("This Chroma client cannot open another collection")
        source = bind(source_collection, None)
        grouped: dict[str, list[tuple[int, str]]] = {}
        sources: dict[str, str] = {}
        offset = 0
        while True:
            rows = source.page(offset)
            if not rows:
                break
            offset += len(rows)
            for row in rows:
                doc_id = row.get("source_id", row.get("id"))
                text = row.get("text")
                if not isinstance(doc_id, str) or not isinstance(text, str):
                    continue
                chunk = row.get("chunk", 0)
                grouped.setdefault(doc_id, []).append((chunk if isinstance(chunk, int) else 0, text))
                if isinstance(row.get("source"), str):
                    sources[doc_id] = str(row["source"])
        migrated = 0
        skipped = 0
        for doc_id, parts in grouped.items():
            text = _rejoin([part for _, part in sorted(parts)])
            try:
                self.save_document(doc_id, text, sources.get(doc_id, ""))
            except ValueError:
                skipped += 1
                continue
            migrated += 1
        self.log.info(
            "documents.migrate from=%s migrated=%s skipped=%s env=%s",
            source_collection,
            migrated,
            skipped,
            self.settings.hermes_env,
        )
        return {"migrated": migrated, "skipped": skipped}

    def _index_memory(self, key: str, value: str) -> bool:
        """Mirror one memory record into the memory collection. A failure keeps the file write."""
        if self.memory_chroma is None:
            return False
        chunks = chunk_text(value)
        if not chunks:
            return False
        digest = content_hash(value)
        try:
            if self._unchanged(self.memory_chroma, "key", key, digest, len(chunks), ""):
                return True
            vectors = self.embedder.embed_passages(chunks)
            self.memory_chroma.delete_source("key", key)
            self.memory_chroma.upsert_chunks(
                [chunk_id(key, index) for index in range(len(chunks))],
                chunks,
                vectors,
                [
                    {
                        "key": key,
                        "chunk": index,
                        "chunks": len(chunks),
                        "doc_sha256": digest,
                        "embedder": self._embedder_name(),
                    }
                    for index in range(len(chunks))
                ],
            )
        except (ChromaError, EmbeddingError) as exc:
            self.log.warning(
                "memory.index_failed key=%s status=%s env=%s",
                key,
                getattr(exc, "status", None),
                self.settings.hermes_env,
            )
            return False
        self.log.info("memory.index key=%s chunks=%s env=%s", key, len(chunks), self.settings.hermes_env)
        return True

    def _unchanged(
        self,
        chroma: object,
        field: str,
        value: str,
        digest: str,
        count: int,
        source: str,
    ) -> bool:
        lookup = getattr(chroma, "source_metadatas", None)
        if not callable(lookup):
            return False
        stored = lookup(field, value)
        if len(stored) != count:
            return False
        name = self._embedder_name()
        return all(
            row.get("doc_sha256") == digest
            and row.get("embedder") == name
            and str(row.get("source", "")) == source
            for row in stored
        )

    def _embedder_name(self) -> str:
        name = getattr(self.embedder, "name", HASH_NAME)
        return name if isinstance(name, str) else HASH_NAME

    def _retrieve_context(
        self,
        prompt: str,
        skills: list[Skill],
        suggestion: str | None,
    ) -> tuple[str | None, list[str]]:
        """Return the Context block and its passage labels. Shadow logs and returns nothing."""
        mode = self.settings.rag_mode
        if mode not in {"shadow", "soft"}:
            return None, []
        try:
            found = self.search_documents(prompt[:MAX_QUERY_CHARS], CONTEXT_PASSAGES)
        except (ChromaError, EmbeddingError, ValueError) as exc:
            self.log.warning(
                "rag.context mode=%s reason=search_failed status=%s env=%s",
                mode,
                getattr(exc, "status", None),
                self.settings.hermes_env,
            )
            return None, []
        matches = found.get("matches")
        passages = [match for match in matches if isinstance(match, dict)] if isinstance(matches, list) else []
        block, used = _fitted_context(prompt, skills, suggestion, passages)
        labels = [passage_label(passage) for passage in used]
        if block is not None and mode == "soft" and self.settings.jev_mode == "soft":
            route = _guard_screen(
                mode=self.settings.jev_mode,
                client=self.jev,
                model=self.settings.jev_model,
                side="inbound",
                text=block,
            )
            if route != "pass":
                self.log.info(
                    "rag.context mode=%s passages=%s used=false reason=guardrail env=%s",
                    mode,
                    ",".join(labels),
                    self.settings.hermes_env,
                )
                return None, []
        inject = mode == "soft" and block is not None
        self.log.info(
            "rag.context mode=%s passages=%s used=%s env=%s",
            mode,
            ",".join(labels),
            str(inject).lower(),
            self.settings.hermes_env,
        )
        if not inject:
            return None, []
        return block, labels

    def run_tools(self, calls: list[ToolCall]) -> list[ToolResult]:
        """Run an allowlisted batch. Soft mode may hold a call the allowlist would run.

        Soft mode also stops calls that follow a looping supervisor judgment.
        Shadow logs that judgment and still runs the batch.
        """
        if len(calls) > MAX_STEPS:
            raise ValueError(f"A tool run is limited to {MAX_STEPS} calls")
        verdict = _tool_gate(
            mode=self.settings.jev_mode,
            client=self.jev,
            model=self.settings.jev_model,
            calls=calls,
        )
        enforce = self.settings.jev_mode == "soft" and verdict is not None
        holds = None
        if enforce and verdict is not None:
            holds = [
                hold_for(
                    name=call.name,
                    index=index,
                    choice=verdict.choice,
                    reason=verdict.reason,
                    answers=verdict.answers,
                )
                for index, call in enumerate(calls)
            ]
        if self.settings.jev_mode == "soft":
            results = self._run_until_loop(calls, holds)
        else:
            results = run_calls(self, calls, holds)
        if verdict is not None:
            record_tools(
                mode=self.settings.jev_mode,
                model=verdict.model,
                call_names=logged_names(calls),
                choice=verdict.choice,
                statuses=[result.status for result in results],
                answers=verdict.answers,
                reason=verdict.reason,
                enforced=enforce,
            )
        if self.settings.jev_mode != "soft":
            _supervise(
                mode=self.settings.jev_mode,
                client=self.jev,
                model=self.settings.jev_model,
                side="loop",
                steps=loop_steps(results),
                evidence=loop_evidence(results),
            )
        return results

    def _run_until_loop(
        self,
        calls: list[ToolCall],
        holds: list[str] | None,
    ) -> list[ToolResult]:
        """Run calls until a looping judgment. Later calls are not executed."""
        results: list[ToolResult] = []
        stop = False
        for index, call in enumerate(calls):
            if stop:
                results.append(_loop_stop(self, call))
                continue
            held = None if holds is None else [holds[index]]
            results.extend(run_calls(self, [call], held))
            stop = _supervise(
                mode=self.settings.jev_mode,
                client=self.jev,
                model=self.settings.jev_model,
                side="loop",
                steps=loop_steps(results),
                evidence=loop_evidence(results),
                stop_remaining=index < len(calls) - 1,
            )
        return results

    def complete(self, prompt: str) -> dict[str, object]:
        """Send one completion: skill index, optional retrieved context, then the caller's prompt.

        Shadow mode asks the skill-suggestion pack and logs the winner.
        Soft mode asks the same pack and adds a skill_relevance block.
        The model may ignore that block. Shadow logs a guardrail route and
        still returns the model reply. Soft withholds that reply on review
        or block, including when Jev fails. Mode off does not call Jev.

        HERMES_RAG_MODE shadow searches and logs the passage labels it would add.
        Soft adds them as a Context block and returns their labels as `sources`.
        A search failure completes without context.
        """
        if self.model is None:
            raise ModelNotConfigured("Model provider is not configured")
        checked_prompt = check_prompt(prompt)
        skills = self.skills.load()
        check_prompt(assemble_completion_prompt(checked_prompt, skills))
        block = _skill_suggestion(
            mode=self.settings.jev_mode,
            client=self.jev,
            model=self.settings.jev_model,
            request=checked_prompt,
            skills=skills,
        )
        checked = check_prompt(assemble_completion_prompt(checked_prompt, skills, block))
        inbound = _guard_screen(
            mode=self.settings.jev_mode,
            client=self.jev,
            model=self.settings.jev_model,
            side="inbound",
            text=checked_prompt,
        )
        name = self.settings.model_name or self.model.model
        held = held_reply(inbound) if self.settings.jev_mode == "soft" else None
        if held is not None:
            self.log.info(
                "model.complete model=%s skills=%s env=%s",
                name,
                len(skills),
                self.settings.hermes_env,
            )
            _supervise(
                mode=self.settings.jev_mode,
                client=self.jev,
                model=self.settings.jev_model,
                side="completion",
                steps=completion_steps("held"),
                evidence=completion_evidence(name, len(skills)),
            )
            return {"text": held, "model": name}
        context, sources = self._retrieve_context(checked_prompt, skills, block)
        if context is not None:
            checked = check_prompt(assemble_completion_prompt(checked_prompt, skills, block, context))
        completion_model = _model_route(
            mode=self.settings.jev_mode,
            client=self.jev,
            jev_model=self.settings.jev_model,
            request=checked_prompt,
            frontier_name=self.settings.model_name or self.model.model,
            small_name=self.settings.model_small,
        )
        text = self.model.complete(checked, model=completion_model)
        outbound = _guard_screen(
            mode=self.settings.jev_mode,
            client=self.jev,
            model=self.settings.jev_model,
            side="outbound",
            text=text,
        )
        replacement = held_reply(outbound) if self.settings.jev_mode == "soft" else None
        if replacement is not None:
            text = replacement
        name = self.settings.model_name or self.model.model
        self.log.info(
            "model.complete model=%s skills=%s env=%s",
            completion_model,
            len(skills),
            self.settings.hermes_env,
        )
        _supervise(
            mode=self.settings.jev_mode,
            client=self.jev,
            model=self.settings.jev_model,
            side="completion",
            steps=completion_steps("ran"),
            evidence=completion_evidence(name, len(skills)),
        )
        result: dict[str, object] = {"text": text, "model": name}
        if sources:
            result["sources"] = sources
        return result


def _fitted_context(
    prompt: str,
    skills: list[Skill],
    suggestion: str | None,
    passages: list[dict[str, object]],
) -> tuple[str | None, list[dict[str, object]]]:
    """Keep the best passages that fit the prompt cap. Lower-ranked passages are dropped first."""
    for count in range(len(passages), 0, -1):
        kept = passages[:count]
        block = context_block(kept)
        if block is None:
            continue
        if len(assemble_completion_prompt(prompt, skills, suggestion, block)) <= MAX_PROMPT_CHARS:
            return block, [passage for passage in kept if passage_label(passage)]
    return None, []


def _rejoin(parts: list[str]) -> str:
    """Join chunks written with overlap. Parts that share no overlap are joined by a blank line."""
    if not parts:
        return ""
    text = parts[0]
    for part in parts[1:]:
        overlap = 0
        for size in range(min(len(text), len(part), 2 * OVERLAP_CHARS), 0, -1):
            if text.endswith(part[:size]):
                overlap = size
                break
        text = text + part[overlap:] if overlap >= 20 else f"{text}\n\n{part}"
    return text


def _model_client(settings: Settings) -> ModelClient | None:
    if not (settings.model_base_url and settings.model_name and settings.model_api_key):
        return None
    return ModelClient(settings.model_base_url, settings.model_name, settings.model_api_key)


def _jev_client(settings: Settings) -> JevClient | None:
    if settings.jev_mode == "off" or not settings.jev_api_key:
        return None
    return JevClient(settings.jev_base_url, settings.jev_model, settings.jev_api_key)


def _grok_client(settings: Settings) -> GrokClient | None:
    if settings.grok_handoff != "on":
        return None
    if not (settings.grok_webhook_url and settings.grok_alias_token and settings.grok_handoff_secret):
        return None
    return GrokClient(settings.grok_webhook_url, settings.grok_alias_token, settings.grok_handoff_secret)


def _skill_suggestion(
    *,
    mode: str,
    client: object | None,
    model: str,
    request: str,
    skills: list[Skill],
) -> str | None:
    """Return the soft-mode advisory block. Shadow logs and returns nothing."""
    if mode not in {"shadow", "soft"} or client is None or PACK not in ACTIVE_PACKS:
        return None
    names = [skill.name for skill in skills]
    try:
        result = suggest(client, request, skills)
    except (JevError, ValueError):
        record_suggestion(
            mode=mode,
            model=model,
            skill_names=names,
            answers={},
            suggested="",
            reason="jev_error",
        )
        return None
    suggested = result.name or ""
    reason = result.reason
    if suggested not in names:
        suggested = ""
        if result.name:
            reason = "unknown"
    inject = mode == "soft" and reason != "no_skills"
    record_suggestion(
        mode=mode,
        model=result.model or model,
        skill_names=names,
        answers=result.answers,
        suggested=suggested,
        reason=reason,
        suggestion_in_prompt=inject,
    )
    if not inject:
        return None
    return suggestion_block(suggested or None)


def _passage_filter(
    *,
    mode: str,
    client: object | None,
    model: str,
    query: str,
    matches: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Return the matches to show. Shadow logs and leaves the neighbor list intact."""
    if mode not in {"shadow", "soft"} or client is None or PASSAGE_PACK not in ACTIVE_PACKS:
        return matches
    ids = [row["id"] for row in passage_rows(matches)]
    try:
        result = judge(client, query, matches)
    except (JevError, ValueError):
        record_passages(
            mode=mode,
            model=model,
            match_ids=ids,
            shown=[],
            answers={},
            reason="jev_error",
            filtered=False,
        )
        return matches
    shown = shown_ids(result.answers, ids) if result.reason == "ok" else []
    apply = mode == "soft" and result.reason == "ok"
    record_passages(
        mode=mode,
        model=result.model or model,
        match_ids=ids,
        shown=shown,
        answers=result.answers,
        reason=result.reason,
        filtered=apply,
    )
    if not apply:
        return matches
    return visible_matches(matches, shown)


def _guard_screen(
    *,
    mode: str,
    client: object | None,
    model: str,
    side: str,
    text: str,
) -> str:
    """Log one guardrail route. Soft mode is the only mode that honors it."""
    if mode not in {"shadow", "soft"} or client is None or GUARD_PACK not in ACTIVE_PACKS:
        return "pass"
    enforce = mode == "soft"
    try:
        result = screen(client, side, text)
    except (JevError, ValueError):
        record_screen(
            mode=mode,
            model=model,
            side=side,
            route="review",
            answers={},
            reason="jev_error",
            enforced=enforce,
        )
        return "review"
    record_screen(
        mode=mode,
        model=result.model or model,
        side=side,
        route=result.route,
        answers=result.answers,
        reason=result.reason,
        enforced=enforce,
    )
    return result.route


@dataclass(frozen=True)
class _MemoryVerdict:
    keep: bool
    model: str
    kind: str
    answers: dict[str, object]
    reason: str


def _memory_gate(
    *,
    mode: str,
    client: object | None,
    model: str,
    key: str,
    value: str,
) -> _MemoryVerdict | None:
    """Judge one write. Shadow always keeps it. Soft keeps a durable kind or a Jev error."""
    if mode not in {"shadow", "soft"} or client is None or MEMORY_PACK not in ACTIVE_PACKS:
        return None
    try:
        result = judge_memory(client, key, value)
    except (JevError, ValueError):
        return _MemoryVerdict(keep=True, model=model, kind="", answers={}, reason="jev_error")
    keep = mode != "soft" or result.reason == "ok"
    return _MemoryVerdict(
        keep=keep,
        model=result.model or model,
        kind=result.kind,
        answers=result.answers,
        reason=result.reason,
    )


@dataclass(frozen=True)
class _ToolVerdict:
    model: str
    choice: str
    answers: dict[str, object]
    reason: str


def _tool_gate(
    *,
    mode: str,
    client: object | None,
    model: str,
    calls: list[ToolCall],
) -> _ToolVerdict | None:
    """Log-only tool judgment. An empty batch, or mode off, makes no Jev call."""
    if not calls or mode not in {"shadow", "soft"} or client is None or TOOL_PACK not in ACTIVE_PACKS:
        return None
    try:
        result = judge_tools(client, calls)
    except (JevError, ValueError):
        return _ToolVerdict(model=model, choice="", answers={}, reason="jev_error")
    return _ToolVerdict(
        model=result.model or model,
        choice=result.choice,
        answers=result.answers,
        reason=result.reason,
    )


def _supervise(
    *,
    mode: str,
    client: object | None,
    model: str,
    side: str,
    steps: list[dict[str, str]],
    evidence: list[dict[str, str]],
    stop_remaining: bool = False,
) -> bool:
    """Log one supervisor judgment. Empty steps and mode off make no Jev call.

    A looping judgment stops later tool calls only in soft mode. Completion
    text is never changed here. A Jev error does not stop the batch.
    """
    if not steps or mode not in {"shadow", "soft"} or client is None or SUPERVISOR_PACK not in ACTIVE_PACKS:
        return False
    try:
        result = judge_step(client, steps, evidence)
    except (JevError, ValueError):
        record_step(
            mode=mode,
            model=model,
            side=side,
            reason="jev_error",
            looping=False,
            done=False,
            answers={},
        )
        return False
    enforced = mode == "soft" and side == "loop" and result.reason == "looping" and stop_remaining
    record_step(
        mode=mode,
        model=result.model or model,
        side=side,
        reason=result.reason,
        looping=result.looping,
        done=result.done,
        answers=result.answers,
        enforced=enforced,
    )
    return enforced


def _loop_stop(agent: HermesAgent, call: ToolCall) -> ToolResult:
    """Record a call that soft mode did not run after a looping judgment."""
    result = ToolResult(call.name, "stopped", STOP_TEXT)
    name = call.name if call.name in TOOL_ARGUMENTS else "unknown"
    agent.log.info(
        "tools.run name=%s status=%s env=%s",
        name,
        result.status,
        agent.settings.hermes_env,
    )
    return result


def _model_route(
    *,
    mode: str,
    client: object | None,
    jev_model: str,
    request: str,
    frontier_name: str,
    small_name: str | None,
) -> str:
    """Log a tier. In soft mode may return small_name when the judge says small/ok."""
    if mode not in {"shadow", "soft"} or client is None or ROUTER_PACK not in ACTIVE_PACKS:
        return frontier_name
    try:
        result = judge_route(client, request)
    except (JevError, ValueError):
        record_route(mode=mode, model=jev_model, tier="frontier", answers={}, reason="jev_error")
        return frontier_name
    record_route(
        mode=mode,
        model=result.model or jev_model,
        tier=result.tier,
        answers=result.answers,
        reason=result.reason,
    )
    if (
        mode == "soft"
        and small_name
        and result.tier == "small"
        and result.reason == "ok"
    ):
        return small_name
    return frontier_name


def _health_payload(settings: Settings, reachable: bool) -> dict[str, object]:
    return {
        "status": "ok",
        "environment": settings.hermes_env,
        "version": __version__,
        "chroma": {
            "reachable": reachable,
            "host": settings.chroma_host,
            "port": settings.chroma_port,
        },
        "model": {
            "configured": settings.model_base_url is not None,
            "name": settings.model_name or "",
        },
        "jev": {
            "configured": settings.jev_api_key is not None,
            "mode": settings.jev_mode,
            "model": settings.jev_model,
        },
        "mcp": {
            "enabled": settings.mcp_enabled,
        },
        "grok": {
            "handoff": settings.grok_handoff,
        },
        "retrieval": {
            "rag_mode": settings.rag_mode,
            "embedder": settings.embed_model or HASH_NAME,
            "documents_collection": settings.documents_collection,
            "memory_index": settings.memory_index,
            "memory_collection": settings.memory_collection,
        },
    }
