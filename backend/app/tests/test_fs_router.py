"""TDD tests for GET /fs/browse — filesystem directory browser."""

import os
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


class TestFsBrowse:
    async def test_browse_default_returns_200(self, client: AsyncClient):
        response = await client.get("/fs/browse")
        assert response.status_code == 200

    async def test_browse_returns_path_and_entries(self, client: AsyncClient):
        response = await client.get("/fs/browse")
        body = response.json()
        assert "path" in body
        assert "entries" in body
        assert isinstance(body["entries"], list)

    async def test_browse_entry_shape(self, client: AsyncClient, tmp_path: Path):
        (tmp_path / "subdir").mkdir()
        (tmp_path / "file.txt").write_text("hi")
        response = await client.get(f"/fs/browse?path={tmp_path}")
        body = response.json()
        names = {e["name"] for e in body["entries"]}
        assert "subdir" in names
        assert "file.txt" in names
        for entry in body["entries"]:
            assert "name" in entry
            assert "is_dir" in entry
            assert "path" in entry

    async def test_browse_only_dirs_filter(self, client: AsyncClient, tmp_path: Path):
        (tmp_path / "subdir").mkdir()
        (tmp_path / "file.txt").write_text("hi")
        response = await client.get(f"/fs/browse?path={tmp_path}&dirs_only=true")
        body = response.json()
        names = {e["name"] for e in body["entries"]}
        assert "subdir" in names
        assert "file.txt" not in names

    async def test_browse_has_parent_when_not_root(self, client: AsyncClient, tmp_path: Path):
        response = await client.get(f"/fs/browse?path={tmp_path}")
        body = response.json()
        assert body["parent"] is not None

    async def test_browse_parent_is_none_at_root(self, client: AsyncClient):
        response = await client.get("/fs/browse?path=/")
        body = response.json()
        assert body["parent"] is None

    async def test_browse_invalid_path_returns_404(self, client: AsyncClient):
        response = await client.get("/fs/browse?path=/this/path/does/not/exist/xyz123")
        assert response.status_code == 404

    async def test_browse_file_path_returns_400(self, client: AsyncClient, tmp_path: Path):
        f = tmp_path / "file.txt"
        f.write_text("hi")
        response = await client.get(f"/fs/browse?path={f}")
        assert response.status_code == 400

    async def test_browse_entries_sorted_dirs_first(self, client: AsyncClient, tmp_path: Path):
        (tmp_path / "z_dir").mkdir()
        (tmp_path / "a_file.txt").write_text("hi")
        (tmp_path / "a_dir").mkdir()
        response = await client.get(f"/fs/browse?path={tmp_path}")
        entries = response.json()["entries"]
        dirs = [e for e in entries if e["is_dir"]]
        files = [e for e in entries if not e["is_dir"]]
        # All dirs come before files
        dir_indices = [i for i, e in enumerate(entries) if e["is_dir"]]
        file_indices = [i for i, e in enumerate(entries) if not e["is_dir"]]
        if dir_indices and file_indices:
            assert max(dir_indices) < min(file_indices)
        # Sorted alphabetically within group
        assert [e["name"] for e in dirs] == sorted(e["name"] for e in dirs)
        assert [e["name"] for e in files] == sorted(e["name"] for e in files)

    async def test_browse_hides_dotfiles_by_default(self, client: AsyncClient, tmp_path: Path):
        (tmp_path / ".hidden").mkdir()
        (tmp_path / "visible").mkdir()
        response = await client.get(f"/fs/browse?path={tmp_path}")
        names = {e["name"] for e in response.json()["entries"]}
        assert ".hidden" not in names
        assert "visible" in names
