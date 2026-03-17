"""
Utility functions for the Wizard Store AI application
"""

import tiktoken
from typing import List, Dict


def count_tokens(text: str, model: str = "gpt-3.5-turbo") -> int:
    try:
        encoding = tiktoken.encoding_for_model(model)
        return len(encoding.encode(text))
    except Exception as e:
        print(f"⚠ Warning: Could not use tiktoken, using approximate count: {e}")
        return len(text.split()) * 1.3


def chunk_text(text: str, chunk_size: int = 500, overlap: int = 100, model: str = "gpt-3.5-turbo") -> List[Dict]:
    try:
        encoding = tiktoken.encoding_for_model(model)
    except Exception as e:
        print(f"⚠ Warning: Could not load tiktoken encoding: {e}")
        print("Using character-based chunking as fallback...")
        return chunk_text_by_chars(text, chunk_size * 4, overlap * 4)

    tokens = encoding.encode(text)
    total_tokens = len(tokens)

    chunks = []
    start = 0
    chunk_id = 0

    while start < total_tokens:
        end = min(start + chunk_size, total_tokens)
        chunk_tokens = tokens[start:end]
        chunk_text_str = encoding.decode(chunk_tokens)

        chunks.append({
            'id': chunk_id,
            'text': chunk_text_str,
            'start_token': start,
            'end_token': end,
            'token_count': len(chunk_tokens),
            'char_count': len(chunk_text_str)
        })

        chunk_id += 1
        start += (chunk_size - overlap)

    return chunks


def chunk_text_by_chars(text: str, chunk_size: int = 2000, overlap: int = 400) -> List[Dict]:
    chunks = []
    start = 0
    chunk_id = 0
    text_length = len(text)

    while start < text_length:
        end = min(start + chunk_size, text_length)

        if end < text_length:
            for delimiter in ['. ', '.\n', '! ', '? ', '\n\n']:
                last_delim = text[start:end].rfind(delimiter)
                if last_delim > chunk_size * 0.7:
                    end = start + last_delim + len(delimiter)
                    break

        chunk_text_str = text[start:end]

        chunks.append({
            'id': chunk_id,
            'text': chunk_text_str,
            'start_char': start,
            'end_char': end,
            'token_count': len(chunk_text_str.split()),
            'char_count': len(chunk_text_str)
        })

        chunk_id += 1
        start += (chunk_size - overlap)

    return chunks


def display_chunk_stats(chunks: List[Dict], show_sample: bool = True, sample_id: int = 0):
    if not chunks:
        print("No chunks to display!")
        return

    print("\n" + "="*80)
    print("CHUNKING STATISTICS")
    print("="*80)
    print(f"Total chunks created: {len(chunks)}")

    total_tokens = sum(chunk['token_count'] for chunk in chunks)
    total_chars = sum(chunk['char_count'] for chunk in chunks)
    avg_tokens = total_tokens / len(chunks) if chunks else 0
    avg_chars = total_chars / len(chunks) if chunks else 0

    print(f"Total tokens (all chunks): {total_tokens:,}")
    print(f"Total characters (all chunks): {total_chars:,}")
    print(f"Average tokens per chunk: {avg_tokens:.1f}")
    print(f"Average characters per chunk: {avg_chars:.1f}")

    token_counts = [chunk['token_count'] for chunk in chunks]
    print(f"Smallest chunk: {min(token_counts)} tokens")
    print(f"Largest chunk: {max(token_counts)} tokens")
    print("="*80 + "\n")

    if show_sample and 0 <= sample_id < len(chunks):
        sample = chunks[sample_id]
        print("="*80)
        print(f"SAMPLE CHUNK (ID: {sample['id']})")
        print("="*80)
        print(f"Token count: {sample['token_count']}")
        print(f"Character count: {sample['char_count']}")
        print("-"*80)
        print("Content preview (first 500 chars):")
        print("-"*80)
        print(sample['text'][:500])
        if len(sample['text']) > 500:
            print("\n... [truncated] ...")
        print("="*80 + "\n")
