# Subscription vs API Key Authentication Strategy

Type: task
Status: resolved
Blocked by: none

## Question

How will programmatic access to Claude and Gemini be authenticated given the user's web subscriptions? Can Google AI Studio API access (free tier / Google One AI Premium bundled key) and Anthropic API Console tokens be obtained and configured as environment variables (`GEMINI_API_KEY`, `ANTHROPIC_API_KEY`), or is an alternative credential bridge required?

## Answer

- **Zero Paid API Architecture**: Do not use raw pay-per-token API endpoints (`api.anthropic.com` or paid Gemini endpoints).
- **Subscription Agent Bridge**: Drive existing authenticated subscriptions via local agent session interfaces:
  1. **Claude**: Subprocess / PTY bridge invoking Claude Code CLI (`claude -p "..."` or interactive REPL stream) authenticated via the user's active Claude subscription.
  2. **Gemini**: Antigravity session bridge (using the `google-antigravity` local agent SDK or session connector) authenticated under Google Antigravity.
- **Bonus Architectural Advantage**: Built-in tool execution. Both Claude Code and Antigravity already possess battle-tested toolkits (shell execution, file read/write, git integration, web search). The voice frontend acts as an audio envelope (Wake Word + STT -> Session Prompt -> Streaming Stdout -> Piper TTS).
