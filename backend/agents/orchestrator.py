import asyncio
import os
import uuid
from pathlib import Path
from typing import Any

from backend.agents.ielts_graph import (
    IELTSGraphDependencies,
    build_combined_graph,
    build_evaluation_graph,
    build_grammar_graph,
)
from backend.observability.telemetry import workflow_span


DEFAULT_CHECKPOINT_PATH = (
    Path(__file__).resolve().parents[1] / "data" / "langgraph_checkpoints.sqlite"
)


class IELTSWritingOrchestrator:
    """Run IELTS Writing Task 2 workflows through checkpointed LangGraph graphs."""

    def __init__(
        self,
        checkpointer: Any = None,
        dependencies: IELTSGraphDependencies | None = None,
        checkpoint_path: str | Path | None = None,
    ):
        self._checkpointer = checkpointer
        self._dependencies = dependencies or IELTSGraphDependencies()
        self._checkpoint_path = Path(
            checkpoint_path
            or os.getenv("LANGGRAPH_CHECKPOINT_DB", DEFAULT_CHECKPOINT_PATH)
        )
        self._checkpoint_context = None
        self._owns_checkpointer = checkpointer is None
        self._start_lock = asyncio.Lock()
        self._started = False
        self.evaluation_graph = None
        self.grammar_graph = None
        self.combined_graph = None

    async def start(self) -> None:
        if self._started:
            return

        async with self._start_lock:
            if self._started:
                return

            if self._checkpointer is None:
                os.environ.setdefault("LANGGRAPH_STRICT_MSGPACK", "true")
                from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

                self._checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
                self._checkpoint_context = AsyncSqliteSaver.from_conn_string(
                    str(self._checkpoint_path)
                )
                self._checkpointer = await self._checkpoint_context.__aenter__()

            try:
                self.evaluation_graph = build_evaluation_graph(
                    self._checkpointer,
                    self._dependencies,
                )
                self.grammar_graph = build_grammar_graph(
                    self._checkpointer,
                    self._dependencies,
                )
                self.combined_graph = build_combined_graph(
                    self._checkpointer,
                    self._dependencies,
                )
                self._started = True
            except Exception:
                if self._owns_checkpointer and self._checkpoint_context is not None:
                    await self._checkpoint_context.__aexit__(None, None, None)
                    self._checkpoint_context = None
                    self._checkpointer = None
                raise

    async def close(self) -> None:
        if self._owns_checkpointer and self._checkpoint_context is not None:
            await self._checkpoint_context.__aexit__(None, None, None)
            self._checkpoint_context = None
            self._checkpointer = None
            self._started = False

    async def evaluate_essay(
        self,
        question: str,
        answer: str,
        session_id: str | None = None,
    ) -> dict:
        with workflow_span(
            "evaluate",
            self._session_source(session_id),
            self._checkpoint_backend(),
        ):
            await self.start()
            thread_id = session_id or str(uuid.uuid4())
            state = await self.evaluation_graph.ainvoke(
                {
                    "question": question,
                    "answer": answer,
                    "session_id": thread_id,
                },
                config=self._graph_config(thread_id),
            )
            return state["report"]

    async def correct_grammar(
        self,
        answer: str,
        session_id: str | None = None,
    ) -> dict:
        with workflow_span(
            "grammar",
            self._session_source(session_id),
            self._checkpoint_backend(),
        ):
            await self.start()
            thread_id = session_id or str(uuid.uuid4())
            state = await self.grammar_graph.ainvoke(
                {
                    "answer": answer,
                    "session_id": thread_id,
                },
                config=self._graph_config(thread_id),
            )
            return state["report"]

    async def process_essay(
        self,
        question: str,
        answer: str,
        session_id: str | None = None,
    ) -> dict:
        with workflow_span(
            "combined",
            self._session_source(session_id),
            self._checkpoint_backend(),
        ):
            await self.start()
            thread_id = session_id or str(uuid.uuid4())
            state = await self.combined_graph.ainvoke(
                {
                    "question": question,
                    "answer": answer,
                    "session_id": thread_id,
                },
                config=self._graph_config(thread_id),
            )
            return state["report"]

    def _checkpoint_backend(self) -> str:
        return "sqlite" if self._owns_checkpointer else "injected"

    @staticmethod
    def _session_source(session_id: str | None) -> str:
        return "provided" if session_id else "generated"

    @staticmethod
    def _graph_config(thread_id: str) -> dict:
        return {"configurable": {"thread_id": thread_id}}
