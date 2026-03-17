"""
Test script for RAG architectural improvements
"""

from app.rag import WizardStoreRAG

def test_improvements():
    """Test the new intent classification and soft grounding features"""
    
    print("\n🧪 TESTING RAG ARCHITECTURAL IMPROVEMENTS\n")
    print("="*80)
    
    # Initialize RAG
    try:
        rag = WizardStoreRAG()
        print()
    except Exception as e:
        print(f"Failed to initialize: {e}")
        print("Run 'python app/ingest.py' first to build the knowledge base.")
        return
    
    # Test cases
    test_queries = [
        # Should work - specific product query
        ("How much is the Dragon Heartstring Wand - Slytherin Edition?", "specific_product"),
        
        # Should be refused - not in database (soft grounding)
        ("Do you sell broomsticks?", "specific_product"),
        
        # Should work - policy query
        ("What is your return policy?", "policy"),
        
        # Should work - FAQ
        ("How do I track my order?", "faq"),
        
        # Should be refused - completely irrelevant
        ("What's the weather like today?", "general"),
    ]
    
    for i, (query, expected_intent) in enumerate(test_queries, 1):
        print(f"\n{'='*80}")
        print(f"TEST {i}: {query}")
        print(f"Expected Intent: {expected_intent}")
        print("="*80)
        
        # Test intent classification
        intent = rag._classify_query_intent(query)
        print(f"✓ Classified Intent: {intent}")
        
        # Get full answer
        answer = rag.answer_question(query, verbose=True)
        
        print("-"*80)
        input("\nPress Enter for next test...")

if __name__ == "__main__":
    test_improvements()
