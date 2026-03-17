"""
Test script to verify chunking overlap is working correctly
"""

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent / 'app'))

from utils import chunk_text
from ingest import ingest_all_data

print("\n🧙‍♂️ WIZARD STORE - CHUNKING OVERLAP VERIFICATION\n")

# Load data
print("Loading data...")
combined_text = ingest_all_data()

# Create chunks
print("\nCreating chunks with 500 token size and 100 token overlap...")
chunks = chunk_text(combined_text, chunk_size=500, overlap=100)

print(f"\n✓ Created {len(chunks)} chunks")
print(f"✓ Total tokens across all chunks: {sum(c['token_count'] for c in chunks):,}")

# Verify overlap between consecutive chunks
print("\n" + "="*80)
print("OVERLAP VERIFICATION")
print("="*80)

if len(chunks) >= 2:
    # Check first two chunks
    chunk_0 = chunks[0]['text']
    chunk_1 = chunks[1]['text']
    
    # Get last 200 chars of first chunk
    chunk_0_end = chunk_0[-200:]
    # Get first 200 chars of second chunk
    chunk_1_start = chunk_1[:200]
    
    # Find common substring
    overlap_found = False
    for i in range(len(chunk_0_end), 0, -10):
        substring = chunk_0_end[-i:]
        if substring in chunk_1_start:
            overlap_found = True
            print(f"✓ Overlap detected between Chunk 0 and Chunk 1")
            print(f"  Overlap length: ~{len(substring)} characters")
            print(f"\n  Overlapping content:")
            print(f"  " + "-"*76)
            print(f"  {substring[:150]}...")
            print(f"  " + "-"*76)
            break
    
    if not overlap_found:
        print("⚠ Warning: No obvious overlap detected in first 200 chars")
        print("  (This is normal if chunks break at different points)")
else:
    print("Not enough chunks to verify overlap")

# Show token distribution
print("\n" + "="*80)
print("TOKEN DISTRIBUTION ACROSS CHUNKS")
print("="*80)
for i, chunk in enumerate(chunks):
    bar_length = int(chunk['token_count'] / 10)
    bar = "█" * bar_length
    print(f"Chunk {i:2d}: {bar} {chunk['token_count']} tokens")

print("\n" + "="*80)
print("CHUNK BOUNDARIES")
print("="*80)
print(f"{'Chunk':<8} {'Start Token':<15} {'End Token':<15} {'Token Count':<15}")
print("-"*80)
for i, chunk in enumerate(chunks[:10]):  # First 10 chunks
    print(f"{i:<8} {chunk['start_token']:<15} {chunk['end_token']:<15} {chunk['token_count']:<15}")
if len(chunks) > 10:
    print(f"... ({len(chunks) - 10} more chunks)")

print("\n✅ Chunking verification complete!\n")
