"""
Data ingestion module for loading, chunking, embedding, and storing store data
"""

import json
import os
from pathlib import Path
from typing import List, Dict
from dotenv import load_dotenv
import openai

from app.services.vector_store import get_vector_store, VectorDocument

# Load environment variables
load_dotenv()
openai.api_key = os.getenv('OPENAI_API_KEY')

_DATA_DIR = Path(__file__).parent.parent.parent / 'data'


def load_products(file_path) -> List[str]:
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            products = json.load(f)

        product_chunks = []
        for product in products:
            chunk = (
                f"Product: {product['name']}\n"
                f"Category: {product['category']}\n"
                f"House: {product['house']}\n"
                f"Price: ${product['price']}\n"
                f"Description: {product['description']}\n"
                f"Tags: {', '.join(product['tags'])}\n"
                f"Stock: {product['stock_status']}\n"
                f"ID: {product['id']}"
            )
            product_chunks.append(chunk)

        print(f"✓ Loaded {len(product_chunks)} product chunks from {file_path}")
        return product_chunks

    except FileNotFoundError:
        print(f"✗ Error: File not found - {file_path}")
        return []
    except json.JSONDecodeError as e:
        print(f"✗ Error: Invalid JSON in {file_path} - {e}")
        return []
    except Exception as e:
        print(f"✗ Error loading products: {e}")
        return []


def load_policies(file_path) -> List[str]:
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        sections = content.split('\n\n')
        policy_chunks = [s.strip() for s in sections if s.strip()]

        print(f"✓ Loaded {len(policy_chunks)} policy chunks from {file_path}")
        return policy_chunks

    except FileNotFoundError:
        print(f"✗ Error: File not found - {file_path}")
        return []
    except Exception as e:
        print(f"✗ Error loading policies: {e}")
        return []


def load_faq(file_path) -> List[str]:
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        sections = content.split('\n\n')
        faq_chunks = [s.strip() for s in sections if s.strip()]

        print(f"✓ Loaded {len(faq_chunks)} FAQ chunks from {file_path}")
        return faq_chunks

    except FileNotFoundError:
        print(f"✗ Error: File not found - {file_path}")
        return []
    except Exception as e:
        print(f"✗ Error loading FAQ: {e}")
        return []


def ingest_all_data(data_dir=None) -> List[Dict[str, str]]:
    print("\n" + "="*80)
    print("STARTING DATA INGESTION")
    print("="*80 + "\n")

    data_path = Path(data_dir) if data_dir else _DATA_DIR

    products = load_products(data_path / 'products.json')
    policies = load_policies(data_path / 'policies.txt')
    faqs = load_faq(data_path / 'faq.txt')

    documents = []

    for i, text in enumerate(products):
        documents.append({'text': text, 'source': 'product', 'id': f'product_{i}'})

    for i, text in enumerate(policies):
        documents.append({'text': text, 'source': 'policy', 'id': f'policy_{i}'})

    for i, text in enumerate(faqs):
        documents.append({'text': text, 'source': 'faq', 'id': f'faq_{i}'})

    print("\n" + "="*80)
    print("DATA INGESTION SUMMARY")
    print("="*80)
    print(f"Total documents: {len(documents)}")
    print(f"  - Products: {len(products)}")
    print(f"  - Policies: {len(policies)}")
    print(f"  - FAQs: {len(faqs)}")
    print("="*80 + "\n")

    return documents


def create_embeddings(documents: List[Dict[str, str]]) -> List[Dict]:
    print("Creating embeddings with OpenAI...")

    try:
        for i, doc in enumerate(documents):
            response = openai.embeddings.create(
                model="text-embedding-3-small",
                input=doc['text']
            )
            doc['embedding'] = response.data[0].embedding

            if (i + 1) % 10 == 0:
                print(f"  Processed {i + 1}/{len(documents)} documents")

        print(f"✓ Created {len(documents)} embeddings")
        return documents

    except Exception as e:
        print(f"✗ Error creating embeddings: {e}")
        return []


def store_in_vector_store(documents: List[Dict], collection_name='wizard_store'):
    """Store documents in the configured vector store backend (ChromaDB or Qdrant)."""
    store = get_vector_store()
    print(f"\nStoring documents in collection '{collection_name}' via {type(store).__name__}...")

    try:
        store.reset_collection(collection_name)
        print(f"  Reset collection '{collection_name}'")

        vector_docs = [
            VectorDocument(
                id=doc['id'],
                text=doc['text'],
                embedding=doc['embedding'],
                metadata={'source': doc['source']},
            )
            for doc in documents
        ]

        store.upsert(collection_name, vector_docs)
        count = store.count(collection_name)
        print(f"✓ Stored {count} documents in '{collection_name}'\n")

    except Exception as e:
        print(f"✗ Error storing documents: {e}")


def build_knowledge_base():
    print("\n🧙‍♂️ WIZARD STORE - BUILDING KNOWLEDGE BASE\n")

    documents = ingest_all_data()

    if not documents:
        print("✗ No documents loaded. Aborting.")
        return

    documents = create_embeddings(documents)

    if not documents:
        print("✗ Failed to create embeddings. Aborting.")
        return

    store_in_vector_store(documents)

    print("✅ Knowledge base built successfully!\n")


if __name__ == "__main__":
    build_knowledge_base()
