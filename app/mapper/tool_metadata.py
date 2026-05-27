"""
Tool Metadata Schema and Loader
"""
import json
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from datetime import datetime
from pathlib import Path
import numpy as np


@dataclass
class ToolMetadata:
    """Enhanced tool metadata for hybrid mapping"""
    tool_name: str
    domain: str  # 'cost', 'inventory', 'logs', 'metrics', 'account'
    description: str
    example_queries: List[str]
    required_parameters: List[str]
    optional_parameters: List[str]
    service_tags: List[str]
    synonyms: List[str]
    version: str
    
    # Embedding cache (populated at runtime)
    embedding_vector: Optional[np.ndarray] = None
    embedding_timestamp: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict (excluding embedding vector)"""
        return {
            'tool_name': self.tool_name,
            'domain': self.domain,
            'description': self.description,
            'example_queries': self.example_queries,
            'required_parameters': self.required_parameters,
            'optional_parameters': self.optional_parameters,
            'service_tags': self.service_tags,
            'synonyms': self.synonyms,
            'version': self.version
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ToolMetadata':
        """Create from dict"""
        return cls(
            tool_name=data['tool_name'],
            domain=data['domain'],
            description=data['description'],
            example_queries=data['example_queries'],
            required_parameters=data['required_parameters'],
            optional_parameters=data['optional_parameters'],
            service_tags=data['service_tags'],
            synonyms=data['synonyms'],
            version=data['version']
        )
    
    def get_embedding_text(self) -> str:
        """Get text for embedding (description + examples + synonyms)"""
        examples_text = ', '.join(self.example_queries[:5])
        synonyms_text = ', '.join(self.synonyms)
        return f"{self.description}. Examples: {examples_text}. Also known as: {synonyms_text}"


def load_tool_metadata(metadata_path: str) -> List[ToolMetadata]:
    """
    Load tool metadata from JSON file
    
    Args:
        metadata_path: Path to tool_metadata.json
        
    Returns:
        List of ToolMetadata objects
    """
    path = Path(metadata_path)
    if not path.exists():
        raise FileNotFoundError(f"Tool metadata not found: {metadata_path}")
    
    with open(path, 'r') as f:
        data = json.load(f)
    
    return [ToolMetadata.from_dict(item) for item in data]


def save_tool_metadata(metadata_list: List[ToolMetadata], metadata_path: str):
    """
    Save tool metadata to JSON file
    
    Args:
        metadata_list: List of ToolMetadata objects
        metadata_path: Path to save to
    """
    path = Path(metadata_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    
    data = [meta.to_dict() for meta in metadata_list]
    
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)
