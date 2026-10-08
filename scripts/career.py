"""Create a private workspace or compile its editable LaTeX resume. No network calls."""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
FILES = {"profile.md": "profile.md", "rules.md": "rules.md", "tracker.md": "tracker.md", "resume/resume.tex": "resume.tex"}


def workspace_path(destination: Path) -> Path:
    root = Path(destination).resolve()
    project = PROJECT.resolve()
    if root == project or (project in root.parents and not (root == project / "workspace" or project / "workspace" in root.parents)):
        raise ValueError("Personal files must go in workspace/ or a separate private directory, not public project files.")
    return root


def inside(root: Path, relative: str) -> Path:
    target = root / relative
    if root not in target.resolve().parents:
        raise ValueError(f"Path escapes private workspace: {relative}")
    return target


def initialize(destination: Path) -> list[Path]:
    root = workspace_path(destination)
    content = {}
    for relative, template in FILES.items():
        content[relative] = (PROJECT / "templates" / template).read_bytes()
        target = inside(root, relative)
        if target.exists() and not target.is_file():
            raise ValueError(f"Expected a file: {target}")
        for parent in target.parents:
            if parent == root.parent:
                break
            if parent.exists() and not parent.is_dir():
                raise ValueError(f"Expected a directory: {parent}")
    created = []
    for relative, data in content.items():
        target = inside(root, relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            with target.open("xb") as output:
                output.write(data)
            created.append(target)
        except FileExistsError:
            if not target.is_file():
                raise ValueError(f"Expected a file: {target}")
    return created


def build(destination: Path, draft: bool = False, engine: str | None = None) -> Path:
    root = workspace_path(destination)
    source = inside(root, "resume/resume.tex")
    text = source.read_text(encoding="utf-8")
    # This gate detects template fields, not the truth of candidate claims.
    if not draft and re.search(r"@@[A-Z0-9_]+@@", text):
        raise ValueError("Template fields remain. Codex must fill confirmed facts or remove unused sections; use --draft only for layout testing.")
    compiler = shutil.which(engine or "xelatex")
    if not compiler:
        raise FileNotFoundError("XeLaTeX not found. Ask Codex to check the local TeX installation; do not substitute HTML silently.")
    build_dir = inside(root, "resume/.build")
    build_dir.mkdir(parents=True, exist_ok=True)
    log = inside(root, "resume/.build/compile.log")
    output = inside(root, "resume/resume_draft.pdf" if draft else "resume/resume.pdf")
    if output.exists() and not output.is_file():
        raise ValueError(f"Expected a PDF file: {output}")
    with tempfile.TemporaryDirectory(prefix="compile-", dir=build_dir) as staging:
        command = [compiler, "-no-shell-escape", "-interaction=nonstopmode", "-halt-on-error", "-jobname=resume", f"-output-directory={staging}", source.name]
        transcript = []
        try:
            for pass_number in (1, 2):
                result = subprocess.run(command, cwd=source.parent, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=90)
                transcript.append(f"PASS {pass_number}\n{result.stdout}\n{result.stderr}")
                log.write_text("\n".join(transcript), encoding="utf-8")
                if result.returncode:
                    raise RuntimeError(f"XeLaTeX failed; previous PDF unchanged. See {log}")
            built = Path(staging) / "resume.pdf"
            if not built.is_file() or not built.read_bytes().startswith(b"%PDF-"):
                raise RuntimeError(f"Compiler produced no PDF; previous PDF unchanged. See {log}")
            os.replace(built, output)
        except (OSError, subprocess.TimeoutExpired) as error:
            transcript.append(f"BUILD ERROR: {error}")
            log.write_text("\n".join(transcript), encoding="utf-8")
            raise RuntimeError(f"Build failed; previous PDF unchanged. See {log}") from error
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    init_parser = commands.add_parser("init", help="Create only missing candidate files")
    init_parser.add_argument("workspace", nargs="?", type=Path, default=PROJECT / "workspace")
    build_parser = commands.add_parser("build", help="Compile PDF; facts and PDF layout still need review")
    build_parser.add_argument("workspace", nargs="?", type=Path, default=PROJECT / "workspace")
    build_parser.add_argument("--draft", action="store_true")
    build_parser.add_argument("--engine", help="Path/name of a local XeLaTeX executable")
    args = parser.parse_args()
    try:
        if args.command == "init":
            created = initialize(args.workspace)
            print(f"Workspace: {args.workspace.resolve()}\nCreated {len(created)} files; existing files preserved.")
        else:
            print(f"PDF compiled: {build(args.workspace, args.draft, args.engine)}\nNot yet verified: candidate facts, visual layout, PDF text extraction and target ATS parsing.")
    except (OSError, ValueError, RuntimeError) as error:
        parser.exit(1, f"{error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
