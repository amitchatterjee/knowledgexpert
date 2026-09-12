"""S3-compatible backend for the DeepAgents virtual filesystem.

Talks to any S3-compatible object store (e.g. RustFS) via `boto3`. Copied
near-verbatim from `carqna-agent/src/agent/s3_backend.py` -- see that
project's `.plans/008-2026-08-15-s3-compatible-backend-plan-DONE.md` for
the full design rationale: `read`/`write`/`edit` are modeled on
`FilesystemBackend`'s single-object CRUD; `ls`/`grep`/`glob` are modeled
on `StateBackend`'s flat key-value-store approach, reusing the same
shared helpers both backends use.
"""

from __future__ import annotations

import base64
import logging
from collections.abc import Iterator
from datetime import UTC
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mypy_boto3_s3.type_defs import ObjectTypeDef

import boto3
from botocore.client import Config as BotoConfig
from botocore.exceptions import BotoCoreError, ClientError
from deepagents.backends.protocol import (
    BackendProtocol,
    EditResult,
    FileData,
    FileInfo,
    GlobResult,
    GrepResult,
    LsResult,
    ReadResult,
    WriteResult,
)
from deepagents.backends.utils import (
    _get_backend_read_file_type,
    _glob_search_files,
    check_empty_content,
    create_file_data,
    grep_matches_from_files,
    perform_string_replacement,
    slice_read_response,
)

logger = logging.getLogger(__name__)

_NOT_FOUND_CODES = {"NoSuchKey", "404", "NotFound"}


class S3Backend(BackendProtocol):
    """Backend that stores files as objects in an S3-compatible bucket.

    Not sandboxed and not access-controlled by itself -- the same
    `FilesystemPermission`-based enforcement DeepAgents applies to any other
    backend (a middleware-level, backend-agnostic concern) is what restricts
    what an agent can do with it.
    """

    def __init__(
        self,
        bucket: str,
        prefix: str = "",
        endpoint_url: str | None = None,
        access_key: str | None = None,
        secret_key: str | None = None,
        region: str = "us-east-1",
    ) -> None:
        """Initialize the S3 backend.

        Args:
            bucket: Name of the S3-compatible bucket to store files in.
            prefix: Optional key prefix within the bucket, so one bucket can
                host multiple logical roots. May be empty.
            endpoint_url: S3-compatible endpoint (e.g. RustFS's
                `http://localhost:9000`). `None` uses AWS's default endpoint.
            access_key: Access key ID.
            secret_key: Secret access key.
            region: Region name. Self-hosted stores generally ignore this but
                `boto3` requires some value.
        """
        self.bucket = bucket
        self.prefix = prefix.strip("/")
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
            # Self-hosted S3-compatible stores (RustFS, MinIO, ...) generally
            # don't do virtual-hosted-style bucket DNS.
            config=BotoConfig(s3={"addressing_style": "path"}),
        )

    def _key_for(self, path: str) -> str:
        """Map a virtual DeepAgents path (e.g. `/foo.md`) to an S3 key."""
        rel = path.lstrip("/")
        return f"{self.prefix}/{rel}" if self.prefix else rel

    def _path_for(self, key: str) -> str:
        """Map an S3 key back to a virtual DeepAgents path."""
        if self.prefix:
            key_prefix = self.prefix + "/"
            if key.startswith(key_prefix):
                key = key[len(key_prefix):]
            elif key == self.prefix:
                key = ""
        return "/" + key

    def _dir_key_prefix(self, path: str) -> str:
        """Map a virtual directory path to the S3 key prefix listing its contents."""
        rel = path.strip("/")
        base = f"{self.prefix}/{rel}" if self.prefix and rel else self.prefix or rel
        return f"{base}/" if base else ""

    def _not_found(self, error: ClientError) -> bool:
        code = error.response.get("Error", {}).get("Code")
        return code in _NOT_FOUND_CODES

    def ls(self, path: str) -> LsResult:
        """List entries directly under `path` (non-recursive)."""
        dir_prefix = self._dir_key_prefix(path)
        entries: list[FileInfo] = []
        try:
            paginator = self._client.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=self.bucket, Prefix=dir_prefix, Delimiter="/"):
                for common_prefix in page.get("CommonPrefixes", []):
                    entries.append(
                        FileInfo(path=self._path_for(common_prefix["Prefix"]), is_dir=True, size=0, modified_at="")
                    )
                for obj in page.get("Contents", []):
                    key = obj["Key"]
                    if key == dir_prefix:
                        # Zero-byte directory-marker object, not a real file.
                        continue
                    entries.append(
                        FileInfo(
                            path=self._path_for(key),
                            is_dir=False,
                            size=int(obj["Size"]),
                            modified_at=obj["LastModified"].isoformat(),
                        )
                    )
        except (ClientError, BotoCoreError) as e:
            return LsResult(error=f"Cannot list '{path}': {e}")
        entries.sort(key=lambda entry: entry.get("path", ""))
        return LsResult(entries=entries)

    def read(self, file_path: str, offset: int = 0, limit: int = 2000) -> ReadResult:
        """Read file content for the requested line range."""
        key = self._key_for(file_path)
        try:
            obj = self._client.get_object(Bucket=self.bucket, Key=key)
            raw = obj["Body"].read()
        except ClientError as e:
            if self._not_found(e):
                return ReadResult(error=f"File '{file_path}' not found")
            return ReadResult(error=f"Error reading file '{file_path}': {e}")
        except BotoCoreError as e:
            return ReadResult(error=f"Error reading file '{file_path}': {e}")

        if _get_backend_read_file_type(file_path) != "text":
            encoded = base64.standard_b64encode(raw).decode("ascii")
            return ReadResult(file_data=FileData(content=encoded, encoding="base64"))

        try:
            content = raw.decode("utf-8")
        except UnicodeDecodeError as e:
            return ReadResult(error=f"Error reading file '{file_path}': {e}")

        empty_msg = check_empty_content(content)
        if empty_msg:
            return ReadResult(file_data=FileData(content=empty_msg, encoding="utf-8"))
        return slice_read_response(FileData(content=content, encoding="utf-8"), offset, limit)

    def write(self, file_path: str, content: str) -> WriteResult:
        """Write content to a file, creating it or overwriting it if it already exists.

        Matches `FilesystemBackend`'s current overwrite semantics (create-or-
        overwrite unconditionally) so swapping backends doesn't change tool
        behavior.
        """
        key = self._key_for(file_path)
        try:
            self._client.put_object(Bucket=self.bucket, Key=key, Body=content.encode("utf-8"))
        except (ClientError, BotoCoreError) as e:
            return WriteResult(error=f"Error writing file '{file_path}': {e}")
        return WriteResult(path=file_path)

    def edit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> EditResult:
        """Perform exact string replacements in an existing file."""
        key = self._key_for(file_path)
        try:
            obj = self._client.get_object(Bucket=self.bucket, Key=key)
            raw = obj["Body"].read()
        except ClientError as e:
            if self._not_found(e):
                return EditResult(error=f"Error: File '{file_path}' not found")
            return EditResult(error=f"Error editing file '{file_path}': {e}")
        except BotoCoreError as e:
            return EditResult(error=f"Error editing file '{file_path}': {e}")

        try:
            content = raw.decode("utf-8")
        except UnicodeDecodeError as e:
            return EditResult(error=f"Error editing file '{file_path}': {e}")

        old_string = old_string.replace("\r\n", "\n").replace("\r", "\n")
        new_string = new_string.replace("\r\n", "\n").replace("\r", "\n")
        result = perform_string_replacement(content, old_string, new_string, replace_all)
        if isinstance(result, str):
            return EditResult(error=result)

        new_content, occurrences = result
        try:
            self._client.put_object(Bucket=self.bucket, Key=key, Body=new_content.encode("utf-8"))
        except (ClientError, BotoCoreError) as e:
            return EditResult(error=f"Error editing file '{file_path}': {e}")
        return EditResult(path=file_path, occurrences=int(occurrences))

    def grep(
        self,
        pattern: str,
        path: str | None = None,
        glob: str | None = None,
        *,
        max_count: int | None = None,
    ) -> GrepResult:
        """Search file content for a literal text pattern.

        Downloads every object under this backend's root to search its
        content -- acceptable for a small knowledge-base corpus, but a known
        cost if this backend is later pointed at something much larger.
        """
        try:
            files = self._read_all_file_contents()
        except (ClientError, BotoCoreError) as e:
            return GrepResult(error=f"Error searching for '{pattern}': {e}")
        return grep_matches_from_files(files, pattern, path if path is not None else "/", glob, max_count=max_count)

    def glob(self, pattern: str, path: str | None = None) -> GlobResult:
        """Find files matching a glob pattern.

        Only lists object metadata (key + last-modified) rather than
        downloading content, since glob matches on filename, not content.
        """
        try:
            files, sizes = self._read_all_file_metadata()
        except (ClientError, BotoCoreError) as e:
            return GlobResult(error=f"Error searching for '{pattern}': {e}")

        result = _glob_search_files(files, pattern, path)
        if result == "No files found":
            return GlobResult(matches=[])

        matches: list[FileInfo] = [
            FileInfo(
                path=file_path,
                is_dir=False,
                size=sizes.get(file_path, 0),
                modified_at=files[file_path]["modified_at"],
            )
            for file_path in result.split("\n")
        ]
        return GlobResult(matches=matches)

    def _iter_all_objects(self) -> Iterator[ObjectTypeDef]:
        """Iterate every object under this backend's root prefix."""
        prefix = f"{self.prefix}/" if self.prefix else ""
        paginator = self._client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
            yield from page.get("Contents", [])

    def _read_all_file_contents(self) -> dict[str, FileData]:
        """Download every object under this backend's root, for `grep`.

        Objects that can't be decoded as UTF-8 text (or fail to download) are
        skipped rather than erroring the whole search, matching
        `FilesystemBackend`'s grep, which skips unreadable files too.
        """
        files: dict[str, FileData] = {}
        for obj in self._iter_all_objects():
            key = obj["Key"]
            if key.endswith("/"):
                continue  # Directory-marker object, not a real file.
            try:
                body = self._client.get_object(Bucket=self.bucket, Key=key)["Body"].read()
                content = body.decode("utf-8")
            except (ClientError, BotoCoreError, UnicodeDecodeError):
                logger.warning("Skipping unreadable object during grep: %s", key)
                continue
            files[self._path_for(key)] = create_file_data(content)
        return files

    def _read_all_file_metadata(self) -> tuple[dict[str, FileData], dict[str, int]]:
        """List every object under this backend's root, for `glob`.

        No content is downloaded -- glob matches on filename/path, so only
        `modified_at` (for `_glob_search_files`'s sort) and `size` are needed.
        """
        files: dict[str, FileData] = {}
        sizes: dict[str, int] = {}
        for obj in self._iter_all_objects():
            key = obj["Key"]
            if key.endswith("/"):
                continue
            vpath = self._path_for(key)
            modified_at_iso = obj["LastModified"].astimezone(UTC).isoformat()
            files[vpath] = FileData(content="", encoding="utf-8", modified_at=modified_at_iso)
            sizes[vpath] = int(obj["Size"])
        return files, sizes
