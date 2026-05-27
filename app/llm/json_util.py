import json


def extract_json_balanced(text: str) -> str:
    """
    Extracts the first balanced JSON object { ... } from a string.
    String-aware: correctly handles braces inside JSON string literals
    and escaped quotes within strings.
    
    Returns the JSON substring or None if no valid JSON is found.
    """
    start_idx = text.find('{')
    if start_idx == -1:
        return None
    
    depth = 0
    in_string = False
    escape_next = False
    
    for i in range(start_idx, len(text)):
        char = text[i]
        
        if escape_next:
            escape_next = False
            continue
        
        if char == '\\' and in_string:
            escape_next = True
            continue
        
        if char == '"':
            in_string = not in_string
            continue
        
        if in_string:
            continue
        
        if char == '{':
            depth += 1
        elif char == '}':
            depth -= 1
            if depth == 0:
                substring = text[start_idx:i + 1]
                try:
                    json.loads(substring)
                    return substring
                except json.JSONDecodeError:
                    # Not valid JSON despite balanced braces; keep searching
                    # Reset and look for next opening brace
                    next_start = text.find('{', i + 1)
                    if next_start == -1:
                        return None
                    # Recurse on remainder
                    return extract_json_balanced(text[next_start:])
    
    return None

