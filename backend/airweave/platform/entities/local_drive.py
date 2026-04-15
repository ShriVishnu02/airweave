"""Local Drive entity schemas.

Two types: LocalDriveFolderEntity (directory container) and
LocalDriveFileEntity (individual file to index).
"""

from datetime import datetime
from typing import Optional

from airweave.platform.entities._airweave_field import AirweaveField
from airweave.platform.entities._base import BaseEntity


class LocalDriveFolderEntity(BaseEntity):
    """A directory node discovered during the local-drive walk."""

    folder_path: str = AirweaveField(
        ...,
        description="Absolute resolved path of the directory.",
        is_entity_id=True,
    )
    folder_name: str = AirweaveField(
        ...,
        description="Basename of the directory.",
        is_name=True,
        embeddable=True,
    )
    parent_path: Optional[str] = AirweaveField(
        None,
        description="Absolute resolved path of the parent directory; None for root.",
    )


class LocalDriveFileEntity(BaseEntity):
    """A single file on the local drive, ready for indexing."""

    file_id: str = AirweaveField(
        ...,
        description="Stable unique ID: the real (symlink-resolved) absolute path.",
        is_entity_id=True,
    )
    file_name: str = AirweaveField(
        ...,
        description="Basename of the file (e.g. 'report.pdf').",
        is_name=True,
        embeddable=True,
    )
    file_path: str = AirweaveField(
        ...,
        description="Absolute path as traversed (may differ from file_id if symlinks exist).",
    )
    extension: str = AirweaveField(
        ...,
        description="Lowercase file extension including dot (e.g. '.pdf'). Empty string if none.",
        embeddable=True,
    )
    size_bytes: int = AirweaveField(
        ...,
        description="File size in bytes at time of discovery.",
    )
    modified_at: Optional[datetime] = AirweaveField(
        None,
        description="Last-modified timestamp from the filesystem (UTC).",
        is_updated_at=True,
    )
    created_at_ts: Optional[datetime] = AirweaveField(
        None,
        description="Creation timestamp (UTC); None if unavailable on this OS/filesystem.",
        is_created_at=True,
    )
    mime_type: Optional[str] = AirweaveField(
        None,
        description="MIME type guessed from extension (e.g. 'application/pdf').",
        embeddable=True,
    )
    relative_path: str = AirweaveField(
        ...,
        description="Path relative to the configured root_path.",
        embeddable=True,
    )
