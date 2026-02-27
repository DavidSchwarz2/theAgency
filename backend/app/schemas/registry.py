from pydantic import BaseModel, ConfigDict, model_validator


class _RegistryBase(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AgentProfile(_RegistryBase):
    name: str
    description: str
    opencode_agent: str
    system_prompt_additions: str = ""


class PipelineStep(_RegistryBase):
    agent: str
    description: str = ""


class PipelineTemplate(_RegistryBase):
    name: str
    description: str
    steps: list[PipelineStep]


class RegistryConfig(_RegistryBase):
    agents: list[AgentProfile]
    pipelines: list[PipelineTemplate]

    @model_validator(mode="after")
    def _steps_reference_known_agents(self) -> "RegistryConfig":
        known = {a.name for a in self.agents}
        for pipeline in self.pipelines:
            for step in pipeline.steps:
                if step.agent not in known:
                    raise ValueError(f"Pipeline '{pipeline.name}' step references unknown agent '{step.agent}'")
        return self


# --- Response models (for router, deliberately omit internal fields) ---
# These are intentionally separate from the domain models to control the API surface.
# When adding fields to the domain models above, decide explicitly whether they belong
# in the API response. Fields intentionally excluded:
#   AgentProfileResponse: system_prompt_additions (internal prompt detail)


class _ResponseBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class AgentProfileResponse(_ResponseBase):
    name: str
    description: str
    opencode_agent: str


class PipelineStepResponse(_ResponseBase):
    agent: str
    description: str


class PipelineTemplateResponse(_ResponseBase):
    name: str
    description: str
    steps: list[PipelineStepResponse]
