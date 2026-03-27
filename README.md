# claude-profiles

Manage multiple Claude Code profiles across machines. Share skills, memories, plugins, and settings while keeping credentials separate.

```bash
uvx claude-profiles create r                        # new profile -> ~/.rclaude
uvx claude-profiles create work --copy-creds-from s  # with credentials
uvx claude-profiles init                             # or discover existing ones
uvx claude-profiles status                           # check health
```

## Profile names

The `claude` suffix is implicit — profiles are just the prefix:

| Directory | Profile | Alias |
|-----------|---------|-------|
| `~/.claude` | `default` (canonical) | `claude` |
| `~/.sclaude` | `s` | `sclaude` |
| `~/.rclaude` | `r` | `rclaude` |

## Launching profiles

```bash
uvx claude-profiles run s
uvx claude-profiles run r --model opus

# Or add aliases to your shell rc:
eval "$(uvx claude-profiles shell-init)"
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
uvx claude-profiles sync -f local:s -t remote:gpu-box -v
uvx claude-profiles sync -f local:default -t docker:abc123
uvx claude-profiles sync -f remote:serverA -t remote:serverB
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
| `create <name> [--copy-creds-from]` | Create a new profile with symlinks |
| `init` | Discover existing profiles, set up symlinks |
| `status` | Show profiles, link health, credential status |
| `run <profile> [args...]` | Launch claude with a profile |
| `shell-init` | Print shell aliases for `.zshrc`/`.bashrc` |
| `link` | Re-create symlinks if broken |
| `sync -f SRC -t DST [-v]` | Sync credentials between locations |
