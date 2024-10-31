import json
import logging
from typing import Dict, List, Any

logger = logging.getLogger()

class CodeAnalysisPrompts:
    @staticmethod
    def get_analysis_prompt(file_path: str, file_content: str, repo_url: str) -> str:
        return f"""You are analyzing a code file to generate structured metadata. Analyze the following code and respond with ONLY a JSON object matching the specified structure.

File Path: {file_path}
Repository: {repo_url}

CODE TO ANALYZE:
{file_content}

Generate a JSON object with the following structure:
{{
    "code_analysis": {{
        "language": {{"name": string, "confidence": float, "reasoning": [string]}},
        "file_type": {{"type": string, "subtype": string, "confidence": float, "reasoning": [string]}},
        "primary_purpose": {{"purpose": string, "confidence": float, "reasoning": [string]}},
        "detected_patterns": [
            {{
                "name": string,
                "confidence": float,
                "reasoning": [string]
            }}
        ],
        "dependencies": {{
            "imports": [
                {{
                    "name": string,
                    "type": "internal|external",
                    "purpose": string
                }}
            ],
            "components": [string],
            "services": [string]
        }},
        "code_structure": {{
            "classes": [
                {{
                    "name": string,
                    "type": string,
                    "responsibility": string,
                    "patterns": [string]
                }}
            ],
            "functions": [
                {{
                    "name": string,
                    "purpose": string,
                    "complexity": "low|medium|high"
                }}
            ]
        }},
        "features": [string],
        "architectural_context": {{
            "layer": "presentation|business|data|infrastructure",
            "patterns": [string],
            "dependencies": [string]
        }}
    }},
    "context": {{
        "tech_stack": {{
            "languages": [string],
            "frameworks": [string],
            "tools": [string],
            "confidence": float,
            "reasoning": [string]
        }},
        "architectural_patterns": {{
            "patterns": [string],
            "confidence": float,
            "reasoning": [string]
        }},
        "business_domain": {{
            "domain": string,
            "subdomain": string,
            "confidence": float,
            "reasoning": [string]
        }},
        "project_type": {{
            "type": string,
            "confidence": float,
            "reasoning": [string]
        }}
    }},
    "search_filters": {{
        "primary_language": string,
        "file_categories": [string],
        "pattern_types": [string],
        "tech_stack": [string],
        "implementation_category": string,
        "architectural_layer": string,
        "complexity_level": string
    }}


}}"""

class CodeAnalyzer:
    def __init__(self, api_key: str):
        from anthropic import Anthropic
        self.client = Anthropic(api_key=api_key)
        self.prompts = CodeAnalysisPrompts()

    def analyze_code(self, file_path: str, file_content: str, repo_url: str) -> Dict[str, Any]:
        """Perform comprehensive code analysis using Claude"""
        try:
            logger.info("Starting code analysis with Claude-3")
            response = self.client.messages.create(
                model="claude-3-haiku-20240307",
                max_tokens=4096,
                messages=[{
                    "role": "user",
                    "content": self.prompts.get_analysis_prompt(file_path, file_content, repo_url)
                }]
            )
            
            # Added more detailed logging to track the response
            logger.info("Received response from Claude-3")
            logger.info(f"Response content: {response.content[0].text[:200]}...")  # Log start of response
            
            analysis_result = json.loads(response.content[0].text)
            return analysis_result
            
        except Exception as e:
            logger.error(f"Error in code analysis: {str(e)}")
            if hasattr(e, 'response'):
                logger.error(f"API Response: {e.response}")
            raise