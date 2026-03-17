"""
RAG (Retrieval Augmented Generation) module for query processing

Architecture Features:
- Query Intent Classification: Routes queries to appropriate handlers
- Soft Grounding: Uses similarity threshold (1.1) to refuse irrelevant queries
- Score Dominance: Prevents false ambiguity when one result is clearly better
- Hallucination Prevention: Strict grounding to context only
"""

import asyncio
import os
import logging
from typing import List, Dict
from dotenv import load_dotenv
import openai

from app.services.vector_store import get_vector_store

load_dotenv()

logger = logging.getLogger("wizard_store.rag")

_OPENAI_TIMEOUT = 15  # seconds

# Initialise OpenAI client once at module level
_client = openai.OpenAI(
    api_key=os.getenv('OPENAI_API_KEY'),
    timeout=_OPENAI_TIMEOUT,
)


class WizardStoreRAG:
    """
    RAG system for the Wizard Store chatbot
    """

    def __init__(self, collection_name='wizard_store', db_path=None):
        """
        Initialize RAG system with the configured vector store backend.

        Args:
            collection_name (str): Name of the vector store collection
            db_path (str): Path to ChromaDB database (only used when VECTOR_STORE=chroma)
        """
        self.collection_name = collection_name
        self._store = get_vector_store(db_path)
        logger.info("RAG initialized with collection '%s'", collection_name)

    def embed_query(self, query: str) -> List[float]:
        """
        Create embedding for user query

        Args:
            query (str): User's question

        Returns:
            List[float]: Query embedding vector
        """
        try:
            response = _client.embeddings.create(
                model="text-embedding-3-small",
                input=query
            )
            return response.data[0].embedding
        except Exception as e:
            logger.error("Error embedding query: %s", e)
            return []

    def retrieve_context(self, query: str, top_k: int = 5) -> List[Dict]:
        """
        Retrieve most relevant documents from the vector store

        Args:
            query (str): User's question
            top_k (int): Number of documents to retrieve

        Returns:
            List[Dict]: Retrieved documents with metadata
        """
        try:
            query_embedding = self.embed_query(query)

            if not query_embedding:
                return []

            results = self._store.search(
                collection=self.collection_name,
                query_vector=query_embedding,
                top_k=top_k,
            )

            return [
                {
                    'id': r.id,
                    'text': r.text,
                    'metadata': r.metadata,
                    'distance': r.distance,
                }
                for r in results
            ]

        except Exception as e:
            logger.error("Error retrieving context: %s", e)
            return []

    def _classify_query_intent(self, query: str) -> str:
        """
        Classify query intent using LLM for better accuracy

        Args:
            query (str): User's question

        Returns:
            str: Intent type - 'catalog', 'specific_product', 'faq', 'policy', or 'general'
        """
        try:
            prompt = f"""Classify the user query into one of these categories:
- catalog (asking what products exist, browsing, listing items)
- specific_product (asking about a specific item, price, availability, or details)
- faq (general how-to, informational question, store operations)
- policy (returns, shipping, refund, warranty, payment)
- general (other questions not fitting above categories)

Only return the category name.

Query: "{query}"
"""

            response = _client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                temperature=0
            )

            intent = response.choices[0].message.content.strip().lower()

            valid_intents = ['catalog', 'specific_product', 'faq', 'policy', 'general']
            if intent not in valid_intents:
                return 'general'

            return intent

        except Exception as e:
            logger.warning("Error classifying intent: %s", e)
            return 'general'

    def _apply_soft_grounding(self, context_docs: List[Dict], query: str = "", threshold: float = 1.1, intent: str = 'general') -> tuple:
        """
        Apply soft grounding - check if retrieved results are relevant enough
        """
        if not context_docs:
            return False, []

        intent_thresholds = {
            'catalog': 1.25,
            'general': 1.15,
            'specific_product': 1.0,
            'faq': 1.15,
            'policy': 1.15
        }

        adjusted_threshold = intent_thresholds.get(intent, threshold)
        top_distance = context_docs[0]['distance']

        logger.debug("Soft grounding | intent=%s top_dist=%.4f threshold=%.4f", intent, top_distance, adjusted_threshold)

        if top_distance > adjusted_threshold:
            logger.debug("No relevant match found (dist %.4f > threshold %.4f)", top_distance, adjusted_threshold)
            return False, []

        if intent == 'specific_product' and query:
            query_lower = query.lower()
            top_text = " ".join([doc['text'] for doc in context_docs[:3]]).lower()
            product_types = ['broomstick', 'broom', 'owl', 'pet', 'snitch', 'quaffle']
            mentioned_absent = [ptype for ptype in product_types if ptype in query_lower and ptype not in top_text]

            if mentioned_absent:
                logger.debug("Semantic mismatch: query mentions %s but docs don't", mentioned_absent)
                return False, []

        filtered = [doc for doc in context_docs if doc['distance'] <= adjusted_threshold + 0.15]
        logger.debug("Found %d relevant documents within threshold", len(filtered))

        return True, filtered

    def _check_ambiguous_query(self, query: str, context_docs: List[Dict]) -> bool:
        """
        Check if query is ambiguous and multiple products retrieved
        """
        ambiguous_patterns = [
            'the wand', 'the product', 'the item', 'the potion',
            'the book', 'the spellbook', 'it', 'this product', 'that one',
            'this item', 'that item', 'this one'
        ]

        query_lower = query.lower()
        has_generic_pattern = any(pattern in query_lower for pattern in ambiguous_patterns)

        if not has_generic_pattern:
            return False

        product_docs = [doc for doc in context_docs if doc['metadata']['source'] == 'product']

        if len(product_docs) < 2:
            return False

        top_distance = product_docs[0]['distance']
        second_distance = product_docs[1]['distance']
        distance_difference = abs(second_distance - top_distance)

        logger.debug("Ambiguity check | top=%.4f second=%.4f diff=%.4f", top_distance, second_distance, distance_difference)

        if distance_difference < 0.05:
            logger.debug("Ambiguous query detected: '%s' | products=%d", query, len(product_docs))
            return True
        else:
            logger.debug("Clear winner - not ambiguous despite multiple products")
            return False

    async def _log_cost(self, endpoint: str, prompt_tokens: int, completion_tokens: int) -> None:
        """Write a token cost row to cost_log. Fire-and-forget — never blocks the response."""
        try:
            from app.database.connection import AsyncSessionLocal
            from app.database.models import CostLog
            if AsyncSessionLocal is None:
                return
            async with AsyncSessionLocal() as session:
                session.add(CostLog(
                    endpoint=endpoint,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=prompt_tokens + completion_tokens,
                ))
                await session.commit()
        except Exception as e:
            logger.debug("Cost log write failed (non-critical): %s", e)

    def _generate_response_with_usage(self, query: str, context_docs: List[Dict]) -> tuple[str, int, int]:
        """
        Generate response using GPT with retrieved context.
        Returns (answer_text, prompt_tokens, completion_tokens).
        """
        try:
            if self._check_ambiguous_query(query, context_docs):
                product_docs = [doc for doc in context_docs if doc['metadata']['source'] == 'product']
                product_names = []

                for doc in product_docs[:5]:
                    lines = doc['text'].split('\n')
                    for line in lines:
                        if line.strip().startswith('Product:'):
                            name = line.replace('Product:', '').strip()
                            product_names.append(name)
                            break

                if product_names:
                    clarification = "🔍 I found multiple products matching your query:\n\n"
                    for i, name in enumerate(product_names, 1):
                        clarification += f"   {i}. {name}\n"
                    clarification += "\nCould you please specify which one you're asking about?"
                    return clarification, 0, 0

            context = "\n\n---\n\n".join([doc['text'] for doc in context_docs])

            system_prompt = """You are a helpful assistant for "The Enchanted Emporium" wizard store.

CRITICAL RULES - YOU MUST FOLLOW THESE EXACTLY:
1. ONLY answer using information explicitly stated in the provided context below.
2. If the information IS in the context, answer it directly and confidently.
3. If the answer is NOT clearly found in the context, respond with: "I don't have that specific information in our current database. Please contact our store directly for more details."
4. Do NOT make up information, add details, or use external knowledge.
5. Do NOT use your training data about Harry Potter, wizards, or any other knowledge.
6. If asked about product details not in the context (like dimensions, weight, length), say you don't have that information.
7. Keep responses friendly, helpful, and conversational - but factually accurate to the context only.

When information IS available in the context (like prices, descriptions, policies), answer it clearly and naturally.
You are grounded ONLY to the context provided - nothing else."""

            user_prompt = f"""Context information from our store database:

{context}

---

Customer question: {query}

Answer based ONLY on the context above. If the context doesn't contain the answer, clearly state you don't have that information."""

            response = _client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.2,
                max_tokens=500
            )

            usage = response.usage
            return (
                response.choices[0].message.content,
                usage.prompt_tokens if usage else 0,
                usage.completion_tokens if usage else 0,
            )

        except Exception as e:
            logger.error("Error generating response: %s", e)
            return "I apologize, but I'm having trouble generating a response right now. Please try again.", 0, 0

    def generate_response(self, query: str, context_docs: List[Dict]) -> str:
        """Convenience wrapper that discards token usage info."""
        text, _, _ = self._generate_response_with_usage(query, context_docs)
        return text

    def answer_question(self, query: str, top_k: int = 5, verbose: bool = False, return_context: bool = False):
        """
        Complete RAG pipeline with intent classification and soft grounding.
        Fires a non-blocking cost_log write after generating the response.
        """
        intent = self._classify_query_intent(query)

        context_docs = self.retrieve_context(query, top_k=top_k)

        if not context_docs:
            answer = "I couldn't find relevant information to answer your question."
            if return_context:
                return {"answer": answer, "context": [], "intent": intent}
            return answer

        is_relevant, filtered_docs = self._apply_soft_grounding(context_docs, query=query, threshold=1.1, intent=intent)

        if not is_relevant:
            answer = ("I don't have information about that in our store database. "
                   "We specialize in magical items like wands, potions, spellbooks, and robes. "
                   "Is there something specific about our products I can help you with?")
            if return_context:
                return {"answer": answer, "context": [], "intent": intent}
            return answer

        context_docs = filtered_docs
        response, prompt_tokens, completion_tokens = self._generate_response_with_usage(query, context_docs)

        # Fire-and-forget cost log (non-blocking)
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(self._log_cost("chat", prompt_tokens, completion_tokens))
        except Exception:
            pass

        if return_context:
            return {
                "answer": response,
                "context": [
                    {
                        "content": doc['text'],
                        "metadata": doc['metadata'],
                        "distance": doc['distance']
                    }
                    for doc in context_docs
                ],
                "intent": intent
            }

        return response
