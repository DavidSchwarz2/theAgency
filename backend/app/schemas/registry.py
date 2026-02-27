from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class _RegistryBase(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AgentProfile(_RegistryBase):
    name: str
    description: str
    opencode_agent: str
    default_model: str | None = None
    system_prompt_additions: str = ""


class AgentStep(_RegistryBase):
    """A pipeline step that delegates to an AI agent."""

    type: Literal["agent"] = "agent"
    agent: str
    description: str = ""
    model: str | None = None


class ApprovalStep(_RegistryBase):
    """A pipeline step that pauses execution until a human approves or rejects."""

    type: Literal["approval"]
    description: str = ""
    remind_after_hours: float | None = Field(default=None, gt=0)


# Discriminated union — the `type` field routes parsing.
PipelineStep = Annotated[AgentStep | ApprovalStep, Field(discriminator="type")]


def _inject_step_type(steps: list) -> list:
    """Backwards-compatibility: inject type='agent' for steps that omit the type field."""
    result = []
    for step in steps:
        if isinstance(step, dict) and "type" not in step:
            step = {**step, "type": "agent"}
        result.append(step)
    return result


class PipelineTemplate(_RegistryBase):
    name: str
    description: str
    steps: list[PipelineStep]

    @field_validator("steps", mode="before")
    @classmethod
    def _backfill_step_types(cls, v: object) -> object:
        if isinstance(v, list):
            return _inject_step_type(v)
        return v


class RegistryConfig(_RegistryBase):
    agents: list[AgentProfile]
    pipelines: list[PipelineTemplate]

    @model_validator(mode="after")
    def _steps_reference_known_agents(self) -> "RegistryConfig":
        known = {a.name for a in self.agents}
        for pipeline in self.pipelines:
            for step in pipeline.steps:
                if isinstance(step, AgentStep) and step.agent not in known:
                    raise ValueError(f"Pipeline '{pipeline.name}' step references unknown agent '{step.agent}'")
        return self


# --- Response models (for router, deliberately omit internal fields) ---
# These are intentionally separate from the domain models to control the API surface.
# When adding fields to the domain models above, decide explicitly whether they belong
# in the API response. Fields intentionally excluded:
#   AgentProfileResponse: system_prompt_additions (internal prompt detail)
#   ApprovalStepResponse: remind_after_hours is included so the UI can display the timeout config.


class _ResponseBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class AgentProfileResponse(_ResponseBase):
    name: str
    description: str
    opencode_agent: str
    default_model: str | None = None


class AgentStepResponse(_ResponseBase):
    type: Literal["agent"] = "agent"
    agent: str
    description: str


class ApprovalStepResponse(_ResponseBase):
    type: Literal["approval"]
    description: str
    remind_after_hours: float | None = None


PipelineStepResponse = Annotated[AgentStepResponse | ApprovalStepResponse, Field(discriminator="type")]


class PipelineTemplateResponse(_ResponseBase):
    name: str
    description: str
    steps: list[PipelineStepResponse]


class AgentWriteRequest(_RegistryBase):
    """Request body for POST /registry/agents and PUT /registry/agents/{name}."""

    name: str
    description: str
    opencode_agent: str
    default_model: str | None = None
    system_prompt_additions: str = ""


class AgentStepWrite(_RegistryBase):
    """A write-side agent step — includes optional model override.

    Structurally identical to AgentStep by design: the separate class gives this type
    a distinct name in the OpenAPI schema, which keeps the generated client types clean.
    """

    type: Literal["agent"] = "agent"
    agent: str
    description: str = ""
    model: str | None = None


class ApprovalStepWrite(_RegistryBase):
    """A write-side approval step."""

    type: Literal["approval"]
    description: str = ""
    remind_after_hours: float | None = Field(default=None, gt=0)


PipelineStepWrite = Annotated[AgentStepWrite | ApprovalStepWrite, Field(discriminator="type")]


class PipelineWriteRequest(_RegistryBase):
    """Request body for POST /registry/pipelines and PUT /registry/pipelines/{name}."""

    name: str
    description: str
    steps: list[PipelineStepWrite]


class GitHubIssueResponse(BaseModel):
    number: int
    title: str
    body: str | None = None
    labels: list[str] = []
