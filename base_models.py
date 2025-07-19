from pydantic import BaseModel, Field
from typing import Literal, List, Dict, Any

class EvaluationResult(BaseModel):
    result: Literal["correct", "incorrect", "partial"] = Field(
        description="Whether the answer meets GCSE marking criteria fully, partially, or not at all"
    )
    score: float = Field(
        description="Score between 0.0 and 1.0, aligned with GCSE grade boundaries"
    )
    feedback: str = Field(
        description="Detailed feedback including: key points covered, areas for improvement, and GCSE-specific guidance"
    )

class PlanStep(BaseModel):
    description: str = Field(description="Description of what this step accomplishes")
    step_id: str = Field(description="Unique identifier for this step (e.g., 'E1')")
    tool_name: str = Field(description="Name of the tool to execute")
    tool_input: Dict[str, Any] = Field(description="Input parameters for the tool")

class PlannerResult(BaseModel):
    plan_description: str = Field(description="Overall description of the plan")
    steps: List[PlanStep] = Field(description="Ordered list of steps to execute")
    state_updates: Dict[str, Any] = Field(description="Any immediate state updates needed")
