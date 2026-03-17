"""
Chat API router for Wizard Store AI
"""

import logging
from fastapi import APIRouter, HTTPException, Request, Depends
from pydantic import BaseModel, Field, field_validator
from typing import List, Optional, Dict, Any
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.services.rag import WizardStoreRAG

logger = logging.getLogger("wizard_store.chat")
limiter = Limiter(key_func=get_remote_address)

router = APIRouter()

# ── Thread-safe singleton via module-level lock ───────────────────────────────
_rag_system: Optional[WizardStoreRAG] = None

def get_rag_system() -> WizardStoreRAG:
    global _rag_system
    if _rag_system is None:
        logger.info("Initializing RAG system...")
        _rag_system = WizardStoreRAG()
        logger.info("RAG system initialized.")
    return _rag_system


# ── Request / Response models ─────────────────────────────────────────────────
class ChatRequest(BaseModel):
    query: str = Field(..., description="User's question or query")
    top_k: int = Field(5, ge=1, le=20, description="Number of context documents to retrieve")

    @field_validator("query")
    @classmethod
    def validate_query(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Query cannot be empty.")
        if len(v) > 1000:
            raise ValueError("Query must be 1000 characters or fewer.")
        return v


class ChatResponse(BaseModel):
    answer: str
    context: Optional[List[Dict[str, Any]]] = None
    intent: Optional[str] = None
    error: Optional[str] = None


# ── Endpoints ─────────────────────────────────────────────────────────────────
@router.post("/chat", response_model=ChatResponse, tags=["Chat"])
@limiter.limit("20/minute")
async def chat(request: Request, body: ChatRequest, rag: WizardStoreRAG = Depends(get_rag_system)):
    logger.info("Chat request | query_len=%d top_k=%d", len(body.query), body.top_k)
    try:
        result = rag.answer_question(
            query=body.query,
            top_k=body.top_k,
            return_context=True,
        )

        context = None
        if result.get("context"):
            context = [
                {
                    "content": doc.get("content", ""),
                    "metadata": doc.get("metadata", {}),
                    "score": doc.get("distance", 0),
                }
                for doc in result["context"]
            ]

        logger.info("Chat response | intent=%s context_docs=%d", result.get("intent"), len(context or []))
        return ChatResponse(
            answer=result.get("answer", "I apologize, but I could not generate a response."),
            context=context,
            intent=result.get("intent"),
            error=result.get("error"),
        )

    except Exception as e:
        logger.exception("Error in /chat: %s", e)
        raise HTTPException(status_code=500, detail="An error occurred while processing your request.")


@router.post("/recommend", tags=["Recommendations"])
@limiter.limit("20/minute")
async def get_recommendations(request: Request, body: Dict[str, str], rag: WizardStoreRAG = Depends(get_rag_system)):
    query = (body.get("query") or "").strip()[:500]
    if not query:
        raise HTTPException(status_code=422, detail="query field is required.")

    logger.info("Recommend request | query_len=%d", len(query))
    try:
        result = rag.answer_question(
            query=f"Show me products related to: {query}",
            top_k=8,
            return_context=True,
        )

        products = []
        for doc in result.get("context", []):
            if doc.get("metadata", {}).get("source") != "product":
                continue
            parsed = _parse_product_from_text(
                doc.get("content", ""),
                relevance=round(1 - doc.get("distance", 0), 4),
            )
            if parsed:
                products.append(parsed)

        logger.info("Recommend response | products=%d", len(products))
        return {"products": products}

    except Exception as e:
        logger.exception("Error in /recommend: %s", e)
        raise HTTPException(status_code=500, detail="An error occurred while fetching recommendations.")


# ── Helpers ───────────────────────────────────────────────────────────────────
def _parse_product_from_text(text: str, relevance: float) -> Optional[Dict[str, Any]]:
    """Parse structured product fields from RAG document text."""
    lines = text.strip().split("\n")
    product: Dict[str, Any] = {"relevance": relevance}
    for line in lines:
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip().lower()
        value = value.strip()
        if key == "product":
            product["name"] = value
        elif key == "category":
            product["category"] = value
        elif key == "house":
            product["house"] = value
        elif key == "price":
            try:
                product["price"] = float(value.replace("$", "").strip())
            except ValueError:
                product["price"] = 0.0
        elif key == "description":
            product["description"] = value
        elif key == "tags":
            product["tags"] = [t.strip() for t in value.split(",")]
        elif key == "stock":
            product["stock_status"] = value
        elif key == "id":
            product["id"] = value

    if "name" not in product:
        return None

    product.setdefault("category", "General")
    product.setdefault("house", "All")
    product.setdefault("price", 0.0)
    product.setdefault("description", "")
    product.setdefault("tags", [])
    product.setdefault("stock_status", "In Stock")
    product.setdefault("id", product["name"].lower().replace(" ", "_"))
    return product
