import asyncio
import argparse
import json
import os
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import date, datetime
import re

# Add backend to path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.append(str(backend_dir))

from app.pipeline.conversational_filter import ConversationalFilter
from app.pipeline.intent_classifier import IntentClassifier
from app.pipeline.tool_restriction import ToolRestrictionLayer
from app.pipeline.time_parser import DeterministicTimeParser
from app.planner.modifier_detector import ModifierDetector
from app.mapper.hybrid_mapper import HybridToolMapper
from app.llm.openai_client import OpenAIClient

class MockOpenAIClient:
    """Mock client to bypass API calls"""
    def chat(self, messages, **kwargs):
        # Return dummy for hybrid mode if LLM disabled
        return json.dumps({
            "selected_tool": "unknown", 
            "confidence": 0.5, 
            "reason": "Mocked LLM"
        })

class PipelineEvaluator:
    def __init__(self, mode: str = 'deterministic'):
        self.mode = mode
        
        # Initialize Pipeline Components
        self.conversational_filter = ConversationalFilter()
        self.intent_classifier = IntentClassifier()
        self.restriction_layer = ToolRestrictionLayer()
        self.time_parser = DeterministicTimeParser()
        self.modifier_detector = ModifierDetector()
        
        # LLM Client
        if self.mode == 'hybrid':
            # In a real scenario, this would load from env
            # For this evaluation, unless we have a key, we might need to mock or fail
            # The user user provided 'Partial: Quota limit' before, so checks are needed.
            api_key = os.getenv("OPENAI_API_KEY")
            if api_key:
                self.llm_client = OpenAIClient(api_key=api_key)
            else:
                 print("WARNING: No OpenAI API Key found. Fallback to Mock in Hybrid mode.")
                 self.llm_client = MockOpenAIClient()
        else:
            self.llm_client = MockOpenAIClient()

        # Hybrid Mapper
        # Force weights based on mode
        self.mapper = HybridToolMapper(
            llm_client=self.llm_client,
            metadata_path=str(backend_dir / "app/mapper/tool_metadata.json"),
            cache_dir=str(backend_dir / "datasets/embeddings_cache")
        )
        
        if self.mode == 'deterministic':
            self.mapper.confidence_fusion.llm_weight = 0.0
            self.mapper.confidence_fusion.embedding_weight = 1.0

    async def run_pipeline(self, query: str) -> Dict[str, Any]:
        """
        Run the 7-stage pipeline and return decision + metadata.
        """
        stage_log = {}
        
        # Stage 1: Conversational Filter
        conv_result = self.conversational_filter.detect(query)
        if conv_result:
            return {
                "selected_tool": None,
                "intent": "CONVERSATIONAL",
                "stage": "conversational_filter",
                "confidence": 1.0,
                "params": {}
            }
            
        # Stage 2: Intent Classification
        predicted_intent = self.intent_classifier.classify(query)
        stage_log['intent'] = predicted_intent
        
        # Stage 3: Tool Restriction
        allowed_tools = self.restriction_layer.get_allowed_tools(predicted_intent)
        
        # Stage 4: Time Parsing & Modifier Extraction
        # (These update params, not tool selection usually, unless we use them for disambiguation later)
        time_result = self.time_parser.parse(query)
        clean_query = self.modifier_detector.strip_modifiers(query)
        
        params = {}
        if time_result:
            params['time_range'] = time_result[2] # normalized key
            
        selected_tool = None
        decision_stage = "unknown"
        confidence = 0.0
        
        # Logic:
        # If intent is CLARIFICATION_REQUIRED -> Stop
        # If allowed_tools is empty -> Stop (Clarify)
        # If allowed_tools has 1 tool -> Direct Execution (Deterministic)
        # If allowed_tools has > 1 tool -> Hybrid Mapper (Restricted)
        
        if predicted_intent == 'CLARIFICATION_REQUIRED':
            selected_tool = None # Should return clarification
            decision_stage = "intent_classifier"
            confidence = 1.0 # High confidence that we need help? Or low confidence?
                             # clarification_precision metric uses this.
        
        elif not allowed_tools:
            # Intent detected but no tools map to it? (Shouldn't happen with valid config)
            # OR mapped to Fallback
            selected_tool = None
            decision_stage = "tool_restriction"
        
        elif len(allowed_tools) == 1:
            selected_tool = allowed_tools[0]
            decision_stage = "tool_restriction_direct"
            confidence = 1.0
            
        else:
            # Ambiguity handling (Multiple allowed or Clarification needed)
            
            # Setup for Hybrid Mapper
            target_allowed = allowed_tools if allowed_tools else None 
            # If CLARIFICATION_REQUIRED (allowed_tools empty), we pass None to map()
            # which will use semantic search to find candidates globally (or we could restrict to all tools?)
            # But the requirement is "LLM should operate only within the 25.4% ambiguity bucket".
            # If intent is CLARIFICATION_REQUIRED, we rely on semantic search + LLM.
            
            # MODE CHECK: If deterministic mode, we can't use LLM.
            if self.mode == 'deterministic':
                 # Fallback to simple semantic top-1 or None
                 # But standard map() uses LLM if configured.
                 # In deterministic mode, HybridMapper is configured with llm_weight=0 (but still calls select_best_tool?)
                 # Actually HybridMapper calls llm_disambiguator.select_best_tool.
                 # We need to make sure we don't call LLM in deterministic mode if we want to be strict,
                 # OR our Mock client handles it (which it does).
                 pass

            mapping_result = await self.mapper.map(
                clean_query, 
                classified_intent=predicted_intent if predicted_intent != 'CLARIFICATION_REQUIRED' else None,
                allowed_tools=target_allowed
            )
            
            selected_tool = mapping_result.selected_tool
            confidence = mapping_result.confidence
            decision_stage = "hybrid_mapper_llm" if self.mode == 'hybrid' else "hybrid_mapper_deterministic"
            
            # Confidence Guardrail (Phase 2)
            # "Only execute if confidence >= threshold ... Suggested: 0.75"
            # But only if we are actually using LLM judgment.
            if self.mode == 'hybrid':
                if confidence < 0.75:
                    selected_tool = None # Force clarification
                    decision_stage = "confidence_gate_rejection"
                
        return {
            "selected_tool": selected_tool,
            "intent": predicted_intent,
            "stage": decision_stage,
            "confidence": confidence,
            "params": params
        }

    async def run(self, input_file: str, max_samples: int = None):
        print(f"Loading data from {input_file}...")
        with open(input_file, 'r') as f:
            data = json.load(f)
            
        if max_samples:
            data = data[:max_samples]
            
        results = []
        confusion_matrix = {}
        stage_stats = {}
        
        # Metrics Counters
        correct_tools = 0
        correct_intents = 0 # We don't have ground truth intent in dataset usually, only expected_tool.
                            # We can infer expected intent from expected tool for analysis?
                            # Or we only measure tool accuracy for now if dataset lacks intent labels.
                            # The synthetic dataset might not have intent labels.
                            # We will infer 'expected_intent' from the 'expected_tool' using reverse mapping
                            # or just skip intent accuracy if we can't.
                            # For now: We'll skip formal Intent Accuracy metric unless we map back.
                            # actually, let's map back for better stats.
                            
        tool_to_intent_map = {}
        for intent, tools in self.restriction_layer.RESTRICTIONS.items():
            for tool in tools:
                tool_to_intent_map[tool] = intent
                
        total = 0
        deterministic_count = 0
        clarification_correct = 0
        clarification_total = 0
        false_positive_exec = 0
        
        print(f"Evaluating {len(data)} queries in {self.mode.upper()} mode...")
        
        for entry in data:
            query = entry['query']
            expected_tool = entry.get('expected_tool')
            
            # Infer expected intent
            expected_intent = tool_to_intent_map.get(expected_tool, "UNKNOWN")
            if expected_tool is None:
                # Could be conversational or clarification
                # Hard to distinguish without labels. 
                # If conversational, intent is CONVERSATIONAL.
                # Inspect query??
                pass

            # Run Pipeline
            output = await self.run_pipeline(query)
            
            predicted_tool = output['selected_tool']
            predicted_intent = output['intent']
            stage = output['stage']
            
            # Evaluation
            is_tool_correct = False
            if expected_tool is None:
                is_tool_correct = (predicted_tool is None)
            else:
                is_tool_correct = (predicted_tool == expected_tool)
            
            if is_tool_correct:
                correct_tools += 1
                
            # Intent Accuracy (Heuristic)
            # If tool is correct, intent is likely correct.
            # If tool is wrong, intent might still be correct (if multiple tools for intent).
            if expected_intent != "UNKNOWN":
                if predicted_intent == expected_intent:
                    correct_intents += 1
            
            # Stage Stats
            stage_stats[stage] = stage_stats.get(stage, 0) + 1
            if stage in ['conversational_filter', 'tool_restriction_direct', 'intent_classifier']: # intent_classifier = clarification
                 deterministic_count += 1
                 
            # Confusion Matrix
            if not is_tool_correct:
                key = f"{expected_tool} -> {predicted_tool}"
                confusion_matrix[key] = confusion_matrix.get(key, 0) + 1
                
                # Log detailed failure
                results.append({
                    "query": query,
                    "expected": expected_tool,
                    "predicted": predicted_tool,
                    "intent": predicted_intent,
                    "stage": stage
                })
                
            total += 1
            
            # print(f"[{total}] {query[:30]}... -> {predicted_tool} ({'[OK]' if is_tool_correct else '[FAIL]'}) [{stage}]")
            
        # Reporting
        accuracy = (correct_tools / total) * 100 if total else 0
        det_rate = (deterministic_count / total) * 100 if total else 0
        
        print("\n=== Evaluation Results ===")
        print(f"Mode: {self.mode}")
        print(f"Tool Accuracy: {accuracy:.2f}%")
        print(f"Deterministic Rate: {det_rate:.2f}%")
        
        print("\n=== Stage Attribution ===")
        for s, count in stage_stats.items():
             print(f"  {s}: {count} ({count/total*100:.1f}%)")
             
        print("\n=== Top Confusions ===")
        sorted_conf = sorted(confusion_matrix.items(), key=lambda x: x[1], reverse=True)[:5]
        for k, v in sorted_conf:
            print(f"  {k}: {v}")
            
        # Save detailed logs
        log_dir = backend_dir / "datasets/logs"
        log_dir.mkdir(exist_ok=True)
        
        with open(log_dir / "confusion_matrix.json", 'w') as f:
            json.dump(confusion_matrix, f, indent=2)
            
        with open(log_dir / "stage_attribution.json", 'w') as f:
            json.dump(stage_stats, f, indent=2)
            
        with open(log_dir / "failed_queries.json", 'w') as f:
            json.dump(results, f, indent=2)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--mode", default="deterministic", choices=["deterministic", "hybrid"])
    parser.add_argument("--max-samples", type=int, default=None)
    
    args = parser.parse_args()
    
    evaluator = PipelineEvaluator(mode=args.mode)
    asyncio.run(evaluator.run(args.input, args.max_samples))
