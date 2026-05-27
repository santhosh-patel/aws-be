"""
Test script for pipeline components
Validates DeterministicRouter, DomainClassifier, and ConfidenceGate
"""
import sys
from pathlib import Path

# Add backend to path
backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))

from app.pipeline.deterministic_router import DeterministicRouter
from app.pipeline.domain_classifier import DomainClassifier
from app.pipeline.confidence_gate import ConfidenceGate


def test_deterministic_router():
    """Test deterministic router"""
    print("\n" + "="*60)
    print("Testing DeterministicRouter")
    print("="*60)
    
    router = DeterministicRouter()
    
    test_queries = [
        "what's the cost today?",
        "show me yesterday's billing",
        "current month spend",
        "list all s3 buckets",
        "what's my account ID?",
        "this won't match anything"
    ]
    
    for query in test_queries:
        result = router.route(query)
        if result:
            print(f"  [OK] '{query}'")
            print(f"  -> Tool: {result['tool']}")
            print(f"  -> Pattern: {result['matched_pattern']}")
            print(f"  -> Confidence: {result['confidence']}")
        else:
            print(f"  [FAIL] '{query}' -> No match")
    
    stats = router.get_stats()
    print(f"\nRouter Stats: {stats['total_rules']} rules, {stats['total_patterns']} patterns")


def test_domain_classifier():
    """Test domain classifier"""
    print("\n" + "="*60)
    print("Testing DomainClassifier")
    print("="*60)
    
    classifier = DomainClassifier()
    
    test_queries = [
        "show me the cost last month",
        "list all ec2 instances",
        "fetch cloudwatch logs",
        "what's my account id",
        "show cpu metrics",
        "random text without domain keywords"
    ]
    
    for query in test_queries:
        result = classifier.classify(query)
        print(f"\n'{query}'")
        print(f"  -> Domain: {result['domain']}")
        print(f"  -> Confidence: {result['confidence']}")
        print(f"  -> Tools: {len(result['filtered_tools'])} tools")
        if result['clarification_needed']:
            print(f"  -> WARN: Clarification needed")
    
    stats = classifier.get_stats()
    print(f"\nClassifier Stats: {stats['total_domains']} domains")


def test_confidence_gate():
    """Test confidence gate"""
    print("\n" + "="*60)
    print("Testing ConfidenceGate")
    print("="*60)
    
    gate = ConfidenceGate()
    
    test_scores = [0.9, 0.7, 0.6, 0.4, 0.2]
    
    for score in test_scores:
        result = gate.evaluate(score)
        print(f"\nConfidence: {score}")
        print(f"  -> Level: {result['level']}")
        print(f"  -> Execute: {result['execute']}")
        print(f"  -> Action: {result['action']}")
        print(f"  -> Reason: {result['reason']}")
    
    # Test statistics
    stats = gate.get_statistics(test_scores)
    print(f"\nGate Stats:")
    print(f"  High: {stats['high']} ({stats['high_pct']}%)")
    print(f"  Medium: {stats['medium']} ({stats['medium_pct']}%)")
    print(f"  Low: {stats['low']} ({stats['low_pct']}%)")


def test_integration():
    """Test integration of all three components"""
    print("\n" + "="*60)
    print("Testing Integration Flow")
    print("="*60)
    
    router = DeterministicRouter()
    classifier = DomainClassifier()
    gate = ConfidenceGate()
    
    query = "show me yesterday's cost"
    
    print(f"\nQuery: '{query}'")
    print("\nStep 1: Try deterministic routing...")
    det_result = router.route(query)
    if det_result:
        print(f"  [OK] Deterministic match: {det_result['tool']}")
        print(f"  [OK] Confidence: {det_result['confidence']}")
        print(f"  -> Skip AI, proceed directly to execution")
    else:
        print("  No deterministic match, proceed to domain classification...")
        
        print("\nStep 2: Classify domain...")
        dom_result = classifier.classify(query)
        print(f"  [OK] Domain: {dom_result['domain']}")
        print(f"  [OK] Filtered to {len(dom_result['filtered_tools'])} tools")
        
        print("\nStep 3: (Would run hybrid mapper here)")
        print("  -> Semantic similarity on filtered tools")
        print("  -> LLM disambiguation")
        print("  -> Confidence fusion")
        
        simulated_confidence = 0.85
        print(f"\nStep 4: Confidence gate (simulated score: {simulated_confidence})")
        gate_result = gate.evaluate(simulated_confidence)
        print(f"  [OK] Level: {gate_result['level']}")
        print(f"  [OK] Execute: {gate_result['execute']}")


if __name__ == "__main__":
    print("\nPipeline Components Test Suite")
    
    try:
        test_deterministic_router()
        test_domain_classifier()
        test_confidence_gate()
        test_integration()
        
        print("\n" + "="*60)
        print("[OK] All tests completed successfully!")
        print("="*60 + "\n")
        
    except Exception as e:
        print(f"\n[FAIL] Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
