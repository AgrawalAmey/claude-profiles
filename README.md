# claude-profiles

Manage multiple Claude Code profiles — credentials, skills, and memories across nodes.

## Install

```bash
# Run directly (no install needed)
uvx --from git+https://github.com/AgrawalAmey/claude-profiles claude-profiles

# Or install globally
uv tool install git+https://github.com/AgrawalAmey/claude-profiles

# Or from PyPI
uvx claude-profiles
```

## Usage

```bash
# Auto-discover profiles and symlink skills/memories
claude-profiles init

# Check profile health
claude-profiles status

# Sync credentials to a remote node
claude-profiles sync -f local:sclaude -t remote:gpu-box -v

# Sync to a Docker container
claude-profiles sync -f local:claude -t docker:abc123 -v

# Fix broken symlinks
claude-profiles link
```

## How it works

Claude Code stores config in `~/.claude/`. If you run multiple instances with different credentials (e.g., `~/.sclaude`, `~/.rclaude`), you typically want shared **skills** and **project memories** but separate **credentials** and **session state**.

`claude-profiles init` auto-discovers all `~/.{*}claude` directories and:

1. Picks `~/.claude` as the canonical source (configurable)
2. Symlinks `skills/` and `projects/` from all other profiles → canonical
3. Merges any existing content before replacing with symlinks
4. Keeps credentials, settings, history, and sessions separate per profile

## Credential sync

Supports three target types:

| Location | Syntax | Default path |
|----------|--------|-------------|
| Local profile | `local[:profile]` | `~/.{profile}` |
| SSH host | `remote:host[:profile]` | `~/.claude` |
| Docker container | `docker:container[:path]` | `/root/.claude` |

```bash
# Sync from sclaude to a remote server's rclaude profile
claude-profiles sync -f local:sclaude -t remote:gpu-node:rclaude -v
```
