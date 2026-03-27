# claude-profiles

Manage multiple Claude Code profiles across machines. Share skills, memories, plugins, and settings while keeping credentials separate per profile.

## Install

```bash
uvx claude-profiles          # run directly
uv tool install claude-profiles  # or install as a tool
```

## Quick start

```bash
claude-profiles init      # discover profiles, set up symlinks
claude-profiles status    # check everything looks right
```

If you have `~/.claude`, `~/.sclaude`, `~/.rclaude` (or any `~/.{x}claude`), they now share skills, project memories, plugins, plans, and settings.

## Profile names

The `claude` suffix is implicit — profile names are just the prefix:

| Directory | Profile | Alias |
|-----------|---------|-------|
| `~/.claude` | `default` (canonical) | `claude` |
| `~/.sclaude` | `s` | `sclaude` |
| `~/.rclaude` | `r` | `rclaude` |

## Launching profiles

```bash
# One-off
claude-profiles run s
claude-profiles run r --model opus

# Or add aliases to your shell rc:
eval "$(claude-profiles shell-init)"
# Now just type:
sclaude
rclaude -p 'explain this'
```

## What's shared vs separate

| Shared (symlinked to ~/.claude) | Per-profile |
|---------------------------------|-------------|
| `skills/` — custom slash commands | `.credentials.json` — auth tokens |
| `projects/` — project memories | `.claude.json` — account identity |
| `plugins/` — installed plugins | `history.jsonl` — session history |
| `plans/` — saved plans | `sessions/`, `cache/`, `debug/` |
| `settings.json` — preferences | |

## Credential sync

Push credentials between local profiles, SSH hosts, and Docker containers.

```bash
claude-profiles sync -f local:s -t remote:gpu-box -v
claude-profiles sync -f local:default -t docker:abc123
claude-profiles sync -f remote:serverA -t remote:serverB
claude-profiles sync -f local:s -t remote:node:r
```

### Location syntax

```
local[:profile]              Local profile (default src: s, dst: default)
remote:host[:profile]        SSH host (default: ~/.claude)
docker:container[:path]      Docker container (default: /root/.claude)
```

## Commands

| Command | Description |
|---------|-------------|
| `init` | Discover profiles, create symlinks, merge existing content |
| `status` | Show profiles, link health, credential status |
| `run <profile> [args...]` | Launch claude with a profile |
| `shell-init` | Print shell aliases for `.zshrc`/`.bashrc` |
| `link` | Re-create symlinks if broken |
| `sync -f SRC -t DST [-v]` | Sync credentials between locations |
