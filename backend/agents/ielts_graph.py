import asyncio
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict

from backend.observability.telemetry import node_span
from backend.tools.report_generator import (
    build_combined_report,
    build_evaluation_report,
    build_grammar_report,
)
from backend.tools.score_processor import (
    clean_feedback_for_response,
    extract_overall_criteria_scores,
)


class IELTSGraphState(TypedDict, total=False):
    question: str
    answer: str
    session_id: str
    overall_score: float
    raw_feedback: dict
    cleaned_feedback: dict
    overall_criteria_scores: dict
    grammar_result: dict
    report: dict


ScoreTool = Callable[[str, str], Awaitable[float]]
GrammarTool = Callable[[str], Awaitable[dict]]
FeedbackTool = Callable[[str, str, float], Awaitable[dict]]


async def run_bert_scoring(question: str, answer: str) -> float:
    from backend.tools.bert_scoring import score_essay

    return await asyncio.to_thread(score_essay, question, answer)


async def run_grammar_check(answer: str) -> dict:
    from backend.tools.grammar_checker import check_grammar

    return await check_grammar(answer)


async def run_gemini_feedback(question: str, answer: str, overall_score: float) -> dict:
    from backend.tools.feedback_generator import generate_feedback

    return await generate_feedback(question, answer, overall_score)


@dataclass(frozen=True)
class IELTSGraphDependencies:
    score_essay: ScoreTool = run_bert_scoring
    check_grammar: GrammarTool = run_grammar_check
    generate_feedback: FeedbackTool = run_gemini_feedback


def validate_input(state: IELTSGraphState) -> IELTSGraphState:
    with node_span("validate_input"):
        answer = state.get("answer", "")
        question = state.get("question")

        if not answer or not answer.strip():
            raise ValueError("Essay answer must not be empty.")
        if question is not None and not question.strip():
            raise ValueError("Essay question must not be empty.")

        return {
            "answer": answer.strip(),
            "question": question.strip() if question is not None else question,
        }


def prepare_session(state: IELTSGraphState) -> IELTSGraphState:
    with node_span("prepare_session"):
        return {"session_id": state.get("session_id") or str(uuid.uuid4())}


def _score_essay_node(dependencies: IELTSGraphDependencies):
    async def score_essay_node(state: IELTSGraphState) -> IELTSGraphState:
        with node_span("score_essay", "bert_scoring"):
            overall_score = await dependencies.score_essay(
                state["question"],
                state["answer"],
            )
            return {"overall_score": float(overall_score)}

    return score_essay_node


def _correct_grammar_node(dependencies: IELTSGraphDependencies):
    async def correct_grammar_node(state: IELTSGraphState) -> IELTSGraphState:
        with node_span("correct_grammar", "coedit_t5"):
            grammar_result = await dependencies.check_grammar(state["answer"])
            return {"grammar_result": grammar_result}

    return correct_grammar_node


def _generate_feedback_node(dependencies: IELTSGraphDependencies):
    async def generate_feedback_node(state: IELTSGraphState) -> IELTSGraphState:
        with node_span("generate_feedback", "gemini_feedback"):
            feedback = await dependencies.generate_feedback(
                state["question"],
                state["answer"],
                state["overall_score"],
            )
            return {"raw_feedback": feedback}

    return generate_feedback_node


def process_scores_node(state: IELTSGraphState) -> IELTSGraphState:
    with node_span("process_scores", "score_processor"):
        scores = extract_overall_criteria_scores(state["raw_feedback"])
        cleaned_feedback = clean_feedback_for_response(state["raw_feedback"])

        return {
            "overall_criteria_scores": scores,
            "cleaned_feedback": cleaned_feedback,
        }


def build_evaluation_report_node(state: IELTSGraphState) -> IELTSGraphState:
    with node_span("build_report", "report_generator"):
        report = build_evaluation_report(
            state["cleaned_feedback"],
            state["overall_criteria_scores"],
            state.get("session_id"),
        )
        return {"report": report}


def build_grammar_report_node(state: IELTSGraphState) -> IELTSGraphState:
    with node_span("build_report", "report_generator"):
        report = build_grammar_report(
            state["grammar_result"],
            state.get("session_id"),
        )
        return {"report": report}


def build_combined_report_node(state: IELTSGraphState) -> IELTSGraphState:
    with node_span("build_report", "report_generator"):
        report = build_combined_report(
            state["session_id"],
            state["cleaned_feedback"],
            state["overall_criteria_scores"],
            state["grammar_result"],
        )
        return {"report": report}


def build_evaluation_graph(
    checkpointer: Any = None,
    dependencies: IELTSGraphDependencies | None = None,
):
    dependencies = dependencies or IELTSGraphDependencies()
    graph = StateGraph(IELTSGraphState)
    graph.add_node("validate_input", validate_input)
    graph.add_node("score_essay", _score_essay_node(dependencies))
    graph.add_node("generate_feedback", _generate_feedback_node(dependencies))
    graph.add_node("process_scores", process_scores_node)
    graph.add_node("build_report", build_evaluation_report_node)

    graph.add_edge(START, "validate_input")
    graph.add_edge("validate_input", "score_essay")
    graph.add_edge("score_essay", "generate_feedback")
    graph.add_edge("generate_feedback", "process_scores")
    graph.add_edge("process_scores", "build_report")
    graph.add_edge("build_report", END)

    return graph.compile(checkpointer=checkpointer)


def build_grammar_graph(
    checkpointer: Any = None,
    dependencies: IELTSGraphDependencies | None = None,
):
    dependencies = dependencies or IELTSGraphDependencies()
    graph = StateGraph(IELTSGraphState)
    graph.add_node("validate_input", validate_input)
    graph.add_node("correct_grammar", _correct_grammar_node(dependencies))
    graph.add_node("build_report", build_grammar_report_node)

    graph.add_edge(START, "validate_input")
    graph.add_edge("validate_input", "correct_grammar")
    graph.add_edge("correct_grammar", "build_report")
    graph.add_edge("build_report", END)

    return graph.compile(checkpointer=checkpointer)


def build_combined_graph(
    checkpointer: Any = None,
    dependencies: IELTSGraphDependencies | None = None,
):
    dependencies = dependencies or IELTSGraphDependencies()
    graph = StateGraph(IELTSGraphState)
    graph.add_node("validate_input", validate_input)
    graph.add_node("prepare_session", prepare_session)
    graph.add_node("score_essay", _score_essay_node(dependencies))
    graph.add_node("correct_grammar", _correct_grammar_node(dependencies))
    graph.add_node("generate_feedback", _generate_feedback_node(dependencies))
    graph.add_node("process_scores", process_scores_node)
    graph.add_node("build_report", build_combined_report_node)

    graph.add_edge(START, "validate_input")
    graph.add_edge("validate_input", "prepare_session")
    graph.add_edge("prepare_session", "score_essay")
    graph.add_edge("prepare_session", "correct_grammar")
    graph.add_edge("score_essay", "generate_feedback")
    graph.add_edge("generate_feedback", "process_scores")
    graph.add_edge(["process_scores", "correct_grammar"], "build_report")
    graph.add_edge("build_report", END)

    return graph.compile(checkpointer=checkpointer)
