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
            # Get primary code analysis
            response = self.client.completions.create(
                model="claude-3-haiku-20240307",
                max_tokens_to_sample=4096,
                prompt=self.prompts.get_analysis_prompt(file_path, file_content, repo_url)
            )
            
            analysis_result = json.loads(response.completion)
            logger.info(f"Analysis complete for {file_path}")
            logger.info(f"Analysis results: {json.dumps(analysis_result, indent=2)}")
            
            return analysis_result
            
        except Exception as e:
            logger.error(f"Error analyzing code: {str(e)}")
            raise