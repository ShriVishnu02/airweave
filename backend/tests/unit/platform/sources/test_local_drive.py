import pytest
from unittest.mock import MagicMock

from airweave.core.logging import ContextualLogger
from airweave.domains.sources.tokenproviders.protocol import SourceAuthProvider
from airweave.platform.configs.config import LocalDriveConfig
from airweave.platform.entities.local_drive import LocalDriveFolderEntity, LocalDriveFileEntity
from airweave.platform.httpclient.airweaveclient import AirweaveHttpClient
from airweave.platform.sources.local_drive import LocalDriveSource
from airweave.schemas.sourceconnection import AuthenticationMethod


def mocks():
    return dict(
        auth=MagicMock(spec=SourceAuthProvider),
        logger=MagicMock(spec=ContextualLogger),
        http_client=MagicMock(spec=AirweaveHttpClient),
    )


async def make_source(tmp_path, **kwargs):
    return await LocalDriveSource.create(
        config=LocalDriveConfig(root_path=str(tmp_path), **kwargs),
        **mocks(),
    )


class TestCreate:
    @pytest.mark.asyncio
    async def test_create_sets_all_config_fields(self, tmp_path):
        src = await make_source(tmp_path, extensions=[".py", ".md"], max_file_size_mb=5.0)
        assert src.root_path == str(tmp_path)
        assert ".py" in src.extensions and ".md" in src.extensions
        assert src.max_file_size_mb == 5.0
        assert src.follow_symlinks is False


class TestValidate:
    @pytest.mark.asyncio
    async def test_valid_dir_passes(self, tmp_path):
        src = await make_source(tmp_path)
        await src.validate()  # must not raise

    @pytest.mark.asyncio
    async def test_empty_root_path_raises(self, tmp_path):
        src = await make_source(tmp_path)
        src.root_path = ""
        with pytest.raises(ValueError, match="root_path is not configured"):
            await src.validate()

    @pytest.mark.asyncio
    async def test_nonexistent_root_path_raises(self, tmp_path):
        src = await make_source(tmp_path)
        src.root_path = "nonexistent_path_xyz"
        with pytest.raises(ValueError, match="does not exist or is not a directory"):
            await src.validate()


class TestGenerateEntities:
    @pytest.mark.asyncio
    async def test_empty_dir_yields_only_folder_entity(self, tmp_path):
        src = await make_source(tmp_path)
        entities = [e async for e in src.generate_entities()]
        assert len(entities) == 1
        assert isinstance(entities[0], LocalDriveFolderEntity)

    @pytest.mark.asyncio
    async def test_folder_entity_has_correct_fields(self, tmp_path):
        src = await make_source(tmp_path)
        folder = [e async for e in src.generate_entities()][0]
        assert folder.folder_name == tmp_path.name
        assert folder.folder_path == str(tmp_path.resolve())

    @pytest.mark.asyncio
    async def test_file_entity_shape(self, tmp_path):
        (tmp_path / "report.pdf").write_bytes(b"%PDF")
        src = await make_source(tmp_path)
        entities = [e async for e in src.generate_entities()]
        file_ent = next(
            (e for e in entities if isinstance(e, LocalDriveFileEntity)), None
        )
        assert file_ent is not None
        assert file_ent.file_name == "report.pdf"
        assert file_ent.extension == ".pdf"
        assert file_ent.size_bytes == 4
        assert file_ent.relative_path == "report.pdf"

    @pytest.mark.asyncio
    async def test_extension_filter(self, tmp_path):
        (tmp_path / "a.py").write_text("code")
        (tmp_path / "b.txt").write_text("text")
        src = await make_source(tmp_path, extensions=[".py"])
        entities = [e async for e in src.generate_entities()]
        file_ents = [e for e in entities if isinstance(e, LocalDriveFileEntity)]
        assert len(file_ents) == 1
        assert file_ents[0].file_name == "a.py"

    @pytest.mark.asyncio
    async def test_max_file_size_filter(self, tmp_path):
        (tmp_path / "large.bin").write_bytes(b"x" * 2 * 1024 * 1024)  # 2 MB
        (tmp_path / "small.txt").write_text("tiny")
        src = await make_source(tmp_path, max_file_size_mb=1.0)
        entities = [e async for e in src.generate_entities()]
        names = [e.file_name for e in entities if isinstance(e, LocalDriveFileEntity)]
        assert "small.txt" in names
        assert "large.bin" not in names

    @pytest.mark.asyncio
    async def test_hidden_files_are_skipped(self, tmp_path):
        (tmp_path / ".hidden").write_text("secret")
        (tmp_path / "visible.txt").write_text("public")
        src = await make_source(tmp_path)
        entities = [e async for e in src.generate_entities()]
        names = [e.file_name for e in entities if isinstance(e, LocalDriveFileEntity)]
        assert ".hidden" not in names
        assert "visible.txt" in names


def test_source_metadata():
    assert LocalDriveSource.short_name == "local_drive"
    assert AuthenticationMethod.DIRECT in LocalDriveSource.auth_methods
    assert LocalDriveSource.internal is True
