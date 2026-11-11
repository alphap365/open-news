import asyncio
from pathlib import Path
import sys

from fastmcp import Client


async def main() -> None:
    async with Client(
        {
            "mcpServers": {
                "open-news": {
                    "command": sys.executable,
                    "args": [
                        "-m",
                        "open_news.mcp",
                    ],
                    "env": {
                        "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src"),
                    },
                }
            }
        }
    ) as client:
        result = await client.call_tool(
            "search_news",
            {"query": "climate policy", "country": "US", "max_results": 3},
        )
        print(result)


if __name__ == "__main__":
    asyncio.run(main())
