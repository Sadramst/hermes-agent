"""Coordinate skills, memory, documents, model completions, and autonomous multi-step tool loops."""

from __future__ import annotations

import json

from agent import __version__
from agent.context import CONTEXT_PASSAGES, context_block, passage_label
from agent.profile import build_agent_system_prompt, load_personal_profile
from agent.prompt import assemble_completion_prompt
from agent.tools import (
    MAX_STEPS,
    ToolCall,
    ToolResult,
    agent_tool_schemas,
    run_calls,
)
from memory.store import MemoryStore
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
from services.ingest import ingest_directory as run_ingest_directory
from services.model import MAX_PROMPT_CHARS, ModelClient, ModelNotConfigured, check_prompt
from services.rerank import fuse
from services.workspace import DEFAULT_EXEC_TIMEOUT, WorkspaceManager
from skills.loader import Skill, SkillLoader
from utils.logging import configure_logging
from utils.settings import Settings
from utils.time import now_report

# Neighbors fetched per requested result so reciprocal-rank fusion can reorder matches.
FETCH_FACTOR = 2
MAX_AGENT_STEPS = 16


class MemoryIndexOff(ValueError):
    """Raised when memory search is asked for while HERMES_MEMORY_INDEX is off."""


class HermesAgent:
    """In-process agent facade used by the API, MCP server, and CLI."""

    def __init__(
        self,
        settings: Settings,
        chroma_client: ChromaClient | None = None,
        model_client: ModelClient | None = None,
        embedder: object | None = None,
        memory_chroma: object | None = None,
    ) -> None:
        self.settings = settings
        self.log = configure_logging(settings.log_level)
        self.memory = MemoryStore(settings.memory_dir)
        self.skills = SkillLoader(settings.skills_dir)
        self.profile = load_personal_profile(settings.profile_dir)
        self.workspace = WorkspaceManager(
            settings.projects_dir or None,
            mode=settings.workspace_mode,
            allowed_cmds=settings.workspace_allowed_cmds,
        )
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
        self.log.info(
            "agent.ready env=%s chroma=%s:%s",
            settings.hermes_env,
            settings.chroma_host,
            settings.chroma_port,
        )

    def list_skills(self) -> list[Skill]:
        skills = self.skills.load()
        self.log.info("skills.loaded count=%s env=%s", len(skills), self.settings.hermes_env)
        return skills

    def remember(self, key: str, value: str) -> bool:
        self.memory.check(key)
        self.memory.write(key, value)
        self.log.info("memory.write key=%s env=%s", key, self.settings.hermes_env)
        self._index_memory(key, value)
        return True

    def recall(self, key: str) -> str:
        self.log.info("memory.read key=%s env=%s", key, self.settings.hermes_env)
        return self.memory.read(key)

    def list_memories(self, prefix: str = "") -> list[str]:
        """Return stored memory keys in sorted order, optionally filtered by prefix."""
        cleaned = prefix.strip()
        keys = [key for key in self.memory.keys() if not cleaned or key.startswith(cleaned)]
        self.log.info("memory.list count=%s env=%s", len(keys), self.settings.hermes_env)
        return keys

    def current_time(self) -> dict[str, str]:
        """Return the current date, local time in the configured timezone, and UTC ISO timestamp."""
        return now_report(self.settings.timezone)

    def provider_status(self) -> dict[str, object]:
        """Return secret-free model provider and subscription readiness metadata."""
        return {
            "auth_mode": self.settings.provider_auth_mode,
            "configured": self.settings.model_base_url is not None,
            "model": self.settings.model_name or "",
            "gemini_subscription": {
                "supported_today": False,
                "status": "pending_official_nous_google_oauth",
                "note": (
                    "Gemini in Hermes runs via API key (OpenRouter or Google AI Studio) today. "
                    "Nous Research and Google are working on official approved Gemini subscription OAuth "
                    "(not live yet, no release date). Claude and ChatGPT OAuth subscriptions are supported "
                    "in hermes-gateway today."
                ),
            },
        }

    def health(self) -> dict[str, object]:
        reachable = self.chroma.heartbeat()
        self.log.debug("chroma.heartbeat reachable=%s env=%s", reachable, self.settings.hermes_env)
        return _health_payload(
            self.settings,
            reachable,
            profile_loaded=self.profile.loaded,
            workspace_enabled=self.workspace.enabled,
            workspace_mode=self.workspace.mode,
            project_count=self.workspace.project_count(),
        )

    def list_projects(self) -> list[dict[str, object]]:
        """Return project summaries inside the configured workspace directory."""
        return self.workspace.list_projects()

    def list_project_files(self, project: str, subpath: str = "", limit: int = 100) -> list[str]:
        """List non-secret files under one project inside the workspace."""
        return self.workspace.list_files(project, subpath, limit=limit)

    def read_project_file(
        self,
        project: str,
        rel_path: str,
        start_line: int = 1,
        end_line: int = 200,
    ) -> dict[str, object]:
        """Read a line range from one file inside a workspace project."""
        return self.workspace.read_file(project, rel_path, start_line=start_line, end_line=end_line)

    def search_project(self, project: str, query: str, limit: int = 20) -> list[dict[str, object]]:
        """Search text files in one workspace project for matching lines."""
        return self.workspace.search_files(project, query, limit=limit)

    def write_project_file(
        self,
        project: str,
        rel_path: str,
        content: str,
        create_dirs: bool = False,
    ) -> dict[str, object]:
        """Write or replace a text file inside a workspace project (rw mode only)."""
        written = self.workspace.write_file(project, rel_path, content, create_dirs=create_dirs)
        self.log.info(
            "workspace.write project=%s path=%s env=%s",
            project,
            written["path"],
            self.settings.hermes_env,
        )
        return written

    def run_project_command(
        self,
        project: str,
        argv: list[str],
        timeout: int = DEFAULT_EXEC_TIMEOUT,
    ) -> dict[str, object]:
        """Run an allowlisted command inside a workspace project (rw mode only)."""
        result = self.workspace.run_command(project, argv, timeout=timeout)
        self.log.info(
            "workspace.exec project=%s cmd=%s code=%s env=%s",
            project,
            argv[0],
            result["returncode"],
            self.settings.hermes_env,
        )
        return result

    def ingest_directory(
        self,
        directory: str,
        *,
        prefix: str = "brain",
        include_code: bool = False,
        max_files: int = 200,
    ) -> dict[str, object]:
        """Ingest Markdown/text (and optional code) files from `directory` into ChromaDB."""
        summary = run_ingest_directory(
            self,
            directory,
            prefix=prefix,
            include_code=include_code,
            max_files=max_files,
        )
        self.log.info(
            "brain.ingest prefix=%s ingested=%s unchanged=%s env=%s",
            prefix,
            summary["ingested"],
            summary["unchanged"],
            self.settings.hermes_env,
        )
        return summary

    def ingest_project(
        self,
        project: str,
        *,
        prefix: str = "",
        include_code: bool = False,
        max_files: int = 100,
    ) -> dict[str, object]:
        """Ingest one project directory from the configured workspace into ChromaDB."""
        proj_root = self.workspace.resolve_project(project)
        effective_prefix = prefix.strip() or f"proj-{project}"
        return self.ingest_directory(
            str(proj_root),
            prefix=effective_prefix,
            include_code=include_code,
            max_files=max_files,
        )

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
        """Return saved passages for a query string, ordered by hybrid vector + keyword fusion."""
        checked_query = check_query(query)
        checked_limit = check_limit(limit)
        fetch = min(MAX_LIMIT, checked_limit * FETCH_FACTOR)
        matches = self.chroma.query_documents(self.embedder.embed_query(checked_query), fetch)
        visible = fuse(checked_query, matches)[:checked_limit]
        self.log.info("documents.search matches=%s env=%s", len(visible), self.settings.hermes_env)
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
        """Copy documents from an older collection into the active one, embedding them again."""
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

    def run_tools(self, calls: list[ToolCall]) -> list[ToolResult]:
        """Run an allowlisted batch of tool calls in order."""
        if len(calls) > MAX_STEPS:
            raise ValueError(f"A tool run is limited to {MAX_STEPS} calls")
        return run_calls(self, calls)

    def complete(
        self,
        prompt: str,
        *,
        autonomous: bool = False,
        max_steps: int = MAX_STEPS,
    ) -> dict[str, object]:
        """Send one completion or run the autonomous multi-step tool loop when autonomous=True."""
        if autonomous:
            return self.run_agent(prompt, max_steps=max_steps)
        if self.model is None:
            raise ModelNotConfigured("Model provider is not configured")
        checked_prompt = check_prompt(prompt)
        skills = self.skills.load()
        checked = check_prompt(assemble_completion_prompt(checked_prompt, skills))
        context, sources = self._retrieve_context(checked_prompt, skills)
        if context is not None:
            checked = check_prompt(assemble_completion_prompt(checked_prompt, skills, context))
        name = self.settings.model_name or self.model.model
        text = self.model.complete(checked, model=name)
        self.log.info(
            "model.complete model=%s skills=%s env=%s",
            name,
            len(skills),
            self.settings.hermes_env,
        )
        result: dict[str, object] = {"text": text, "model": name}
        if sources:
            result["sources"] = sources
        return result

    def run_agent(self, prompt: str, *, max_steps: int = MAX_STEPS) -> dict[str, object]:
        """Run an autonomous multi-step tool-calling loop until the model answers or hits max_steps."""
        if isinstance(max_steps, bool) or not isinstance(max_steps, int) or not 1 <= max_steps <= MAX_AGENT_STEPS:
            raise ValueError(f"max_steps must be between 1 and {MAX_AGENT_STEPS}")
        if self.model is None:
            raise ModelNotConfigured("Model provider is not configured")
        checked_prompt = check_prompt(prompt)
        skills = self.skills.load()
        checked = check_prompt(assemble_completion_prompt(checked_prompt, skills))
        context, sources = self._retrieve_context(checked_prompt, skills)
        if context is not None:
            checked = check_prompt(assemble_completion_prompt(checked_prompt, skills, context))
        name = self.settings.model_name or self.model.model
        chat_fn = getattr(self.model, "chat", None)
        if not callable(chat_fn):
            text = self.model.complete(checked, model=name)
            steps_taken: list[dict[str, object]] = []
        else:
            system_prompt = build_agent_system_prompt(
                self.profile,
                timezone_name=self.settings.timezone,
                provider_auth_mode=self.settings.provider_auth_mode,
                workspace_enabled=self.workspace.enabled,
                workspace_mode=self.workspace.mode,
            )
            messages: list[dict[str, object]] = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": checked},
            ]
            steps_taken = []
            text = ""
            active_tools = agent_tool_schemas(self.settings.workspace_mode)
            for step_index in range(max_steps):
                turn = chat_fn(messages, tools=active_tools, model=name)
                if not turn.tool_calls:
                    text = turn.content
                    break
                batch_calls = turn.tool_calls[:MAX_STEPS]
                messages.append(
                    {
                        "role": "assistant",
                        "content": turn.content or "",
                        "tool_calls": [
                            {
                                "id": tc.id,
                                "type": "function",
                                "function": {
                                    "name": tc.name,
                                    "arguments": json.dumps(tc.arguments),
                                },
                            }
                            for tc in batch_calls
                        ],
                    }
                )
                tool_results = self.run_tools([ToolCall(tc.name, tc.arguments) for tc in batch_calls])
                halt_loop = False
                for tc, res in zip(batch_calls, tool_results):
                    steps_taken.append(
                        {
                            "step": step_index + 1,
                            "name": res.name,
                            "status": res.status,
                            "output": res.output,
                        }
                    )
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "name": tc.name,
                            "content": res.output,
                        }
                    )
                    if res.status == "ask_person":
                        halt_loop = True
                if halt_loop:
                    break
            if not text:
                final_turn = chat_fn(messages, tools=None, model=name)
                text = final_turn.content

        self.log.info(
            "agent.run model=%s steps=%s skills=%s env=%s",
            name,
            len(steps_taken),
            len(skills),
            self.settings.hermes_env,
        )
        result: dict[str, object] = {"text": text, "model": name, "steps": steps_taken}
        if sources:
            result["sources"] = sources
        return result

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

    def _retrieve_context(self, prompt: str, skills: list[Skill]) -> tuple[str | None, list[str]]:
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
        block, used = _fitted_context(prompt, skills, passages)
        labels = [passage_label(passage) for passage in used]
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


def _fitted_context(
    prompt: str,
    skills: list[Skill],
    passages: list[dict[str, object]],
) -> tuple[str | None, list[dict[str, object]]]:
    """Keep the best passages that fit the prompt cap. Lower-ranked passages are dropped first."""
    for count in range(len(passages), 0, -1):
        kept = passages[:count]
        block = context_block(kept)
        if block is None:
            continue
        if len(assemble_completion_prompt(prompt, skills, block)) <= MAX_PROMPT_CHARS:
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


def _health_payload(
    settings: Settings,
    reachable: bool,
    *,
    profile_loaded: bool = False,
    workspace_enabled: bool = False,
    workspace_mode: str = "off",
    project_count: int = 0,
) -> dict[str, object]:
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
        "provider": {
            "auth_mode": settings.provider_auth_mode,
            "gemini_subscription": "pending_official_oauth",
        },
        "assistant": {
            "timezone": settings.timezone,
            "profile_loaded": profile_loaded,
        },
        "workspace": {
            "enabled": workspace_enabled,
            "mode": workspace_mode,
            "project_count": project_count,
        },
        "mcp": {
            "enabled": settings.mcp_enabled,
        },
        "retrieval": {
            "rag_mode": settings.rag_mode,
            "embedder": settings.embed_model or HASH_NAME,
            "documents_collection": settings.documents_collection,
            "memory_index": settings.memory_index,
            "memory_collection": settings.memory_collection,
        },
    }
