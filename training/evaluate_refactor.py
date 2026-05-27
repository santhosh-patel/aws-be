import asyncio
import argparse
import json
import os
import sys
from pathlib import Path
from typing import List, Dict, Any
from datetime import date, datetime

# Add backend to path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.append(str(backend_dir))

from app.pipeline.intent_classifier import IntentClassifier
from app.pipeline.time_parser import DeterministicTimeParser
from app.planner.modifier_detector import ModifierDetector
from app.mapper.hybrid_mapper import HybridToolMapper
from app.llm.openai_client import OpenAIClient

class MockOpenAIClient:
    """Mock client to bypass API calls"""
    def __init__(self):
        self.api_key = "mock"
        
    def chat(self, messages, **kwargs):
        # Return a dummy JSON for disambiguator if needed, or just text
        return json.dumps({
            "selected_tool": "unknown", 
            "confidence": 0.5, 
            "reason": "Mocked LLM"
        })

class RefactorEvaluator:
    def __init__(self):
        self.intent_classifier = IntentClassifier()
        self.time_parser = DeterministicTimeParser()
        self.modifier_detector = ModifierDetector()
        
        # Initialize Mapper with Mock LLM
        # We need the real embeddings though
        self.mapper = HybridToolMapper(
            llm_client=MockOpenAIClient(),
            metadata_path=str(backend_dir / "app/mapper/tool_metadata.json"),
            cache_dir=str(backend_dir / "datasets/embeddings_cache")
        )
        # Force LLM weight to 0 to test pure Semantic + Boosting
        self.mapper.confidence_fusion.llm_weight = 0.0
        self.mapper.confidence_fusion.embedding_weight = 1.0

    async def run(self, input_file: str):
        print(f"Loading data from {input_file}...")
        with open(input_file, 'r') as f:
            data = json.load(f)
            
        correct_tools = 0
        correct_intents = 0
        correct_time = 0
        total = 0
        
        results = []
        
        print(f"Evaluating {len(data)} queries with Refactored Pipeline...")
        
        for entry in data:
            query = entry['query']
            expected_tool = entry.get('expected_tool')
            
            # 1. Intent Classification
            predicted_intent = self.intent_classifier.classify(query)
            
            # 2. Time Parsing
            time_result = self.time_parser.parse(query)
            time_range = time_result[0] if time_result else None
            
            # 3. Modifier Stripping
            clean_query = self.modifier_detector.strip_modifiers(query)
            
            # 4. Hybrid Mapping (Boosted)
            if predicted_intent == 'CONVERSATIONAL':
                selected_tool = None
            else:
                mapping_result = self.mapper.map(
                    clean_query, 
                    classified_intent=predicted_intent
                )
                selected_tool = mapping_result.selected_tool
            
            # Evaluation
            if expected_tool is None:
                is_tool_correct = (selected_tool is None)
            else:
                is_tool_correct = (selected_tool == expected_tool)
            
            # Check Time Accuracy (heuristically)
            expected_params = entry.get('expected_parameters', {}) or {}
            expected_time = expected_params.get('time_range')
            
            # Very basic check: if we found a time and expected one existed
            is_time_correct = False
            if expected_time and time_range:
                is_time_correct = True # We found something!
            elif not expected_time and not time_range:
                is_time_correct = True
            
            if is_tool_correct: correct_tools += 1
            if is_time_correct: correct_time += 1
            total += 1
            
            print(f"[{total}/{len(data)}] {query[:50]}...")
            print(f"  Intent: {predicted_intent}")
            print(f"  Detect Time: {time_result[1] if time_result else 'None'}")
            print(f"  Clean Q: {clean_query}")
            print(f"  Tool: {selected_tool} (Exp: {expected_tool}) {'[OK]' if is_tool_correct else '[FAIL]'}")
            
            results.append({
                "query": query,
                "predicted_intent": predicted_intent,
                "selected_tool": selected_tool,
                "expected_tool": expected_tool,
                "correct": is_tool_correct
            })
            
        accuracy = (correct_tools / total) * 100 if total else 0
        print(f"\nFinal Tool Accuracy (No LLM): {accuracy:.2f}%")
        
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    args = parser.parse_args()
    
    evaluator = RefactorEvaluator()
    asyncio.run(evaluator.run(args.input))
