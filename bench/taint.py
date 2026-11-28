"""The taint search over a run's streams. Every tool input (Bash commands, WebFetch URLs, WebSearch queries, file paths)
is searched for what would show the agent the finished work:
- the issue's URL, and the fix's pull request by number (pull/N, pulls/N);
- OWNER/REPO/pull/ and OWNER/REPO/commit/;
- the fix's commit, its first seven characters or more;
- a `gh` command;
- a fetch of the project's own package or repository: a WebFetch or WebSearch naming it, or a Bash download or
  install command naming it;
- a read of the bench's own folders, where the hidden tests and the fix live on this machine.
The bare repository name is not searched: Go module paths and scoped npm names hold it, so ordinary commands would
match. A hit marks the run tainted, and the report leaves it out."""

import json
import os
import re

FETCH = re.compile(r"\b(curl|wget|pip3?\s+(install|download)|uv\s+(pip\s+install|add)|npm\s+(install|i|view|pack|info)|"
                   r"pnpm\s+(add|install|view)|yarn\s+(add|info)|cargo\s+(add|install|search|fetch)|"
                   r"go\s+(get|install|mod\s+download)|git\s+(clone|fetch|ls-remote))\b")
GH = re.compile(r"(^|[;&|(`\s])gh(\s|$)")


def terms(situation, fix_sha, folders):
    """[(name, regex)] for one situation. `folders` are the bench's own folders on this machine."""
    out = []
    p = situation.project
    if situation.issue:
        bare = re.sub(r"^https?://", "", situation.issue)
        out.append(("issue URL", re.compile(re.escape(bare))))
    if situation.pull:
        out.append(("pull request number", re.compile(rf"\bpulls?/{situation.pull}\b")))
    if p.slug:
        out.append(("pull request link", re.compile(rf"{re.escape(p.slug)}/pulls?/", re.I)))
        out.append(("commit link", re.compile(rf"{re.escape(p.slug)}/commits?/", re.I)))
    if fix_sha:
        out.append(("fix commit", re.compile(rf"\b{fix_sha[:7]}[0-9a-f]{{0,33}}\b")))
    for folder in folders:
        if folder:
            out.append(("bench folder", re.compile(re.escape(folder.rstrip("/")))))
    return out


def tool_calls(path):
    """(tool, input) for every tool call in a stream file, subagents' included."""
    with open(path, errors="replace") as f:
        for line in f:
            try:
                data = json.loads(line)
            except ValueError:
                continue
            if not isinstance(data, dict) or data.get("type") != "assistant":
                continue
            content = (data.get("message") or {}).get("content")
            for part in content if isinstance(content, list) else []:
                if isinstance(part, dict) and part.get("type") == "tool_use":
                    yield part.get("name") or "?", part.get("input") or {}


def names_project(text, p):
    """Whether text names the project's package (as a word) or its OWNER/REPO (also inside a URL)."""
    if p.package and re.search(rf"(?<![\w./-]){re.escape(p.package)}(?![\w-])", text):
        return True
    return bool(p.slug and re.search(rf"(?<![\w.-]){re.escape(p.slug)}(?![\w-])", text, re.I))


def search(paths, situation, fix_sha, folders=()):
    """The hits in the streams at `paths`: [{file, tool, term, input}]."""
    found = terms(situation, fix_sha, folders)
    p = situation.project
    hits = []
    for path in paths:
        for tool, tool_input in tool_calls(path):
            text = json.dumps(tool_input, ensure_ascii=False)
            command = tool_input.get("command", "") if isinstance(tool_input, dict) else ""
            named = []
            for name, regex in found:
                if regex.search(text):
                    named.append(name)
            if tool == "Bash" and GH.search(command):
                named.append("gh command")
            if tool in ("WebFetch", "WebSearch") and names_project(text, p):
                named.append("fetch of the project")
            elif tool == "Bash" and FETCH.search(command) and names_project(command, p):
                named.append("fetch of the project")
            for name in named:
                hits.append({"file": os.path.basename(path), "tool": tool, "term": name, "input": text[:300]})
    return hits
