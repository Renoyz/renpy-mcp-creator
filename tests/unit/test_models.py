"""Tests for shared data models."""

from pathlib import Path

from renpy_mcp.models import BuildRequest, BuildResult, ImageGenerationResult


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
            error="Build script not found",
        )
        assert result.success is False
        assert result.error == "Build script not found"
        assert result.output_path is None


class TestImageGenerationResult:
    def test_image_generation_result_defaults(self):
        result = ImageGenerationResult(success=True, prompt="a castle", image_type="background")
        assert result.success is True
        assert result.files == []
        assert result.primary_file is None
