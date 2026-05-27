"""
Prompt Library — Structured responses for slash commands and greeting
Provides clean, structured JSON payloads for /help, /tools, /about, and greeting.
"""

GREETING_RESPONSE = {
    "type": "GREETING",
    "title": "Hey there!",
    "message": "I'm your friendly DevOps sidekick for AWS — think of me as the teammate who always knows what's happening in your cloud. I can dig into costs, list resources, pull metrics, and search logs. Everything's read-only, so your environment stays untouched. What shall we look at first?",
    "capabilities": [],
    "quick_commands": [
        {"command": "/help", "label": "See all commands"},
        {"command": "/tools", "label": "Available tools"},
        {"command": "/about", "label": "About this agent"}
    ],
    "suggestions": [
        "What's my AWS cost this month?",
        "List all EC2 instances",
        "Show cost breakdown by service for last 30 days",
        "What CloudWatch metrics are available for EC2?"
    ]
}

SOCIAL_REPLIES = [
    "Hey! Your friendly cloud engineer reporting for duty. Want to check costs, peek at resources, or dive into some metrics?",
    "Hi there! I've got eyes on your AWS environment — just say the word and I'll pull up whatever you need. Costs, instances, logs, you name it!",
    "Hello! Ready to crunch some cloud numbers. What's on your mind — costs, resources, or something else entirely?",
    "Hey! Think of me as your AWS command center. I can check your spend, list what's running, pull CloudWatch metrics — what sounds useful right now?",
    "Hi! I'm your go-to for all things AWS observability. Fire away — I love a good cloud question!",
]

HELP_RESPONSE = {
    "type": "SLASH_COMMAND",
    "command": "/help",
    "title": "Help & Commands",
    "sections": [
        {
            "heading": "Natural Language Queries",
            "items": [
                {"label": "Cost Queries", "examples": ["What's my AWS cost today?", "Show cost breakdown by service", "Compare costs month over month"]},
                {"label": "Resource Queries", "examples": ["List all EC2 instances", "Show S3 buckets", "How many Lambda functions do I have?"]},
                {"label": "Metrics & Logs", "examples": ["Show CPU utilization for EC2", "Search CloudWatch logs for errors", "What metrics are available?"]},
            ]
        },
        {
            "heading": "Slash Commands",
            "items": [
                {"label": "/help", "description": "Show this help guide"},
                {"label": "/tools", "description": "List all available AWS tools"},
                {"label": "/about", "description": "Learn about this agent"},
            ]
        },
        {
            "heading": "Tips",
            "items": [
                {"label": "Be specific", "description": "Include time ranges (e.g., 'last 7 days') and service names for best results"},
                {"label": "Follow up", "description": "Ask follow-up questions — I remember our conversation context"},
                {"label": "See all tools", "description": "Use /tools to see all available data sources"},
            ]
        }
    ]
}


def build_tools_response_from_catalog(tools: list) -> dict:
    """
    Build /tools response from registry catalog (list of dicts with name, description).
    Groups tools by domain; same JSON shape as TOOLS_RESPONSE for frontend.
    """
    sections_map = {
        "Cost & Billing": [],
        "Account": [],
        "Compute & Infrastructure": [],
        "Storage & Data": [],
        "Organization": [],
        "Logs & Monitoring": [],
    }
    for t in tools:
        name = t.get("name", "")
        desc = t.get("description", "") or ""
        item = {"label": name, "description": desc}
        if "cost" in name.lower():
            sections_map["Cost & Billing"].append(item)
        elif any(x in name for x in ["caller_identity", "account_alias", "enabled_regions", "account_summary"]):
            sections_map["Account"].append(item)
        elif any(x in name for x in ["list_ec2", "list_lambda", "list_eks", "list_load_balancers", "list_nat"]):
            sections_map["Compute & Infrastructure"].append(item)
        elif any(x in name for x in ["list_s3", "list_rds"]):
            sections_map["Storage & Data"].append(item)
        elif "organization" in name.lower():
            sections_map["Organization"].append(item)
        elif "log" in name.lower() or "cloudwatch" in name.lower():
            sections_map["Logs & Monitoring"].append(item)
        else:
            sections_map["Compute & Infrastructure"].append(item)
    sections = [
        {"heading": k, "items": v}
        for k, v in sections_map.items()
        if v
    ]
    return {
        "type": "SLASH_COMMAND",
        "command": "/tools",
        "title": "Available AWS Tools",
        "sections": sections,
    }


TOOLS_RESPONSE = {
    "type": "SLASH_COMMAND",
    "command": "/tools",
    "title": "Available AWS Tools",
    "sections": [
        {
            "heading": "Cost & Billing",
            "items": [
                {"label": "aws_get_cost_and_usage", "description": "Retrieve cost data for a date range, grouped by service or usage type"},
                {"label": "aws_get_cost_forecast", "description": "Forecast upcoming AWS spending based on historical data"},
            ]
        },
        {
            "heading": "Compute & Infrastructure",
            "items": [
                {"label": "aws_ec2_describe_instances", "description": "List and describe all EC2 instances with status, type, and tags"},
                {"label": "aws_lambda_list_functions", "description": "List all Lambda functions with runtime, memory, and timeout info"},
                {"label": "aws_ecs_list_clusters", "description": "List ECS clusters and their services"},
            ]
        },
        {
            "heading": "Storage & Data",
            "items": [
                {"label": "aws_s3_list_buckets", "description": "List S3 buckets with creation date and region"},
                {"label": "aws_rds_describe_instances", "description": "List RDS database instances with engine and status"},
                {"label": "aws_dynamodb_list_tables", "description": "List DynamoDB tables"},
            ]
        },
        {
            "heading": "Monitoring & Observability",
            "items": [
                {"label": "aws_cloudwatch_get_metrics", "description": "Fetch CloudWatch metrics — CPU, network, disk, custom metrics"},
                {"label": "aws_cloudwatch_get_log_events", "description": "Retrieve log events from CloudWatch Log Groups"},
                {"label": "aws_cloudwatch_list_metrics", "description": "List available CloudWatch metrics for a namespace"},
            ]
        }
    ]
}

ABOUT_RESPONSE = {
    "type": "SLASH_COMMAND",
    "command": "/about",
    "title": "About Enculture AWS Agent",
    "sections": [
        {
            "heading": "What I Am",
            "items": [
                {"label": "Purpose", "description": "AI-powered AWS observability agent built for real-time cloud insights"},
                {"label": "Architecture", "description": "MCP (Model Context Protocol) based — routes queries through intent planning → tool execution → structured response"},
                {"label": "Access", "description": "Strictly read-only. I cannot modify, create, or delete any AWS resources"},
            ]
        },
        {
            "heading": "Technology Stack",
            "items": [
                {"label": "Backend", "description": "Python, FastAPI, OpenAI GPT-4o for intent understanding"},
                {"label": "Frontend", "description": "React + Vite with Enculture design system"},
                {"label": "Data", "description": "MongoDB for chat persistence, AWS SDK (Boto3) for live data"},
            ]
        },
        {
            "heading": "Safety Guarantees",
            "items": [
                {"label": "Read-Only", "description": "All AWS API calls are describe/list/get only — no mutations ever"},
                {"label": "RBAC", "description": "Role-based access control with audit logging"},
                {"label": "Input Validation", "description": "All queries pass through strict input validation and sanitization"},
            ]
        }
    ]
}
