# Web Search Integration

**When:** User asks about current docs, latest API changes, version compatibility, or "look up" / "search for" / "find" something.

**Detection signals:**
- "search", "look up", "find", "latest", "current version", "docs", "documentation"
- "how to", "best practice" + unfamiliar technology
- Korean: "검색", "찾아", "최신", "현재", "문서", "공식"

**When to suggest web_search:**
- Unknown API or library version compatibility
- Current best practices for a rapidly evolving tool
- Error messages that don't match known patterns
- Checking if a dependency is maintained/deprecated

**How to use:**
- `/OAL:escalate codex "search for [topic] and summarize findings"`
- Direct web_search tool if available in the environment
- Use `web_search` first for discovery, then use `chrome-devtools` MCP to validate findings on live pages when browser verification is needed
- Check package registry (npm, PyPI) for version info

**When NOT to search:**
- Well-known, stable patterns (basic SQL, HTML, CSS fundamentals)
- Information already in .oal/knowledge/
- When the user hasn't asked and you already know the answer
