#!/usr/bin/env python3
"""
claude-profiles — manage multiple Claude Code profiles across nodes.

Profiles share skills and project memories via symlinks while keeping
credentials, settings, and session state separate.

Usage:
    claude-profiles init                    Set up profiles and symlinks
    claude-profiles status                  Show all profiles and link health
    claude-profiles sync -f SRC -t DST      Sync credentials between locations
    claude-profiles link                    Re-create symlinks if broken
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

# ── Configuration ──────────────────────────────────────────────────────

HOME = Path.home()
CONFIG_PATH = HOME / ".claude" / "profiles.json"

# Directories/files shared across profiles (symlinked to canonical).
# Everything except identity and transient session state.
SHARED_DIRS = ["skills", "projects", "plugins", "plans"]
SHARED_FILES = ["settings.json"]

# Per-profile only (identity or session-bound, never shared)
PRIVATE = {
    ".credentials.json",  # auth tokens
    ".claude.json",       # oauthAccount, userID, per-profile state
    "history.jsonl",      # session history (large, per-profile)
    "sessions",
    "session-env",
    "debug",
    "cache",
    "backups",
    "file-history",
    "paste-cache",
    "image-cache",
    "ide",
    "shell-snapshots",
    "stats-cache.json",
    "mcp-needs-auth-cache.json",
}

CRED_FILES = [".credentials.json", ".claude.json"]


@dataclass
class Profile:
    name: str
    path: Path
    is_canonical: bool = False

    @property
    def exists(self) -> bool:
        return self.path.exists()

    @property
    def has_creds(self) -> bool:
        return (self.path / ".credentials.json").exists()


@dataclass
class Config:
    canonical: str = "claude"
    profiles: dict[str, str] = field(default_factory=dict)

    def save(self):
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(json.dumps({
            "canonical": self.canonical,
            "profiles": self.profiles,
        }, indent=2) + "\n")

    @classmethod
    def load(cls) -> "Config":
        if CONFIG_PATH.exists():
            data = json.loads(CONFIG_PATH.read_text())
            return cls(
                canonical=data.get("canonical", "claude"),
                profiles=data.get("profiles", {}),
            )
        return cls.discover()

    @classmethod
    def discover(cls) -> "Config":
        """Auto-discover profiles from ~/.claude, ~/.sclaude, ~/.rclaude, etc."""
        profiles = {}
        for p in HOME.iterdir():
            if p.name.startswith(".") and p.name.endswith("claude") and p.is_dir():
                # .claude -> "", .sclaude -> "s", .rclaude -> "r", .atclaude -> "at"
                prefix = p.name.lstrip(".").removesuffix("claude")
                name = prefix if prefix else "default"
                profiles[name] = str(p)
        return cls(canonical="default", profiles=profiles)

    def get_profiles(self) -> list[Profile]:
        result = []
        for name, path_str in self.profiles.items():
            result.append(Profile(
                name=name,
                path=Path(path_str),
                is_canonical=(name == self.canonical),
            ))
        return sorted(result, key=lambda p: (not p.is_canonical, p.name))


# ── Commands ───────────────────────────────────────────────────────────

def cmd_init(args: argparse.Namespace):
    """Set up profiles and create symlinks."""
    config = Config.discover()

    if not config.profiles:
        print("No Claude profiles found (expected ~/.claude, ~/.sclaude, etc.)")
        return 1

    print(f"Discovered {len(config.profiles)} profile(s):")
    for name, path in sorted(config.profiles.items()):
        tag = " (canonical)" if name == config.canonical else ""
        print(f"  {name}: {path}{tag}")

    canonical_path = Path(config.profiles[config.canonical])

    # Ensure shared directories exist in canonical
    for d in SHARED_DIRS:
        (canonical_path / d).mkdir(parents=True, exist_ok=True)

    # Create symlinks in non-canonical profiles
    for name, path_str in config.profiles.items():
        if name == config.canonical:
            continue
        profile_path = Path(path_str)
        profile_path.mkdir(parents=True, exist_ok=True)

        # Symlink shared directories
        for d in SHARED_DIRS:
            target = canonical_path / d
            link = profile_path / d
            _ensure_symlink(name, d, link, target, is_dir=True)

        # Symlink shared files
        for f in SHARED_FILES:
            target = canonical_path / f
            link = profile_path / f
            if not target.exists():
                continue
            _ensure_symlink(name, f, link, target, is_dir=False)

    config.save()
    print(f"\nConfig saved to {CONFIG_PATH}")
    return 0


def cmd_status(args: argparse.Namespace):
    """Show all profiles and their link health."""
    config = Config.load()
    profiles = config.get_profiles()

    if not profiles:
        print("No profiles configured. Run: claude-profiles init")
        return 1

    canonical = next(p for p in profiles if p.is_canonical)

    for p in profiles:
        tag = " *canonical*" if p.is_canonical else ""
        exists = "ok" if p.exists else "MISSING"
        creds = "ok" if p.has_creds else "no creds"
        print(f"\n{p.name}{tag}  [{exists}, {creds}]")
        print(f"  path: {p.path}")

        if not p.is_canonical:
            for item in SHARED_DIRS + SHARED_FILES:
                link = p.path / item
                if link.is_symlink():
                    target = link.resolve()
                    expected = (canonical.path / item).resolve()
                    if target == expected:
                        print(f"  {item}: -> {target}")
                    else:
                        print(f"  {item}: WRONG -> {target} (expected {expected})")
                elif link.is_dir() or link.is_file():
                    print(f"  {item}: NOT LINKED (local copy)")
                else:
                    print(f"  {item}: MISSING")

    return 0


def cmd_link(args: argparse.Namespace):
    """Re-create symlinks if broken."""
    # Just re-run init logic
    return cmd_init(args)


def cmd_sync(args: argparse.Namespace):
    """Sync credentials between locations.

    Locations:
        local[:profile]              Profile on this machine (default: claude)
        remote:host[:profile]        SSH host
        docker:container[:profile]   Docker container
    """
    src = _parse_location(args.src, mode="src")
    dst = _parse_location(args.dst, mode="dst")

    print(f"Syncing credentials: {src['desc']} -> {dst['desc']}")

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)

        # Fetch from source
        for f in CRED_FILES:
            _fetch_file(src, f, tmp)

        if not (tmp / ".credentials.json").exists():
            print("Error: .credentials.json not found at source")
            return 1

        # Push to destination
        _push_file(dst, tmp)

    if args.verify:
        print("Verifying auth...")
        _verify_auth(dst)

    print("Done.")
    return 0


# ── Location parsing (compatible with existing sync_claude_cred) ───────

def _parse_location(raw: str, mode: str) -> dict:
    """Parse location string like 'local:sclaude', 'remote:host:rclaude', 'docker:ctr'."""
    config = Config.load()
    parts = raw.split(":")

    loc = {"type": parts[0], "host": "localhost", "path": "", "desc": raw}

    if loc["type"] == "local":
        profile = parts[1] if len(parts) > 1 else ("s" if mode == "src" else "default")
        loc["path"] = _resolve_profile_path(profile, config)
        loc["desc"] = f"local ({profile})"

    elif loc["type"] == "remote":
        loc["host"] = parts[1] if len(parts) > 1 else "localhost"
        if len(parts) > 2:
            profile = parts[2]
            if profile.startswith("/") or profile.startswith("~"):
                loc["path"] = profile
            else:
                loc["path"] = f"~/.{profile}claude"
        else:
            loc["path"] = "~/.claude"
        loc["desc"] = f"remote ({loc['host']}:{loc['path']})"

    elif loc["type"] == "docker":
        loc["host"] = parts[1] if len(parts) > 1 else ""
        loc["path"] = parts[2] if len(parts) > 2 else "/root/.claude"
        loc["desc"] = f"docker ({loc['host']}:{loc['path']})"

    return loc


def _fetch_file(loc: dict, filename: str, tmpdir: Path):
    src_path = f"{loc['path']}/{filename}"
    try:
        if loc["type"] == "local":
            p = Path(src_path).expanduser()
            if p.exists():
                shutil.copy2(p, tmpdir / filename)
                print(f"  found {filename}")
        elif loc["type"] == "remote":
            subprocess.run(
                ["scp", "-q", f"{loc['host']}:{src_path}", str(tmpdir / filename)],
                check=True, capture_output=True,
            )
            print(f"  found {filename}")
        elif loc["type"] == "docker":
            subprocess.run(
                ["docker", "cp", f"{loc['host']}:{src_path}", str(tmpdir / filename)],
                check=True, capture_output=True,
            )
            print(f"  found {filename}")
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass


def _push_file(loc: dict, tmpdir: Path):
    for f in CRED_FILES:
        src = tmpdir / f
        if not src.exists():
            continue
        dst_path = f"{loc['path']}/{f}"

        if loc["type"] == "local":
            p = Path(dst_path).expanduser()
            p.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, p)
            p.chmod(0o600)
        elif loc["type"] == "remote":
            subprocess.run(
                ["ssh", loc["host"], f"mkdir -p '{loc['path']}'"],
                check=True, capture_output=True,
            )
            subprocess.run(
                ["scp", "-q", str(src), f"{loc['host']}:{dst_path}"],
                check=True, capture_output=True,
            )
            subprocess.run(
                ["ssh", loc["host"], f"chmod 600 '{dst_path}'"],
                check=True, capture_output=True,
            )
        elif loc["type"] == "docker":
            subprocess.run(
                ["docker", "exec", loc["host"], "mkdir", "-p", loc["path"]],
                check=True, capture_output=True,
            )
            subprocess.run(
                ["docker", "cp", str(src), f"{loc['host']}:{dst_path}"],
                check=True, capture_output=True,
            )
            subprocess.run(
                ["docker", "exec", loc["host"], "chmod", "600", dst_path],
                check=True, capture_output=True,
            )

    print(f"  pushed to {loc['desc']}")


def _verify_auth(loc: dict):
    cmd = f"export CLAUDE_CONFIG_DIR='{loc['path']}'; claude auth status 2>&1 || echo 'Claude CLI not found'"
    try:
        if loc["type"] == "local":
            result = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True)
        elif loc["type"] == "remote":
            result = subprocess.run(["ssh", loc["host"], cmd], capture_output=True, text=True)
        elif loc["type"] == "docker":
            result = subprocess.run(
                ["docker", "exec", loc["host"], "bash", "-c", cmd],
                capture_output=True, text=True,
            )
        else:
            return
        print(result.stdout.strip())
    except subprocess.CalledProcessError as e:
        print(f"  verify failed: {e}")


# ── Utilities ──────────────────────────────────────────────────────────

def _ensure_symlink(profile_name: str, item_name: str, link: Path, target: Path, is_dir: bool):
    """Create or fix a symlink from link -> target."""
    if link.is_symlink():
        if link.resolve() == target.resolve():
            print(f"  {profile_name}/{item_name} -> already linked")
            return
        else:
            link.unlink()
            print(f"  {profile_name}/{item_name} -> relinked (was pointing elsewhere)")

    if is_dir and link.is_dir():
        print(f"  {profile_name}/{item_name} -> merging into canonical and linking")
        _merge_dir(link, target)
        shutil.rmtree(link)
    elif link.exists():
        # For files: copy to canonical if canonical doesn't have it, then remove
        if not is_dir and not target.exists():
            shutil.copy2(link, target)
        link.unlink()

    link.symlink_to(target)
    print(f"  {profile_name}/{item_name} -> {target}")


def _resolve_profile_path(profile: str, config: Config) -> str:
    """Resolve a profile name to its directory path."""
    if profile in config.profiles:
        return config.profiles[profile]
    if profile.startswith("/") or profile.startswith("~"):
        return str(Path(profile).expanduser())
    # "s" -> "~/.sclaude", "r" -> "~/.rclaude", "default" -> "~/.claude"
    suffix = f"{profile}claude" if profile != "default" else "claude"
    return str(HOME / f".{suffix}")


def cmd_run(args: argparse.Namespace):
    """Launch claude with a specific profile."""
    config = Config.load()
    config_dir = _resolve_profile_path(args.profile, config)

    if not Path(config_dir).exists():
        print(f"Profile directory not found: {config_dir}")
        return 1

    env = {**os.environ, "CLAUDE_CONFIG_DIR": config_dir}
    claude_args = args.claude_args or []

    try:
        os.execvpe("claude", ["claude"] + claude_args, env)
    except FileNotFoundError:
        print("'claude' not found in PATH")
        return 1


def cmd_shell_init(args: argparse.Namespace):
    """Print shell aliases for each non-canonical profile.

    Usage: eval "$(claude-profiles shell-init)"
    """
    config = Config.load()
    shell = os.environ.get("SHELL", "")

    lines = []
    aliases = []
    for name, path_str in sorted(config.profiles.items()):
        if name == config.canonical:
            continue
        # Alias name: "s" -> "sclaude", "at" -> "atclaude"
        alias = f"{name}claude"
        aliases.append(alias)
        if "fish" in shell:
            lines.append(
                f"function {alias}; CLAUDE_CONFIG_DIR='{path_str}' claude $argv; end"
            )
        else:
            lines.append(
                f"alias {alias}='CLAUDE_CONFIG_DIR=\"{path_str}\" claude'"
            )

    if not lines:
        print("# No non-canonical profiles found", file=sys.stderr)
        return 0

    print("# Generated by claude-profiles shell-init")
    for line in lines:
        print(line)

    if not args.quiet:
        print(f"# Aliases: {', '.join(aliases)}", file=sys.stderr)

    return 0


def _merge_dir(src: Path, dst: Path):
    """Merge src directory contents into dst, skipping duplicates."""
    dst.mkdir(parents=True, exist_ok=True)
    for item in src.iterdir():
        target = dst / item.name
        if item.is_dir():
            if target.exists():
                _merge_dir(item, target)
            else:
                shutil.copytree(item, target)
        elif not target.exists():
            shutil.copy2(item, target)


# ── CLI ────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        prog="claude-profiles",
        description="Manage multiple Claude Code profiles across machines.\n"
                    "Share skills, memories, plugins, and settings while keeping credentials separate.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Examples:\n"
               "  claude-profiles init                              Discover and link profiles\n"
               "  claude-profiles status                            Check profile health\n"
               "  claude-profiles run s                                Launch claude as ~/.sclaude\n"
               "  claude-profiles sync -f local:s -t remote:gpu-box -v\n"
               "  eval \"$(claude-profiles shell-init)\"              Add aliases to your shell\n",
    )
    sub = parser.add_subparsers(dest="command", metavar="command")

    sub.add_parser(
        "init",
        help="Discover profiles and set up symlinks",
        description="Auto-discover ~/.{*}claude directories, symlink shared state\n"
                    "(skills, projects, plugins, plans, settings.json) to the canonical\n"
                    "profile (~/.claude), and merge any existing content first.",
    )
    sub.add_parser(
        "status",
        help="Show all profiles, link health, and credential status",
    )
    sub.add_parser(
        "link",
        help="Re-create symlinks if broken (alias for init)",
    )

    run_p = sub.add_parser(
        "run",
        help="Launch claude with a specific profile",
        description="Start claude with CLAUDE_CONFIG_DIR set to the given profile.\n"
                    "Any extra arguments are passed through to claude.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Examples:\n"
               "  claude-profiles run s\n"
               "  claude-profiles run r --model opus\n"
               "  claude-profiles run at -p 'explain this codebase'\n",
    )
    run_p.add_argument("profile", help="Profile name (e.g., s, r, at)")
    run_p.add_argument("claude_args", nargs=argparse.REMAINDER, metavar="...",
                       help="Arguments passed through to claude")

    shell_init_p = sub.add_parser(
        "shell-init",
        help="Print shell aliases (add to .zshrc/.bashrc)",
        description='Generate shell aliases so you can type "sclaude" instead of\n'
                    '"claude-profiles run sclaude".\n\n'
                    'Add to your shell rc file:\n'
                    '  eval "$(claude-profiles shell-init)"',
    )
    shell_init_p.add_argument("-q", "--quiet", action="store_true",
                              help="Suppress stderr hints")

    sync_p = sub.add_parser(
        "sync",
        help="Sync credentials between locations",
        description="Copy .credentials.json and .claude.json between profiles,\n"
                    "SSH hosts, and Docker containers.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Location syntax:\n"
               "  local[:profile]              Local profile (default src: s, dst: default)\n"
               "  remote:host[:profile]        SSH host (default path: ~/.claude)\n"
               "  docker:container[:path]      Docker container (default: /root/.claude)\n"
               "\n"
               "Profile names: s -> ~/.sclaude, r -> ~/.rclaude, default -> ~/.claude\n"
               "\n"
               "Examples:\n"
               "  claude-profiles sync -f local:s -t remote:gpu-box -v\n"
               "  claude-profiles sync -f local:default -t docker:abc123\n"
               "  claude-profiles sync -f remote:serverA -t remote:serverB\n"
               "  claude-profiles sync -f local:s -t remote:node:r\n",
    )
    sync_p.add_argument("-f", "--from", dest="src", required=True, metavar="SRC",
                        help="Source location (e.g., local:sclaude, remote:host)")
    sync_p.add_argument("-t", "--to", dest="dst", required=True, metavar="DST",
                        help="Destination location (e.g., remote:gpu-box, docker:ctr)")
    sync_p.add_argument("-v", "--verify", action="store_true",
                        help="Run 'claude auth status' on destination after sync")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return 0

    commands = {
        "init": cmd_init,
        "status": cmd_status,
        "link": cmd_link,
        "run": cmd_run,
        "shell-init": cmd_shell_init,
        "sync": cmd_sync,
    }

    return commands[args.command](args)


if __name__ == "__main__":
    sys.exit(main() or 0)
