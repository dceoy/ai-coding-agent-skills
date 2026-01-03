---
name: claude-search
description: Search the web using Anthropic Claude's web search tool for up-to-date documentation, best practices, comparisons, and troubleshooting. Use when the user needs current information with citations. Requires an Anthropic API key and web search enabled.
---

# Claude Search Skill

Use Anthropic Claude's **web search tool** via the Messages API to perform **read-only web research** with citations.

## When to Use

- The user asks for current docs, best practices, or library comparisons
- The user needs up-to-date troubleshooting or security guidance
- The user requests sources, links, or citations
- The topic is time-sensitive (news, releases, versions, policies)

## Prerequisites

- `ANTHROPIC_API_KEY` is set
- Web search is enabled for the org/project in the Anthropic Console
- Use a model that supports web search (check Anthropic docs for the current list)

## Basic Usage

### Step 1: Frame the Research Query

- Be specific about the goal and scope
- Prefer official documentation and authoritative sources
- Add date constraints when recency matters

### Step 2: Call the Messages API with the Web Search Tool

```bash
curl https://api.anthropic.com/v1/messages \
  -H "x-api-key: $ANTHROPIC_API_KEY" \
  -H "anthropic-version: 2023-06-01" \
  -H "content-type: application/json" \
  -d '{
    "model": "MODEL_NAME",
    "max_tokens": 1000,
    "messages": [
      {"role": "user", "content": "Research: [QUERY]. Provide a concise answer and cite sources."}
    ],
    "tools": [
      {
        "type": "web_search_20250305",
        "name": "web_search",
        "max_uses": 3,
        "allowed_domains": ["example.com"]
      }
    ]
  }'
```

### Step 3: Present Results with Citations

- **Summary**: direct answer in 2-3 sentences
- **Key findings**: bullet points with citations
- **Sources**: list of URLs referenced

## Domain Filtering and Location

- Use `allowed_domains` or `blocked_domains` to constrain sources
- Use `user_location` to bias results toward a region when needed
- Increase `max_uses` for broader coverage (keep it minimal to reduce cost)

## Best Practices

- Prefer official docs, standards bodies, and vendor sources
- Request dates in the response for time-sensitive info
- Ask for alternative approaches if multiple options exist
- Keep the prompt explicit about citation requirements

## Error Handling

- If web search is not enabled, ask the user to enable it in the Anthropic Console
- If the model lacks web search support, switch to a supported model
- If results are thin, broaden the query or remove domain filters

## Related Skills

- `codex-search` for OpenAI Codex CLI web search
- `claude-ask` for read-only codebase understanding
- `claude-exec` for code modifications
