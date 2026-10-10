"""HTTP API and the desk interface."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from meridian import __version__
from meridian.agent import run_desk
from meridian.calculate import DEMO_BOOK, TARGET_LABELS, scenario_on_book
from meridian.compose import SAMPLE_POLICY
from meridian.corpus import load_documents
from meridian.evaluate import load_saved, run_evaluation
from meridian.index import get_index
from meridian.questions import all_questions
from meridian.settings import CORPUS_DIR, WEB_DIR, embedding_mode, openai_api_key, openai_model

app = FastAPI(title="Meridian", version=__version__)

PRESETS = [
    {
        "id": "stress",
        "label": "LCR under stress",
        "question": "What are the key regulatory requirements affecting LCR under stress?",
    },
    {
        "id": "policy",
        "label": "Policy gap screen",
        "question": "Compare our internal liquidity policy against EBA/ECB requirements and identify potential gaps.",
    },
    {
        "id": "calc",
        "label": "Calculate an LCR",
        "question": "HQLA = €12bn, stressed outflow = €15bn, inflow = €5bn. What is the LCR?",
    },
    {
        "id": "shock",
        "label": "20% outflow shock",
        "question": "HQLA = €12bn, stressed outflow = €15bn, inflow = €5bn. What happens to the LCR if stressed outflows increase by 20%?",
    },
    {
        "id": "wholesale",
        "label": "Wholesale scenario",
        "question": "How would a 20% increase in wholesale deposit outflows affect the bank's liquidity position?",
    },
    {
        "id": "compare",
        "label": "ECB versus EBA",
        "question": "Compare ECB ILAAP expectations with EBA liquidity stress-testing guidance.",
    },
    {
        "id": "fake",
        "label": "Missing instrument",
        "question": "According to ECB Regulation XYZ-999, what minimum LCR may a bank hold?",
    },
]


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=2000)
    policy_text: str = ""
    scenario: dict | None = None


class ScenarioRequest(BaseModel):
    hqla: float = 12
    retail_stable: float = 20
    retail_stable_rate: float = 0.05
    retail_less_stable: float = 8
    retail_less_stable_rate: float = 0.10
    wholesale_operational: float = 6
    wholesale_operational_rate: float = 0.25
    wholesale_non_operational: float = 4
    wholesale_non_operational_rate: float = 1
    other_outflows: float = 1.5
    inflows: float = 5
    shock_target: str = "wholesale"
    shock_pct: float = 0.2


@app.get("/api/status")
def status() -> dict:
    index = get_index()
    documents = load_documents(CORPUS_DIR)
    try:
        import langgraph  # noqa: F401

        graph = "langgraph"
    except ImportError:
        graph = "python"
    return {
        "name": "Meridian",
        "version": __version__,
        "documents": len(documents),
        "chunks": len(index.chunks),
        "embedding": index.backend,
        "embedding_mode": embedding_mode(),
        "vector_store": index.vector_engine,
        "llm": bool(openai_api_key()),
        "llm_model": openai_model() if openai_api_key() else None,
        "verifier": True,
        "orchestrator": graph,
        "questions": len(all_questions()),
    }


@app.get("/api/presets")
def presets() -> dict:
    return {"presets": PRESETS, "sample_policy": SAMPLE_POLICY, "demo_book": DEMO_BOOK}


@app.get("/api/corpus")
def corpus() -> dict:
    documents = []
    for document in load_documents(CORPUS_DIR):
        documents.append(
            {
                "doc_id": document.doc_id,
                "title": document.title,
                "authority": document.authority,
                "topic": document.topic,
                "instruments": document.instruments,
                "sections": [
                    {"chunk_id": chunk.chunk_id, "heading": chunk.heading, "text": chunk.text}
                    for chunk in document.chunks
                ],
            }
        )
    return {"documents": documents}


@app.post("/api/ask")
def ask(body: AskRequest) -> dict:
    return run_desk(body.question, body.policy_text, body.scenario)


@app.post("/api/scenario")
def scenario(body: ScenarioRequest) -> dict:
    if body.shock_target not in TARGET_LABELS:
        raise HTTPException(status_code=400, detail="Unknown shock target.")
    book = body.model_dump(exclude={"shock_target", "shock_pct"})
    try:
        result = scenario_on_book(book, body.shock_target, body.shock_pct)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    components = []
    for base_row, shocked_row in zip(result["base"]["lines"], result["shocked"]["lines"]):
        components.append(
            {
                "label": base_row["label"],
                "rate": base_row["rate"],
                "base": round(base_row["outflow"], 4),
                "shocked": round(shocked_row["outflow"], 4),
            }
        )
    return {
        "target": body.shock_target,
        "target_label": TARGET_LABELS[body.shock_target],
        "shock_pct": body.shock_pct,
        "base": result["base"],
        "shocked": result["shocked"],
        "delta_lcr_pp": result["delta_lcr_pp"],
        "components": components,
    }


@app.get("/api/eval/questions")
def eval_questions() -> dict:
    return {"questions": all_questions()}


@app.get("/api/eval/latest")
def eval_latest() -> dict:
    saved = load_saved()
    if not saved:
        raise HTTPException(status_code=404, detail="No evaluation has been run yet.")
    return _public_eval(saved)


@app.post("/api/eval/run")
def eval_run() -> dict:
    report = run_evaluation(save=True)
    return _public_eval(report)


def _public_eval(report: dict) -> dict:
    return {
        "questions": report["questions"],
        "systems": report["systems"],
        "by_type": report["by_type"],
        "labels": report["labels"],
    }


web_dir = Path(WEB_DIR)
if web_dir.exists():
    app.mount("/assets", StaticFiles(directory=web_dir), name="assets")


@app.get("/styles.css")
def styles() -> FileResponse:
    return FileResponse(web_dir / "styles.css", media_type="text/css")


@app.get("/app.js")
def script() -> FileResponse:
    return FileResponse(web_dir / "app.js", media_type="text/javascript")


@app.get("/")
def index() -> FileResponse:
    page = web_dir / "index.html"
    if not page.exists():
        raise HTTPException(status_code=404, detail="Interface is not built.")
    return FileResponse(page)
