"""Synthesize proposed solutions from research + a recommended agent action.

After research collects sources, Buster proposes concrete solutions and a
recommended next action (an agent run) the user can launch with one click.
Per the agreed design: PROPOSE, one-click to run — never launch automatically.
When Buster asks, it offers "where" (runtime + model tier) and "when"
(now / scheduled / queued).

Solutions are model-generated when a model is available, else a deterministic
fallback derived from the sources — so this works with no LLM.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from buster.config import load_config


class ProposedSolution(BaseModel):
    title: str
    detail: str = ""
    effort: str = "unknown"          # low | medium | high | unknown


class RecommendedAction(BaseModel):
    """A one-click-launchable agent task. Nothing runs without the user's go."""

    summary: str
    prompt: str                       # the task to hand the agent
    # "where" options (populated from detected runtimes/model tiers)
    runtime_options: list[str] = Field(default_factory=list)
    model_options: list[str] = Field(default_factory=list)
    # "when" options
    when_options: list[str] = Field(default_factory=lambda: ["now", "schedule", "queue"])
    recommended_runtime: str = ""


class SolutionSet(BaseModel):
    question: str
    solutions: list[ProposedSolution] = Field(default_factory=list)
    action: RecommendedAction | None = None
    engine: str = "deterministic"     # model | deterministic


async def _model_solutions(question: str, findings_text: str) -> list[ProposedSolution]:
    """Ask the routed model for 1-3 solutions. Returns [] if no model / on error."""
    from buster.models.provider import ChatMessage, ChatRequest
    from buster.models.router import ModelRouter

    router = ModelRouter(load_config())
    decision = await router.route()
    if decision.model == "none":
        return []
    prompt = (
        f"Research question: {question}\n\n"
        f"Key findings from sources:\n{findings_text[:3000]}\n\n"
        "Propose 1-3 concrete, actionable solutions. For each, give a short title "
        "and one or two sentences. Be practical. Format each as:\n"
        "TITLE: <title>\nDETAIL: <detail>\n---"
    )
    try:
        resp = await decision.provider.chat(ChatRequest(
            model=decision.model,
            messages=[ChatMessage(role="system",
                                  content="You propose practical solutions. Be concise."),
                      ChatMessage(role="user", content=prompt)],
            max_tokens=400, temperature=0.4,
        ))
    except Exception:  # noqa: BLE001
        return []
    return _parse_solutions(resp.content)


def _parse_solutions(text: str) -> list[ProposedSolution]:
    import re

    def _clean(s: str) -> str:
        return s.strip().strip("*").strip().strip(":").strip()

    out: list[ProposedSolution] = []
    for block in text.split("---"):
        title = detail = ""
        for line in block.splitlines():
            # Tolerate bold/markdown wrappers: **TITLE:**, - TITLE:, etc.
            m = re.match(r"\s*[-*#>\s]*\**\s*title\s*\**\s*:?\s*(.+)", line, re.IGNORECASE)
            if m and not title:
                title = _clean(m.group(1))
                continue
            m = re.match(r"\s*[-*#>\s]*\**\s*detail\s*\**\s*:?\s*(.+)", line, re.IGNORECASE)
            if m:
                detail = _clean(m.group(1))
        if title:
            out.append(ProposedSolution(title=title, detail=detail))
    # Fallback: if the model used numbered "1. Title — detail" lines instead.
    if not out:
        for line in text.splitlines():
            m = re.match(r"\s*\d+[.)]\s+(.+)", line)
            if m:
                parts = re.split(r"\s+[-–—:]\s+", _clean(m.group(1)), maxsplit=1)
                out.append(ProposedSolution(title=parts[0][:80],
                                            detail=parts[1] if len(parts) > 1 else ""))
    return out[:3]


def _deterministic_solutions(question: str, findings: list) -> list[ProposedSolution]:
    """No-LLM fallback: turn the strongest findings into candidate directions."""
    sols: list[ProposedSolution] = []
    for f in findings[:2]:
        stmt = getattr(f, "statement", str(f))
        sols.append(ProposedSolution(
            title=f"Act on: {stmt[:60]}",
            detail="Derived from a retrieved source; confirm before relying on it."))
    if not sols:
        sols.append(ProposedSolution(
            title=f"Investigate '{question}' further",
            detail="Not enough sources to propose a concrete solution yet."))
    return sols


async def build_recommended_action(
    question: str, solutions: list[ProposedSolution]
) -> RecommendedAction:
    """Assemble a one-click agent action with where/when options."""
    from buster.runtimes import detect_runtimes

    runtimes = await detect_runtimes()
    runtime_ids = [r.id for r in runtimes]
    # Prefer a codegen/dev runtime if present, else Buster-self.
    recommended = next((r.id for r in runtimes if r.runtime_type in ("cli", "buster")),
                       runtime_ids[0] if runtime_ids else "")

    model_options = []
    try:
        from buster.models.router import ModelRouter

        models = await ModelRouter(load_config()).available_models()
        model_options = [m.name for m in models][:5]
    except Exception:  # noqa: BLE001
        pass

    top = solutions[0].title if solutions else question
    return RecommendedAction(
        summary=f"Implement: {top}",
        prompt=(f"Based on research into '{question}', implement this solution: {top}. "
                + (solutions[0].detail if solutions else "")),
        runtime_options=runtime_ids,
        model_options=model_options,
        recommended_runtime=recommended,
    )


async def synthesize(question: str, findings: list) -> SolutionSet:
    findings_text = "\n".join(f"- {getattr(f, 'statement', str(f))}" for f in findings)
    solutions = await _model_solutions(question, findings_text)
    engine = "model"
    if not solutions:
        solutions = _deterministic_solutions(question, findings)
        engine = "deterministic"
    action = await build_recommended_action(question, solutions)
    return SolutionSet(question=question, solutions=solutions, action=action, engine=engine)
