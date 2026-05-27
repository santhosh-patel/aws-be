import json
import os
import asyncio
from datetime import datetime
from typing import List, Dict, Any, Optional
from bson import ObjectId

class JSONCollection:
    def __init__(self, file_path: str):
        self.file_path = file_path
        self._ensure_file()

    def _ensure_file(self):
        if not os.path.exists(self.file_path):
            os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
            with open(self.file_path, 'w') as f:
                json.dump([], f)

    def _load(self) -> List[Dict]:
        try:
            with open(self.file_path, 'r') as f:
                data = json.load(f)
                # Convert ISO strings back to datetime for internal logic if needed, 
                # but MongoDB driver usually returns datetime objects.
                # For simplicity, we'll handle datetime conversion on read/write.
                return data
        except (json.JSONDecodeError, FileNotFoundError):
            return []

    def _save(self, data: List[Dict]):
        # Convert datetime to ISO format for JSON serialization
        def serialize(obj):
            if isinstance(obj, datetime):
                return obj.isoformat()
            if isinstance(obj, ObjectId):
                return str(obj)
            return obj

        with open(self.file_path, 'w') as f:
            json.dump(data, f, default=serialize, indent=2)

    async def insert_one(self, document: Dict) -> Any:
        data = self._load()
        if "_id" not in document:
            document["_id"] = str(ObjectId())
        
        # Deep copy to avoid mutating the input dict if it's used elsewhere
        doc_to_save = document.copy()
        data.append(doc_to_save)
        self._save(data)
        
        class InsertOneResult:
            def __init__(self, inserted_id):
                self.inserted_id = inserted_id
        
        return InsertOneResult(document["_id"])

    async def find_one(self, query: Dict) -> Optional[Dict]:
        data = self._load()
        for doc in data:
            if self._matches(doc, query):
                return self._deserialize(doc)
        return None

    def find(self, query: Dict = {}):
        # Return a cursor-like object
        return JSONCursor(self, query)

    async def update_one(self, query: Dict, update: Dict) -> Any:
        data = self._load()
        modified_count = 0
        
        for doc in data:
            if self._matches(doc, query):
                if "$set" in update:
                    for k, v in update["$set"].items():
                        doc[k] = v
                    modified_count = 1
                    # In a real DB, update_one only updates the first match
                    break
        
        if modified_count > 0:
            self._save(data)
            
        class UpdateResult:
            def __init__(self, modified_count):
                self.modified_count = modified_count
        
        return UpdateResult(modified_count)

    async def delete_one(self, query: Dict) -> Any:
        data = self._load()
        initial_len = len(data)
        
        # Remove first match
        for i, doc in enumerate(data):
            if self._matches(doc, query):
                del data[i]
                break
        
        if len(data) < initial_len:
            self._save(data)
            
        class DeleteResult:
            def __init__(self, deleted_count):
                self.deleted_count = initial_len - len(data)
        
        return DeleteResult(initial_len - len(data))

    async def delete_many(self, query: Dict) -> Any:
        data = self._load()
        initial_len = len(data)
        
        new_data = [doc for doc in data if not self._matches(doc, query)]
        
        if len(new_data) < initial_len:
            self._save(new_data)
            
        class DeleteResult:
            def __init__(self, deleted_count):
                self.deleted_count = initial_len - len(new_data)
        
        return DeleteResult(initial_len - len(new_data))

    def _matches(self, doc: Dict, query: Dict) -> bool:
        for k, v in query.items():
            # Handle ObjectId lookup
            if k == "_id":
                if str(doc.get(k)) != str(v):
                    return False
            elif doc.get(k) != v:
                return False
        return True

    def _deserialize(self, doc: Dict) -> Dict:
        # Convert specific fields back to appropriate types if needed
        # For our app, we mainly need _id as string (which it is in JSON) 
        # But datetime fields might need parsing if the app expects datetime objects
        # The app expects: created_at, updated_at, timestamp as datetime objects
        
        new_doc = doc.copy()
        for field in ['created_at', 'updated_at', 'timestamp']:
            if field in new_doc and isinstance(new_doc[field], str):
                try:
                    new_doc[field] = datetime.fromisoformat(new_doc[field])
                except ValueError:
                    pass
        return new_doc


class JSONCursor:
    def __init__(self, collection, query):
        self.collection = collection
        self.query = query
        self._sort = None
        self._limit = None

    def sort(self, key, direction):
        self._sort = (key, direction)
        return self

    async def to_list(self, length):
        data = self.collection._load()
        # Filter
        results = [self.collection._deserialize(doc) for doc in data if self.collection._matches(doc, self.query)]
        
        # Sort
        if self._sort:
            key, direction = self._sort
            reverse = direction == -1
            try:
                results.sort(key=lambda x: x.get(key, ""), reverse=reverse)
            except:
                pass # varied types might fail sort
                
        # Limit
        if length is not None:
            results = results[:length]
            
        return results

class JSONDatabase:
    def __init__(self, data_dir: str):
        self.chats = JSONCollection(os.path.join(data_dir, 'chats.json'))
        self.messages = JSONCollection(os.path.join(data_dir, 'messages.json'))
        self.users = JSONCollection(os.path.join(data_dir, 'users.json'))
        self.tokens = JSONCollection(os.path.join(data_dir, 'tokens.json'))
        # Historical data collections
        self.cost_snapshots = JSONCollection(os.path.join(data_dir, 'cost_snapshots.json'))
        self.resource_snapshots = JSONCollection(os.path.join(data_dir, 'resource_snapshots.json'))
        self.insights = JSONCollection(os.path.join(data_dir, 'insights.json'))

