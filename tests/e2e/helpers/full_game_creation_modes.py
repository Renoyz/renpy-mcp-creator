from dataclasses import dataclass


@dataclass(frozen=True)
class ExecutionMode:
    name: str
    allow_api_promote_fallback: bool
    allow_api_confirm_fallback: bool
    use_mock_build: bool
    expect_real_build: bool


UI_ONLY_DEBUG = ExecutionMode(
    name="ui_only_debug",
    allow_api_promote_fallback=False,
    allow_api_confirm_fallback=False,
    use_mock_build=True,
    expect_real_build=False,
)

HYBRID_RECOVERY = ExecutionMode(
    name="hybrid_recovery",
    allow_api_promote_fallback=True,
    allow_api_confirm_fallback=True,
    use_mock_build=True,
    expect_real_build=False,
)

MOCK_BUILD_ACCEPTANCE = ExecutionMode(
    name="mock_build_acceptance",
    allow_api_promote_fallback=False,
    allow_api_confirm_fallback=False,
    use_mock_build=True,
    expect_real_build=False,
)

REAL_BUILD_ACCEPTANCE = ExecutionMode(
    name="real_build_acceptance",
    allow_api_promote_fallback=False,
    allow_api_confirm_fallback=False,
    use_mock_build=False,
    expect_real_build=True,
)
