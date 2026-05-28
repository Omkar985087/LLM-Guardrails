"""
LLM Guardrails Gateway — FastAPI Application

This is the main entry point.  It exposes:
  POST /chat    — send a prompt through the guardrails pipeline
  GET  /policy  — view the current active policy (JSON)
  GET  /health  — health check
  GET  /        — web dashboard UI
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from guardrails.input_guards import run_input_guards
from guardrails.llm_client import generate
from guardrails.models import ChatRequest, ChatResponse, GuardrailResult, GuardrailStatus
from guardrails.output_guards import run_output_guards
from guardrails.policy import get_policy, load_policy, reload_policy

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("guardrails")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

# ---------------------------------------------------------------------------
# Lifespan (startup / shutdown)
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load the policy on startup."""
    policy = load_policy()
    logger.info("✅ Policy loaded — model=%s", policy.llm.model)
    logger.info(
        "   Input guards: PII=%s  Injection=%s  MaxLen=%d",
        policy.input_guardrails.pii_detection.enabled,
        policy.input_guardrails.prompt_injection.enabled,
        policy.input_guardrails.max_input_length,
    )
    logger.info(
        "   Output guards: Toxicity=%s  Topic=%s  Schema=%s  MaxLen=%d",
        policy.output_guardrails.toxicity_check.enabled,
        policy.output_guardrails.topic_adherence.enabled,
        policy.output_guardrails.schema_validation.enabled,
        policy.output_guardrails.max_output_length,
    )
    yield
    logger.info("🛑 Shutting down Guardrails Gateway")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="🛡️ LLM Guardrails Gateway",
    description="Middleware layer enforcing safety, compliance, and output structure rules for LLMs.",
    version="1.0.0",
    lifespan=lifespan,
)

# Mount static files
STATIC_DIR.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Templates
TEMPLATES_DIR.mkdir(exist_ok=True)
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Serve the web dashboard."""
    return templates.TemplateResponse(request, "index.html")


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy", "service": "llm-guardrails-gateway"}


@app.get("/policy")
async def view_policy():
    """Return the current active policy as JSON."""
    policy = get_policy()
    return policy.model_dump()


@app.post("/reload-policy")
async def reload_policy_endpoint():
    """Reload the policy from disk."""
    try:
        policy = reload_policy()
        return {"status": "reloaded", "model": policy.llm.model}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """
    Main guardrails pipeline:
    1. Run input guardrails
    2. If passed → call LLM
    3. Run output guardrails on LLM response
    4. Retry if output guardrails fail (up to max_retries)
    5. Return validated response
    """
    policy = get_policy()
    prompt = req.prompt.strip()

    # ── Step 1: Input Guardrails ──────────────────────────────────────────
    input_results = run_input_guards(prompt, policy)
    blocked_results = [r for r in input_results if not r.passed]

    if blocked_results:
        first_block = blocked_results[0]
        logger.warning("🚫 Input BLOCKED: %s", first_block.message)
        return ChatResponse(
            status=GuardrailStatus.BLOCKED,
            response=None,
            input_guardrails=input_results,
            output_guardrails=[],
            retries_used=0,
            message=first_block.message,
        )

    logger.info("✅ Input guardrails passed for prompt: %s...", prompt[:60])

    # ── Step 2 & 3: LLM Call + Output Guardrails (with retries) ───────────
    max_retries = policy.llm.max_retries if policy.llm.retry_on_output_violation else 0
    retries_used = 0
    llm_response = ""
    output_results: list[GuardrailResult] = []
    correction_hint: str | None = None

    for attempt in range(1 + max_retries):
        # Call the LLM
        try:
            llm_response = generate(prompt, policy, correction_hint=correction_hint)
        except Exception as exc:
            logger.error("❌ LLM call failed: %s", exc)
            return ChatResponse(
                status=GuardrailStatus.BLOCKED,
                response=None,
                input_guardrails=input_results,
                output_guardrails=[],
                retries_used=retries_used,
                message=f"LLM call failed: {exc}",
            )

        # Run output guardrails
        output_results = run_output_guards(
            llm_response, policy, override_schema=req.output_schema
        )
        output_failures = [r for r in output_results if not r.passed]

        if not output_failures:
            # All checks passed!
            break

        # Output guardrails failed — prepare for retry
        retries_used += 1
        failure_messages = "; ".join(r.message or r.check_name for r in output_failures)
        correction_hint = failure_messages
        logger.warning(
            "⚠️ Output guardrail failed (attempt %d/%d): %s",
            attempt + 1, 1 + max_retries, failure_messages,
        )

    # ── Step 4: Build final response ──────────────────────────────────────
    final_failures = [r for r in output_results if not r.passed]

    if final_failures:
        first_fail = final_failures[0]
        logger.warning("🚫 Output BLOCKED after %d retries: %s", retries_used, first_fail.message)
        return ChatResponse(
            status=GuardrailStatus.FILTERED,
            response=None,
            input_guardrails=input_results,
            output_guardrails=output_results,
            retries_used=retries_used,
            message=first_fail.message,
        )

    logger.info("✅ Response validated — returning to user")
    return ChatResponse(
        status=GuardrailStatus.PASSED,
        response=llm_response,
        input_guardrails=input_results,
        output_guardrails=output_results,
        retries_used=retries_used,
        message="Response passed all guardrails.",
    )


# ---------------------------------------------------------------------------
# Run with: uvicorn main:app --reload
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
