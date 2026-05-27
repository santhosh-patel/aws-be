"""
Tool Execution Engine - Layer 3
Executes MCP tools and aggregates results
"""
from typing import Dict, Any, List
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging
import time
from ..mcp.registry import MCPRegistry

logger = logging.getLogger(__name__)

MAX_PARALLEL_WORKERS = 4


class ToolExecutor:
    """
    Executes MCP tools safely.
    Handles pagination, normalization, and parallel execution.
    Returns clean JSON.
    """
    
    def __init__(self, registry: MCPRegistry):
        self.registry = registry
    
    def execute_plan(self, plan: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a plan from the Intent Planner.
        Returns aggregated results.
        """
        
        intent_data = plan.get('intent', {})
        if isinstance(intent_data, dict):
            intent_str = intent_data.get('intent', 'UNKNOWN')
        else:
            intent_str = str(intent_data)

        steps = plan.get('steps', [])
        
        # Handle unsupported or unknown intents
        if intent_str in ['UNSUPPORTED_TIME_RANGE', 'UNSUPPORTED', 'UNKNOWN']:
            if not steps:
                return {
                    "success": False,
                    "intent": intent_str,
                    "message": plan.get('explanation', 'Unknown error'),
                    "results": []
                }
        
        # Execute tools
        start_time = time.monotonic()
        results = []
        for step in steps:
            tool_name = step.get('tool_name')
            arguments = step.get('arguments', {})
            
            result = self.execute_tool(tool_name, arguments)
            results.append({
                "tool": tool_name,
                "result": result
            })
        
        elapsed_ms = round((time.monotonic() - start_time) * 1000)
        logger.info(f"Plan executed: {len(steps)} step(s), intent={intent_str}, {elapsed_ms}ms total")
        
        return {
            "success": True,
            "intent": intent_str,
            "time_range": intent_data.get('time_range', {}),
            "results": results
        }
    
    def execute_tool(self, tool_name: str, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a single tool"""
        
        tool = self.registry.get_tool(tool_name)
        if not tool:
            return {
                "success": False,
                "error": f"Tool '{tool_name}' not found in registry",
                "data": None
            }
        
        # Validate input
        if not tool.validate_input(input_data):
            return {
                "success": False,
                "error": f"Invalid input for tool '{tool_name}'",
                "data": None
            }
        
        # Execute tool
        try:
            result = tool.execute(input_data, context={})
            return result
        except Exception as e:
            logger.error(f"Tool '{tool_name}' execution failed: {str(e)}")
            return {
                "success": False,
                "error": f"Tool execution failed: {str(e)}",
                "data": None
            }
    
    def execute_tools_parallel(self, tools_with_inputs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Execute multiple tools in parallel using a thread pool.
        Boto3 API calls are I/O-bound, so threads provide real speedup.
        """
        if not tools_with_inputs:
            return []
        
        # For a single tool, skip thread pool overhead
        if len(tools_with_inputs) == 1:
            item = tools_with_inputs[0]
            result = self.execute_tool(item.get('tool'), item.get('input', {}))
            return [{"tool": item.get('tool'), "result": result}]
        
        results = [None] * len(tools_with_inputs)
        num_workers = min(MAX_PARALLEL_WORKERS, len(tools_with_inputs))
        
        with ThreadPoolExecutor(max_workers=num_workers) as executor:
            future_to_index = {}
            for idx, item in enumerate(tools_with_inputs):
                tool_name = item.get('tool')
                input_data = item.get('input', {})
                future = executor.submit(self.execute_tool, tool_name, input_data)
                future_to_index[future] = (idx, tool_name)
            
            for future in as_completed(future_to_index):
                idx, tool_name = future_to_index[future]
                try:
                    result = future.result()
                except Exception as e:
                    logger.error(f"Parallel execution failed for '{tool_name}': {str(e)}")
                    result = {"success": False, "error": f"Parallel execution failed: {str(e)}", "data": None}
                results[idx] = {"tool": tool_name, "result": result}
        
        return results

