"""
Embedding Service using Sentence Transformers
Provides semantic similarity computation for tool selection
"""
import numpy as np
from typing import Dict, Optional
from pathlib import Path
from datetime import datetime
import hashlib


class EmbeddingService:
    """
    Embedding service for semantic similarity
    Uses sentence-transformers for local inference
    """
    
    def __init__(self, model_name: str = 'all-MiniLM-L6-v2', cache_dir: Optional[str] = None):
        """
        Initialize embedding service
        
        Args:
            model_name: Name of sentence-transformers model
            cache_dir: Directory to cache embeddings (optional)
        """
        self.model_name = model_name
        self.model = None  # Lazy load
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.memory_cache: Dict[str, np.ndarray] = {}
        
        if self.cache_dir:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
    
    def _load_model(self):
        """Lazy load the sentence transformer model"""
        if self.model is None:
            try:
                from sentence_transformers import SentenceTransformer
                self.model = SentenceTransformer(self.model_name)
                print(f"[OK] Loaded embedding model: {self.model_name}")
            except ImportError:
                raise ImportError(
                    "sentence-transformers not installed. "
                    "Install with: pip install sentence-transformers"
                )
    
    def embed_text(self, text: str, use_cache: bool = True) -> np.ndarray:
        """
        Generate embedding for text
        
        Args:
            text: Text to embed
            use_cache: Whether to use memory cache
            
        Returns:
            Embedding vector as numpy array
        """
        # Check memory cache
        if use_cache:
            cache_key = self._get_cache_key(text)
            if cache_key in self.memory_cache:
                return self.memory_cache[cache_key]
        
        # Ensure model is loaded
        self._load_model()
        
        # Generate embedding
        embedding = self.model.encode(text.lower().strip(), convert_to_numpy=True)
        
        # Cache result
        if use_cache:
            cache_key = self._get_cache_key(text)
            self.memory_cache[cache_key] = embedding
        
        return embedding
    
    def compute_similarity(self, vec1: np.ndarray, vec2: np.ndarray) -> float:
        """
        Compute cosine similarity between two vectors
        
        Args:
            vec1: First embedding vector
            vec2: Second embedding vector
            
        Returns:
            Similarity score 0-1 (higher = more similar)
        """
        # Cosine similarity
        dot_product = np.dot(vec1, vec2)
        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        similarity = dot_product / (norm1 * norm2)
        
        # Normalize to 0-1 range (cosine similarity is -1 to 1)
        return (similarity + 1) / 2
    
    def save_embeddings_cache(self, embeddings: Dict[str, np.ndarray], cache_name: str = 'tool_embeddings'):
        """
        Save embeddings to disk cache
        
        Args:
            embeddings: Dict of {identifier: embedding_vector}
            cache_name: Name for cache file (without extension)
        """
        if not self.cache_dir:
            return
        
        cache_path = self.cache_dir / f"{cache_name}.npz"
        
        # Add metadata
        metadata = {
            'timestamp': datetime.utcnow().isoformat(),
            'model_name': self.model_name,
            'count': len(embeddings)
        }
        
        # Save with metadata
        np.savez_compressed(
            cache_path,
            **embeddings,
            __metadata__=np.array([str(metadata)])
        )
        
        print(f"[OK] Saved {len(embeddings)} embeddings to {cache_path}")
    
    def load_embeddings_cache(self, cache_name: str = 'tool_embeddings') -> Optional[Dict[str, np.ndarray]]:
        """
        Load embeddings from disk cache
        
        Args:
            cache_name: Name of cache file (without extension)
            
        Returns:
            Dict of embeddings or None if not found
        """
        if not self.cache_dir:
            return None
        
        cache_path = self.cache_dir / f"{cache_name}.npz"
        
        if not cache_path.exists():
            return None
        
        try:
            data = np.load(cache_path, allow_pickle=True)
            
            # Extract embeddings (skip metadata)
            embeddings = {
                key: data[key]
                for key in data.files
                if key != '__metadata__'
            }
            
            print(f"[OK] Loaded {len(embeddings)} embeddings from {cache_path}")
            return embeddings
            
        except Exception as e:
            print(f"WARN: Failed to load embeddings cache: {e}")
            return None
    
    def _get_cache_key(self, text: str) -> str:
        """Generate cache key for text"""
        return hashlib.md5(text.encode()).hexdigest()
    
    def clear_memory_cache(self):
        """Clear in-memory cache"""
        self.memory_cache.clear()
