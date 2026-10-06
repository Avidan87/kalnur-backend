"""
Tavily Search MCP Server for KAI
Provides web search capabilities to agents via JSON-RPC over stdio.
"""

from tavily import TavilyClient
import os
import sys
import json


class TavilyMCPServer:
    """MCP Server for Tavily Search"""

    def __init__(self):
        api_key = os.environ.get("TAVILY_API_KEY")
        if not api_key:
            raise ValueError("TAVILY_API_KEY environment variable is required")
        self.tavily_client = TavilyClient(api_key=api_key)

    def handle_request(self, request: dict) -> dict:
        """Handle MCP JSON-RPC requests"""
        method = request.get("method")
        params = request.get("params", {})

        if method == "tools/list":
            return self.list_tools()
        elif method == "tools/call":
            return self.call_tool(params)
        else:
            return {"error": f"Unknown method: {method}"}

    def list_tools(self) -> dict:
        """Return available tools"""
        return {
            "tools": [
                {
                    "name": "search_nigerian_nutrition",
                    "description": "Search the web for Nigerian nutrition information from credible sources",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Search query (e.g., 'iron deficiency symptoms Nigeria')"
                            },
                            "max_results": {
                                "type": "integer",
                                "description": "Maximum number of results",
                                "default": 5
                            }
                        },
                        "required": ["query"]
                    }
                },
                {
                    "name": "quick_answer",
                    "description": "Get a quick answer to a Nigerian nutrition question",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "question": {
                                "type": "string",
                                "description": "Question to answer"
                            }
                        },
                        "required": ["question"]
                    }
                }
            ]
        }

    def call_tool(self, params: dict) -> dict:
        """Execute tool call"""
        tool_name = params.get("name")
        arguments = params.get("arguments", {})

        if tool_name == "search_nigerian_nutrition":
            return self.search_nigerian_nutrition(**arguments)
        elif tool_name == "quick_answer":
            return self.quick_answer(**arguments)
        else:
            return {"error": f"Unknown tool: {tool_name}"}

    def search_nigerian_nutrition(self, query: str, max_results: int = 5) -> dict:
        """Search for Nigerian nutrition information"""
        try:
            results = self.tavily_client.search(
                query=f"{query} Nigeria Nigerian food nutrition",
                search_depth="advanced",
                max_results=max_results,
                include_domains=[
                    "who.int",
                    "ncbi.nlm.nih.gov",
                    "nih.gov",
                    "fao.org",
                    "healthline.com",
                    "medicalnewstoday.com",
                ],
                include_answer=True,
                include_raw_content=False,
            )

            # Format response
            formatted_results = {
                "answer": results.get("answer", ""),
                "sources": []
            }

            for result in results.get("results", [])[:max_results]:
                formatted_results["sources"].append({
                    "title": result.get("title"),
                    "url": result.get("url"),
                    "content": (result.get("content", "")[:300] + "...") if result.get("content") else "",
                    "score": result.get("score", 0),
                })

            return {"content": [{"type": "text", "text": json.dumps(formatted_results, indent=2)}]}

        except Exception as e:
            return {"error": str(e)}

    def quick_answer(self, question: str) -> dict:
        """Get quick answer using Tavily QnA"""
        try:
            answer = self.tavily_client.qna_search(
                query=question,
                search_depth="advanced",
            )

            return {"content": [{"type": "text", "text": answer}]}

        except Exception as e:
            return {"error": str(e)}

    def run(self):
        """Run MCP server (stdio transport)"""
        while True:
            try:
                line = sys.stdin.readline()
                if not line:
                    break

                request = json.loads(line)
                response = self.handle_request(request)

                sys.stdout.write(json.dumps(response) + '\n')
                sys.stdout.flush()

            except Exception as e:
                error_response = {"error": str(e)}
                sys.stdout.write(json.dumps(error_response) + '\n')
                sys.stdout.flush()


if __name__ == "__main__":
    server = TavilyMCPServer()
    server.run()


