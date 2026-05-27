"""
MCP Tools - Executable AWS capabilities
All tools are read-only, deterministic, and LLM-agnostic
"""
from typing import Any, Dict, Callable
from abc import ABC, abstractmethod
import boto3
import time
import logging
from datetime import datetime, timedelta
from ..schemas import ToolInputSchema, ToolOutputSchema

logger = logging.getLogger(__name__)


class MCPTool(ABC):
    """Base class for all MCP tools"""
    
    def __init__(self):
        self.name: str = ""
        self.description: str = ""
        self.input_schema: type[ToolInputSchema] = ToolInputSchema
        self.output_schema: type[ToolOutputSchema] = ToolOutputSchema
        self.required_permissions: list[str] = []
    
    @abstractmethod
    def execute(self, input_data: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the tool with given input and context"""
        pass
    
    def validate_input(self, input_data: Dict[str, Any]) -> bool:
        """Validate input against schema"""
        try:
            self.input_schema(**input_data)
            return True
        except Exception:
            return False


class AWSBaseTool(MCPTool):
    """Base class for AWS tools with common boto3 setup"""
    
    def __init__(self, aws_access_key: str, aws_secret_key: str, region: str = "us-east-1"):
        super().__init__()
        self.session = boto3.Session(
            aws_access_key_id=aws_access_key,
            aws_secret_access_key=aws_secret_key,
            region_name=region
        )
    
    def get_client(self, service_name: str):
        """Get boto3 client for a service"""
        return self.session.client(service_name)
    
    def safe_execute(self, func: Callable, error_msg: str = "AWS API call failed") -> Dict[str, Any]:
        """
        Execute AWS API call safely with:
        - Structured error mapping for AWS exceptions
        - Execution timing for performance monitoring
        """
        start_time = time.monotonic()
        try:
            result = func()
            elapsed_ms = round((time.monotonic() - start_time) * 1000)
            logger.info(f"[{self.name}] executed in {elapsed_ms}ms")
            return {"success": True, "data": result, "error": None, "elapsed_ms": elapsed_ms}
        except Exception as e:
            elapsed_ms = round((time.monotonic() - start_time) * 1000)
            # Try structured error mapping for AWS-specific errors
            try:
                from botocore.exceptions import ClientError, NoCredentialsError, PartialCredentialsError
                if isinstance(e, (ClientError, NoCredentialsError, PartialCredentialsError)):
                    from ..executor.error_mapper import ErrorMapper
                    mapped = ErrorMapper.map_error(e)
                    logger.warning(f"[{self.name}] AWS error ({mapped.get('code', 'UNKNOWN')}): {mapped.get('message', str(e))} [{elapsed_ms}ms]")
                    return {"success": False, "data": None, "error": mapped, "elapsed_ms": elapsed_ms}
            except ImportError:
                pass  # ErrorMapper not available, fall through to generic handler
            
            logger.error(f"[{self.name}] failed: {str(e)} [{elapsed_ms}ms]")
            return {"success": False, "data": None, "error": f"{error_msg}: {str(e)}", "elapsed_ms": elapsed_ms}

