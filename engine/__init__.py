"""Agent-independent orchestration engine.

Loads agent specs from YAML, resolves tools by name, invokes the Anthropic SDK
with rate limits + budget accounting, and halts cleanly on breach.
"""
