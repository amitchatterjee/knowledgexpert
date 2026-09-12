"""DeepAgents graph for knowledgexpert.

Phase 1 scope only (see .plans/001-2026-09-05-deepagents-modernization-plan-INPROG.md): the
knowledge-base backend constructor and prompt loading. The supervisor/rule-spec-validator/generator
subagents and the create_deep_agent() wiring land in later phases, once specification-guidelines/
content exists to ground them.
"""

from __future__ import annotations

import logging
import os
import urllib.parse

from deepagents.backends import FilesystemBackend
from deepagents.backends.protocol import BackendProtocol
from dotenv import load_dotenv

from knowledgexpert.s3_backend import S3Backend

load_dotenv()

logger = logging.getLogger(__name__)


def _get_rulegen_root() -> str:
    """Return RULEGEN_ROOT -- the current target application's <app>-rulegen/ directory.

    A local path, or an s3://<bucket>/<prefix> URI when that application's knowledge base is
    S3-backed. No default: this env var is what "which target application" means at runtime (see
    the plan's "Configuration approach"), so an unset value is a configuration error, not something
    to guess at.
    """
    try:
        return os.environ["RULEGEN_ROOT"]
    except KeyError as e:
        raise RuntimeError(
            "RULEGEN_ROOT is not set -- point it at the target application's <app>-rulegen/ "
            "directory (e.g. knowledgenet-examples/autoins-rulegen)."
        ) from e


def _create_knowledge_backend() -> BackendProtocol:
    """Create the backend for the knowledge base at RULEGEN_ROOT/knowledge.

    Dispatches on RULEGEN_ROOT's URI scheme: `s3://<bucket>/<prefix>` selects an S3-compatible
    object store; `file://` or a bare path (no scheme) selects the local filesystem. Mirrors
    carqna-agent's `_create_insurance_backend()`, generalized from a fixed docs corpus to this
    tool's per-application `knowledge/` subpath.

    Returns:
        A BackendProtocol implementation ready to mount at /knowledge/ in a CompositeBackend.

    Raises:
        FileNotFoundError: If the local knowledge/ directory doesn't exist.
    """
    rulegen_root = _get_rulegen_root()
    parsed = urllib.parse.urlsplit(rulegen_root)

    if parsed.scheme == "s3":
        # s3://<bucket>/<prefix...> -- bucket from netloc, everything after the first "/" is an
        # optional key prefix within that bucket, with "knowledge" appended as the fixed subpath.
        bucket = parsed.netloc
        prefix = "/".join(p for p in (parsed.path.strip("/"), "knowledge") if p)
        logger.info(f"Initialized S3 knowledge backend: bucket={bucket} prefix={prefix!r}")
        return S3Backend(
            bucket=bucket,
            prefix=prefix,
            endpoint_url=os.environ["S3_ENDPOINT_URL"],
            access_key=os.environ["S3_ACCESS_KEY_ID"],
            secret_key=os.environ["S3_SECRET_ACCESS_KEY"],
            region=os.getenv("S3_REGION", "us-east-1"),
        )

    # "file:///abs/path" or a bare path (no scheme, e.g. "~/foo" or "./autoins-rulegen") -- "~"
    # only expands in the bare-path form: a file:// URI's path is taken literally per normal URI
    # semantics, so use an absolute file:// path, not file://~/....
    root_path = os.path.expanduser(parsed.path if parsed.scheme == "file" else rulegen_root)
    knowledge_dir = os.path.join(root_path, "knowledge")
    if not os.path.exists(knowledge_dir):
        raise FileNotFoundError(f"Knowledge base not found: {knowledge_dir}")

    logger.info(f"Initialized filesystem knowledge backend: root={knowledge_dir}")
    return FilesystemBackend(root_dir=knowledge_dir, virtual_mode=True)


def _load_prompt_from_file(filename: str) -> str:
    """Load a prompt from a markdown file under RULEGEN_ROOT/prompts.

    Args:
        filename: Name of the prompt file (e.g. "supervisor.md").

    Returns:
        The contents of the prompt file, stripped of leading/trailing whitespace.

    Raises:
        FileNotFoundError: If the prompt file is not found.

    Note: unlike the knowledge base, prompts are always read from local disk, even when
    RULEGEN_ROOT points at an s3:// URI -- prompts are small, human-authored files, and
    S3-backed prompt loading isn't designed/needed yet. Revisit if that changes.
    """
    rulegen_root = _get_rulegen_root()
    prompts_dir = os.path.join(os.path.expanduser(rulegen_root), "prompts")
    prompt_path = os.path.join(prompts_dir, filename)

    if not os.path.exists(prompt_path):
        raise FileNotFoundError(
            f"Prompt file not found at {prompt_path}. Set RULEGEN_ROOT to the target "
            f"application's <app>-rulegen/ directory."
        )

    with open(prompt_path) as f:
        return f.read().strip()
