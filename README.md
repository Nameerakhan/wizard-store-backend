# Backend - Wizard Store AI

FastAPI backend with RAG (Retrieval Augmented Generation) for the Wizard Store AI chatbot.

## Features

- **RAG System**: ChromaDB vector database with semantic search
- **Intent Classification**: Smart query routing
- **OpenAI Integration**: GPT-4o-mini for chat, text-embedding-3-small for embeddings
- **RESTful API**: FastAPI with automatic API documentation

## Setup

### 1. Create Virtual Environment (Optional but Recommended)

```bash
python -m venv .venv
# On Windows
.venv\Scripts\activate
# On macOS/Linux
source .venv/bin/activate
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Environment Variables

Create a `.env` file in the root directory (or set environment variables):

```env
OPENAI_API_KEY=your_openai_api_key_here
```

### 4. Initialize Vector Database

Run this once to load data into ChromaDB:

```bash
python ingest.py
```

This will:
- Load products from `data/products.json`
- Load policies from `data/policies.txt`
- Load FAQs from `data/faq.txt`
- Create embeddings and store in `chroma_db/`

### 5. Start the Server

```bash
python main.py
```

The server will run on `http://localhost:8000`

## API Endpoints

- `POST /chat` - Send a chat message and get AI response
- `GET /health` - Health check endpoint
- `GET /docs` - Interactive API documentation (Swagger UI)

### Example Chat Request

```bash
curl -X POST "http://localhost:8000/chat" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Show me wands for beginners",
    "conversation_history": []
  }'
```

## Project Structure

```
backend/
├── main.py              # FastAPI server entry point
├── rag.py               # RAG system implementation
├── ingest.py            # Data loading and vector database creation
├── utils.py             # Chunking utilities
├── chat.py              # Chat logic
├── requirements.txt     # Python dependencies
├── data/                # Knowledge base
│   ├── products.json    # Product catalog
│   ├── policies.txt     # Store policies
│   └── faq.txt          # Frequently asked questions
├── tests/               # Test files
└── chroma_db/           # Vector database (auto-generated)
```

## Technologies

- **FastAPI**: Modern Python web framework
- **ChromaDB**: Vector database for semantic search
- **OpenAI**: GPT-4o-mini & text-embedding-3-small
- **tiktoken**: Token counting for text chunking
- **Pydantic**: Data validation
