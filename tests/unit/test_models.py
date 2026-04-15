"""Tests for shared data models."""

from pathlib import Path

from renpy_mcp.models import BuildRequest, BuildResult, ImageGenerationResult, ProjectInfo


class TestProjectInfo:
    def test_project_info_defaults(self):
        p = ProjectInfo(name="test_vn", path=Path("/workspace/test_vn"))
        assert p.name == "test_vn"
        assert p.path == Path("/workspace/test_vn")
        assert p.created_at is not None
        assert p.updated_at is not None


class TestBuildRequest:
    def test_build_request_defaults(self):
        req = BuildRequest(project_name="test_vn")
        assert req.project_name == "test_vn"
        assert req.target == "web"
        assert req.force_rebuild is False


class TestBuildResult:
    def test_build_result_success(self):
        result = BuildResult(
            project_name="test_vn",
            target="web",
            success=True,
            output_path=Path("/workspace/test_vn-dists/test_vn-web"),
        )
        assert result.success is True
        assert result.output_path == Path("/workspace/test_vn-dists/test_vn-web")

    def test_build_result_failure(self):
        result = BuildResult(
            project_name="test_vn",
            target="web",
            success=False,
            error="SDK not found",
        )
        assert result.success is False
        assert result.error == "SDK not found"


class TestImageGenerationResult:
    def test_image_generation_result_defaults(self):
        result = ImageGenerationResult(
            success=True,
            prompt="a cafe background",
            image_type="background",
            files=[Path("assets/background/cafe.png")],
            primary_file=Path("assets/background/cafe.png"),
        )
        assert result.success is True
        assert result.files[0] == Path("assets/background/cafe.png")
