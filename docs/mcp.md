# Model Context Protocol (MCP)

Open News includes an optional FastMCP server that exposes news discovery,
article extraction, summarization, filtering, ranking, and story clustering as
tools for MCP clients.

## Install and run

Install the MCP extra and start the server:

```bash
python -m pip install "open-news-api[mcp]"
open-news-mcp
```

The server uses stdio transport by default. Keep the process under the MCP
client's control; do not start a second server manually when the client launches
it for you.

For development from this repository:

```bash
uv sync --group mcp
uv run open-news-mcp
```

## Configure an MCP client

For VS Code, add a `.vscode/mcp.json` file to your workspace:

```json
{
  "servers": {
    "open-news": {
      "command": "uvx",
      "args": [
        "--from",
        "open-news-api[mcp]",
        "open-news-mcp"
      ]
    }
  }
}
```

For local development, replace the `command` and `args` with:

```json
{
  "servers": {
    "open-news": {
      "command": "uv",
      "args": [
        "--directory",
        "${workspaceFolder}",
        "run",
        "--group",
        "mcp",
        "python",
        "-m",
        "open_news.mcp"
      ]
    }
  }
}
```

Other MCP clients use the same command and arguments in their stdio server
configuration. The module can also be started directly with
`python -m open_news.mcp` after installing the `mcp` extra.

## Available tools

| Tool | Purpose |
|---|---|
| `search_news` | Search Google News by query, country, result limit, and time window |
| `fetch_news` | Fetch current news by category or location |
| `get_article` | Extract article text and metadata from a URL |
| `search_site_news` | Search for a query scoped to one publisher domain |
| `discover_site_news` | Discover articles from a website or feed URL, preferring RSS |
| `summarize_articles` | Fetch and summarize articles from a list of URLs |
| `summarize_text_content` | Summarize text provided by the caller |
| `filter_news` | Filter article records by query, topic, and excluded terms |
| `rank_news` | Rank article records by relevance to a query |
| `cluster_news` | Group similar article records into story clusters |

Tools that receive `articles` expect the article dictionaries returned by the
news search and fetch tools. The retrieval tools make live network requests;
article and website tools should only be given URLs the user intends to access.

## Example tool calls

Search for recent results:

```json
{
  "query": "climate policy",
  "country": "US",
  "max_results": 5,
  "time_limit": "w"
}
```

Pass article records from a search or fetch result to the processing tools. For
example, filter records for a topic and then group similar stories:

```json
{
  "articles": [
    {
      "title": "New climate policy announced",
      "url": "https://example.com/climate-policy",
      "description": "A report on the latest climate legislation."
    }
  ],
  "topic": "climate"
}
```

Use the resulting records as the `articles` argument to `cluster_news` or
`rank_news`.

## Example client

The [MCP client example](../examples/mcp_client_demo.py) connects over stdio,
searches for recent news, and prints the MCP tool result. Run it from the
repository root after installing the MCP dependency group:

```bash
uv sync --group mcp
uv run python examples/mcp_client_demo.py
```

## Scope and roadmap

MCP support is an early integration. The current tools cover the main discovery
and processing workflows, but the MCP surface is not yet feature-complete; more
tools and capabilities are planned. The Python API remains the complete
interface for options not currently exposed as MCP tool arguments.
