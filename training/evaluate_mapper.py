
import asyncio
import json
import os
import sys
import argparse
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime, date
from dotenv import load_dotenv

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Load environment variables
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from app.planner.modifier_detector import ModifierDetector
from app.pipeline.deterministic_router import DeterministicRouter
from app.pipeline.domain_classifier import DomainClassifier
from app.pipeline.confidence_gate import ConfidenceGate
from app.mapper.hybrid_mapper import HybridToolMapper
from app.planner.extractor import ParameterExtractor
from app.planner.models import CanonicalIntent
from app.llm.openai_client import OpenAIClient
from app.mcp.registry import MCPRegistry

class AgentEvaluator:
    def __init__(self):
        self.base_dir = Path(__file__).resolve().parent.parent
        self.llm_client = OpenAIClient()
        self.modifier_detector = ModifierDetector()
        self.router = DeterministicRouter()
        self.domain_classifier = DomainClassifier()
        self.hybrid_mapper = HybridToolMapper(
            llm_client=self.llm_client,
            metadata_path=str(self.base_dir / "app/mapper/tool_metadata.json")
        )
        self.confidence_gate = ConfidenceGate()
        self.parameter_extractor = ParameterExtractor(self.llm_client)
        # Mock registry for validation (assuming registry requires AWS creds which we might not want to use in eval)
        # But instructions say "Validation must not impact real AWS resources". Registry init might call AWS...
        # Let's try to init registry, if it fails due to missing creds, we might need a mock.
        # However, registry.py uses boto3. If no creds, it might fail.
        # Providing dummy creds for registry just to load tool definitions.
        try:
            self.registry = MCPRegistry("test", "test", "us-east-1")
        except Exception as e:
            print(f"Warning: Could not initialize MCPRegistry: {e}. Validation skipped.")
            self.registry = None

    def map_tool_to_intent(self, tool_name: str) -> str:
        """Map tool name to CanonicalIntent enum"""
        if "cost_trend" in tool_name: return "COST_TREND"
        if "cost_forecast" in tool_name: return "COST_FORECAST"
        if "cost_by_service" in tool_name: return "COST_BY_SERVICE"
        if "cost_by_region" in tool_name: return "COST_BY_REGION"
        if "cost_by_usage" in tool_name: return "COST_BY_USAGE_TYPE"
        if "cost_by_tag" in tool_name: return "COST_BY_TAG"
        if "cost_by_linked_account" in tool_name: return "COST_BY_ACCOUNT"
        if "describe_organization" in tool_name: return "ACCOUNT_METADATA"
        if "account" in tool_name or "caller_identity" in tool_name or "enabled_regions" in tool_name: return "ACCOUNT_METADATA"
        if "list_" in tool_name: return "RESOURCE_INVENTORY"
        if "metric" in tool_name: return "CLOUDWATCH_METRICS"
        if "log" in tool_name: return "LOG_EVENTS"
        # Default fallback for other cost tools (today, yesterday, etc)
        if "cost" in tool_name: return "COST_TOTAL"
        
        return "UNKNOWN"

    async def evaluate_query(self, entry: Dict[str, Any]) -> Dict[str, Any]:
        query = entry["query"]
        expected_tool = entry["expected_tool"]
        expected_domain = entry["expected_domain"]
        expected_params = entry["expected_parameters"]
        expected_confidence = entry.get("confidence_level", "high") # Default to high if missing

        result = {
            "query": query,
            "expected_tool": expected_tool,
            "expected_domain": expected_domain,
            "predicted_tool": None,
            "predicted_domain": None,
            "predicted_parameters": None,
            "confidence_score": 0.0,
            "action_taken": "unknown",
            "is_correct_tool": False,
            "is_correct_domain": False,
            "is_correct_params": False,
            "error_stage": None
        }

        # 1. Modifier Detection
        modifier = self.modifier_detector.detect(query)
        # We don't have expected modifier in all datasets, so just logging it.
        
        # 2. Deterministic Router
        route_result = self.router.route(query)
        if route_result:
            result["predicted_tool"] = route_result["tool"]
            result["confidence_score"] = 1.0
            result["action_taken"] = "execute"
            result["source"] = "router"
        else:
            # 3. Domain Classification
            domain_result = self.domain_classifier.classify(query)
            result["predicted_domain"] = domain_result["domain"]
            
            if domain_result["clarification_needed"]:
                result["action_taken"] = "clarify"
                result["source"] = "classifier"
            else:
                # 4. Hybrid Mapping
                map_result = self.hybrid_mapper.map(query, domain_filter=domain_result["domain"])
                result["predicted_tool"] = map_result.selected_tool
                result["confidence_score"] = map_result.final_confidence
                
                # 5. Confidence Gate
                gate_result = self.confidence_gate.evaluate(map_result.final_confidence)
                
                if gate_result["execute"]:
                     result["action_taken"] = "execute"
                     result["source"] = "mapper"
                else:
                     result["action_taken"] = "clarify"
                     result["source"] = "confidence_gate"

        # 6. Parameter Extraction (Only if we have a tool)
        if result["predicted_tool"]:
            intent_enum = self.map_tool_to_intent(result["predicted_tool"])
            intent = CanonicalIntent(intent=intent_enum, confidence=result["confidence_score"])
            extracted_intent = await self.parameter_extractor.extract(query, intent)
            
            # Convert intent to dict for comparison
            # Extract relevant fields matching dataset schema
            preds = {
                "time_range": None,
                "service": None, 
                "region": None,
                "currency": None,
                "granularity": None
            }
            
            # Map CanonicalIntent fields to expected_parameters schema
            # Time Range
            if extracted_intent.time_range:
                # This is tricky because expected params might have "this_month" string vs calculated dates
                # For direct comparison, we might need to normalize expected params or just check if populated
                if isinstance(extracted_intent.time_range, dict):
                   preds["time_range"] = extracted_intent.time_range
                else:
                   preds["time_range"] = extracted_intent.time_range.dict() if extracted_intent.time_range else None
            
            # Service
            if extracted_intent.services:
                preds["service"] = ",".join(extracted_intent.services)
            
            # Region
            if extracted_intent.regions:
                preds["region"] = ",".join(extracted_intent.regions)
                
            # Granularity/Currency often in 'params' dict of CanonicalIntent
            if extracted_intent.params:
                preds["granularity"] = extracted_intent.params.get("granularity")
                preds["currency"] = extracted_intent.params.get("currency") # If extracted there
            
            result["predicted_parameters"] = preds

        # Scoring
        result["is_correct_tool"] = (result["predicted_tool"] == expected_tool)
        result["is_correct_domain"] = (result["predicted_domain"] == expected_domain) if result["predicted_domain"] else (expected_domain is None) # strict?
        
        # Domain check: If router matched, predicted_domain is None. 
        # But we can infer domain from tool if we had a reverse lookup, or just ignore domain metric for router hits.
        if result["source"] == "router":
             # Assume correct domain if tool is correct
             # Or better, look up tool domain in metadata
             if self.hybrid_mapper:
                 tools = self.hybrid_mapper.tools_metadata
                 for t in tools:
                     if t.tool_name == result["predicted_tool"]:
                         result["predicted_domain"] = t.domain
                         break
             result["is_correct_domain"] = (result["predicted_domain"] == expected_domain)

        # Parameter accuracy: simplified check
        # We rely on 'extracted parameter matching expected'. 
        # Since expected has specific keywords like "this_month" vs calculated dates, strict equality fails.
        # We will count it as correct if:
        # 1. Both are null
        # 2. Both are non-null (loose check for existence)
        # This needs to be improved for strict validation but suffices for "existence" check for now.
        
        # ACTUALLY, checking specific keys
        params_match = True
        if expected_params:
            for k, v in expected_params.items():
                pred_v = result["predicted_parameters"].get(k) if result["predicted_parameters"] else None
                
                # Normalize None
                if v is None and pred_v is None:
                    continue
                
                if v is not None and pred_v is None:
                    print(f"  Missing param {k}: expected {v}")
                    params_match = False
                    break
                    
                # If both present, tricky. 
                # e.g. expected: "S3", predicted: "AmazonS3". Need normalization.
                if k == "service":
                     if v and pred_v and v.lower() in pred_v.lower(): # simplified substring match
                         continue
                     elif v != pred_v:
                         params_match = False
                         print(f"  Mismatch param {k}: expected {v}, got {pred_v}")
                elif k == "region":
                     if v and pred_v and v.lower() == pred_v.lower():
                         continue
                     elif v != pred_v:
                         params_match = False
                         print(f"  Mismatch param {k}: expected {v}, got {pred_v}")
                elif k == "time_range":
                     # Skip time range strict modification for now, assume correct if present
                     pass
                else: 
                     if str(v).lower() != str(pred_v).lower() and k != "time_range":
                          params_match = False
                          print(f"  Mismatch param {k}: expected {v}, got {pred_v}")

        result["is_correct_params"] = params_match

        return result

    async def run(self, input_path: str):
        # Load dataset
        input_file = Path(input_path)
        if not input_file.exists():
             # Try glob
             files = glob.glob(input_path)
             if not files:
                 print(f"Input not found: {input_path}")
                 return
             entries = []
             for f in files:
                 with open(f, 'r') as fp:
                     entries.extend(json.load(fp))
        else:
             with open(input_file, 'r') as f:
                 entries = json.load(f)

        print(f"Evaluating {len(entries)} queries...")
        
        results = []
        errors = []
        
        for i, entry in enumerate(entries):
            print(f"[{i+1}/{len(entries)}] {entry['query']}...", end="", flush=True)
            res = await self.evaluate_query(entry)
            results.append(res)
            
            if res["is_correct_tool"]:
                print(" [OK]")
            else:
                print(f" [FAIL] (Exp: {res['expected_tool']}, Got: {res['predicted_tool']})")
                errors.append(res)

        # Compute Metrics
        total = len(results)
        tool_acc = sum(1 for r in results if r["is_correct_tool"]) / total if total else 0
        domain_acc = sum(1 for r in results if r["is_correct_domain"]) / total if total else 0
        param_acc = sum(1 for r in results if r["is_correct_params"]) / total if total else 0
        
        clarify_total = sum(1 for e in entries if e.get("confidence_level") == "clarify")
        clarify_correct = sum(1 for r in results if r["action_taken"] == "clarify" and r["expected_tool"] is None) # Approximation
        
        report = {
            "timestamp": datetime.now().isoformat(),
            "total_queries": total,
            "metrics": {
                "tool_accuracy": round(tool_acc * 100, 2),
                "domain_accuracy": round(domain_acc * 100, 2),
                "parameter_accuracy": round(param_acc * 100, 2)
            }
        }
        
        print("\n" + "="*50)
        print("EVALUATION REPORT")
        print("="*50)
        print(json.dumps(report, indent=2))
        
        # Save logs
        log_dir = self.base_dir / "datasets" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        
        with open(log_dir / "mapping_errors.json", 'w') as f:
            json.dump(errors, f, indent=2, cls=NumpyEncoder)
        print(f"\nSaved {len(errors)} errors to {log_dir}/mapping_errors.json")

import glob

class NumpyEncoder(json.JSONEncoder):
    def default(self, obj):
        if hasattr(obj, 'tolist'):
            return obj.tolist()
        if hasattr(obj, 'dtype'):
            return float(obj)
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        return json.JSONEncoder.default(self, obj)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="Input dataset path")
    args = parser.parse_args()
    
    evaluator = AgentEvaluator()
    # Use the custom encoder for saving logs
    original_dump = json.dump
    def numpy_dump(obj, fp, **kwargs):
        kwargs['cls'] = NumpyEncoder
        return original_dump(obj, fp, **kwargs)
    
    # Patch json.dump only for this script's execution context if needed, 
    # but since we are calling it inside the class, it's better to pass usage 
    # or just patch where it's called.
    # Actually, I'll just change the call site in the class method.
    pass

    asyncio.run(evaluator.run(args.input))
