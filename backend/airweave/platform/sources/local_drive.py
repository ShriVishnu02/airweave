"""Local Drive source — indexes files from a local filesystem directory."""

from __future__ import annotations

import asyncio
import mimetypes
import os
from datetime import datetime, timezone
from typing import AsyncGenerator

from airweave.core.logging import ContextualLogger
from airweave.domains.browse_tree.types import NodeSelectionData
from airweave.domains.sources.token_providers.protocol import SourceAuthProvider
from airweave.domains.storage.file_service import FileService
from airweave.domains.syncs.cursors.cursor import SyncCursor
from airweave.platform.configs.auth import LocalDriveAuthConfig
from airweave.platform.configs.config import LocalDriveConfig
from airweave.platform.decorators import source
from airweave.platform.entities._base import BaseEntity
from airweave.platform.entities.local_drive import LocalDriveFileEntity, LocalDriveFolderEntity
from airweave.platform.http_client.airweave_client import AirweaveHttpClient
from airweave.platform.sources._base import BaseSource
from airweave.schemas.source_connection import AuthenticationMethod


@source(
    name="Local Drive",
    short_name="local_drive",
    auth_methods=[AuthenticationMethod.DIRECT],
    auth_config_class=LocalDriveAuthConfig,
    config_class=LocalDriveConfig,
    labels=["Storage", "Local"],
    internal=True,
)
class LocalDriveSource(BaseSource):
    """Source that recursively indexes files from a local filesystem directory."""

    def __init__(
        self,
        *,
        auth: SourceAuthProvider,
        logger: ContextualLogger,
        http_client: AirweaveHttpClient,
    ) -> None:
        """Initialize LocalDriveSource."""
        super().__init__(auth=auth, logger=logger, http_client=http_client)
        self.root_path: str = ""
        self.extensions: list[str] = []
        self.max_file_size_mb: float = 0.0
        self.follow_symlinks: bool = False

    @classmethod
    async def create(
        cls,
        *,
        auth: SourceAuthProvider,
        logger: ContextualLogger,
        http_client: AirweaveHttpClient,
        config: LocalDriveConfig,
    ) -> "LocalDriveSource":
        """Create and configure a LocalDriveSource instance."""
        instance = cls(auth=auth, logger=logger, http_client=http_client)
        if config:
            instance.root_path = config.root_path
            instance.extensions = [e.lower() for e in (config.extensions or [])]
            instance.max_file_size_mb = config.max_file_size_mb or 0.0
            instance.follow_symlinks = config.follow_symlinks
        return instance

    # Validate — abstract in BaseSource
    async def validate(self) -> None:
        """Validate that root_path is a readable directory."""
        if not self.root_path:
            raise ValueError("root_path is not configured.")
        if not os.path.isdir(self.root_path):
            raise ValueError(f"root_path '{self.root_path}' does not exist or is not a directory.")
        try:
            os.listdir(self.root_path)
        except PermissionError as e:
            raise ValueError(f"root_path '{self.root_path}' is not readable: {e}") from e


def _make_file_entity(
    self,
    fpath: str,
    real_root: str,
    stat: os.stat_result,
) -> LocalDriveFileEntity | None:
    """Build a LocalDriveFileEntity from path and stat, or None to skip."""
    real_fpath = os.path.realpath(fpath)
    if not real_fpath.startswith(real_root + os.sep):
        self.logger.warning(f"Skipping path outside root (symlink escape?): {fpath}")
        return None

    size = stat.st_size
    if self.max_file_size_mb and size > self.max_file_size_mb * 1024 * 1024:
        self.logger.warning(f"Skipping large file: {fpath} ({size:,} bytes)")
        return None

    fname = os.path.basename(fpath)
    ext = os.path.splitext(fname)[1].lower()
    mime_type, _ = mimetypes.guess_type(fpath)

    try:
        modified_at = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
    except (OSError, ValueError):
        modified_at = None

    try:
        ctime_val = getattr(stat, "st_birthtime", stat.st_ctime)
        created_at_ts = datetime.fromtimestamp(ctime_val, tz=timezone.utc)
    except (OSError, ValueError):
        created_at_ts = None

    return LocalDriveFileEntity(
        file_id=real_fpath,
        file_name=fname,
        file_path=fpath,
        extension=ext,
        size_bytes=size,
        modified_at=modified_at,
        created_at_ts=created_at_ts,
        mime_type=mime_type,
        relative_path=os.path.relpath(fpath, real_root),
        breadcrumbs=[],
    )


# Generate entities
async def generate_entities(
    self,
    *,
    cursor: SyncCursor | None = None,
    files: FileService | None = None,
    node_selections: list[NodeSelectionData] | None = None,
) -> AsyncGenerator[BaseEntity, None]:
    """Walk root directory and yield folder + file entities."""
    real_root = os.path.realpath(self.root_path)
    loop = asyncio.get_event_loop()

    def _walk_files() -> list[str]:
        """Blocking walk — runs in thread pool executor."""
        results: list[str] = []
        for dir_root, dirs, filenames in os.walk(real_root, followlinks=self.follow_symlinks):
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            for fname in filenames:
                if fname.startswith("."):
                    continue
                ext = os.path.splitext(fname)[1].lower()
                if self.extensions and ext not in self.extensions:
                    continue
                results.append(os.path.join(dir_root, fname))
        return results

    file_paths = await loop.run_in_executor(None, _walk_files)

    self.logger.info(f"LocalDrive: discovered {len(file_paths):,} files under '{real_root}'")

    # Yield root folder entity first
    yield LocalDriveFolderEntity(
        folder_path=real_root,
        folder_name=os.path.basename(real_root) or real_root,
        parent_path=os.path.dirname(real_root) or None,
        breadcrumbs=[],
    )

    # Yield file entities
    total = 0
    for fpath in file_paths:
        try:
            stat = await loop.run_in_executor(None, os.stat, fpath)
        except OSError as e:
            self.logger.warning(f"Cannot stat file '{fpath}': {e}")
            continue

        entity = self._make_file_entity(fpath, real_root, stat)
        if entity is None:
            continue

        yield entity
        total += 1
        if total % 10_000 == 0:
            self.logger.info(f"LocalDrive: yielded {total:,} files so far...")

    self.logger.info(f"LocalDrive: complete — {total:,} files yielded.")
