from typing import List, Tuple, Any, Dict, Union
from copy import deepcopy
from dataclasses import is_dataclass, asdict
import json
import os
from pathlib import Path
import logging
from tutor_db import get_flashcards_by_topic_id
from langchain_core.messages import AIMessage
from langchain_groq import ChatGroq
from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
from langchain.output_parsers import PydanticOutputParser
from base_models import EvaluationResult, PlannerResult

logger = logging.getLogger(__name__)

def bulk_set_state(state: Dict[str, Any], updates: List[Tuple[str, Any]]) -> List[Tuple[str, Any]]:
    """
    Creates a list of merged state update tuples from a list of field updates.
    
    Args:
        state: Current state dictionary to merge updates with
        updates: List of tuples where each tuple contains:
                - field_name (str): The state field to update
                - value (Any): The new value for that field
    
    Returns:
        List of tuples containing (field_name, merged_value) where merged_value includes
        both the update and any existing state for that field.
    
    Example:
        >>> current_state = {"quiz_state": {"state": "idle", "progress": 0}}
        >>> bulk_set_state(current_state, [
        ...     ("quiz_state", {"state": "awaiting_answer"})
        ... ])
        [("quiz_state", {"state": "awaiting_answer", "progress": 0})]  # Preserves progress
    """
    
    # Track merged updates
    merged_updates = []
    
    for field_name, value in updates:
        if "." in field_name:
            # Handle nested updates (e.g., "quiz_state.progress")
            parent, child = field_name.split(".", 1)
            parent_value = deepcopy(state.get(parent, {}))
            if isinstance(parent_value, dict):
                if isinstance(value, dict):
                    # Merge dictionaries for nested updates
                    if child in parent_value:
                        parent_value[child] = {**parent_value[child], **value}
                    else:
                        parent_value[child] = deepcopy(value)
                else:
                    parent_value[child] = value
                merged_updates.append((parent, parent_value))
        else:
            # Handle dictionary merges
            if isinstance(value, dict):
                if field_name in state and isinstance(state[field_name], dict):
                    # Merge with existing dictionary
                    merged_value = {**deepcopy(state[field_name]), **deepcopy(value)}
                else:
                    # Create new dictionary
                    merged_value = deepcopy(value)
                merged_updates.append((field_name, merged_value))
            # Handle list updates for flashcard_states
            elif field_name == "flashcard_states":
                # Ensure value is a list
                if not isinstance(value, list):
                    print(f"Warning: Expected list for flashcard_states but got {type(value)}")
                    continue
                    
                # Get current flashcards, ensure it's a list
                current_flashcards = state.get(field_name, [])
                if not isinstance(current_flashcards, list):
                    current_flashcards = []
                    
                updated_flashcards = list(deepcopy(current_flashcards))
                
                # Update existing flashcards or append new ones
                for new_card in value:
                    if not isinstance(new_card, dict):
                        print(f"Warning: Invalid flashcard format: {new_card}")
                        continue
                        
                    found = False
                    for i, card in enumerate(updated_flashcards):
                        if isinstance(card, dict) and card.get("id") == new_card.get("id"):
                            updated_flashcards[i] = {**card, **deepcopy(new_card)}
                            found = True
                            break
                    if not found:
                        updated_flashcards.append(deepcopy(new_card))
                
                merged_updates.append((field_name, updated_flashcards))
            else:
                merged_updates.append((field_name, deepcopy(value)))
    return merged_updates

def parse_tool_input(input_str: str) -> List[Tuple[str, Any]]:
    """Parse the tool input string into a list of (key, value) tuples."""
    updates = []
    # Clean up the input string
    input_str = input_str.strip()
    
    # Split by semicolon and filter out empty items
    items = [item.strip() for item in input_str.split(';') if item.strip()]
    
    for item in items:
        try:
            # Split by first equals sign
            key, value = item.strip().split('=', 1)
            key = key.strip()
            value = value.strip()
            
            # Try to parse the JSON value
            try:
                parsed_value = json.loads(value)
                # For flashcard_states, ensure we have a list of dicts
                if key == "flashcard_states":
                    if not isinstance(parsed_value, list):
                        print(f"Warning: flashcard_states must be a list, got {type(parsed_value)}")
                        continue
                    # Validate each flashcard is a dict
                    parsed_value = [card for card in parsed_value if isinstance(card, dict)]
            except json.JSONDecodeError as e:
                print(f"JSON parse error for value: {value}")
                print(f"Error: {str(e)}")
                # If JSON parsing fails, use the string value as is, but not for lists
                if key == "flashcard_states":
                    continue  # Skip invalid flashcard states
                parsed_value = value
                
            updates.append((key, parsed_value))
        except ValueError as e:
            print(f"Error parsing item '{item}': {str(e)}")
            continue
            
    return updates

def parse_llm_plan_response(response_content: str) -> List[Tuple[str, str, str, List[Tuple[str, Any]]]]:
    """Parse the LLM's plan response into structured plan steps.
    
    Args:
        response_content: Raw response string from the LLM
        
    Returns:
        List of tuples (description, step_id, tool_name, updates) where:
        - description: Plan description string
        - step_id: Step identifier (e.g., "E1")
        - tool_name: Name of the tool to execute
        - updates: List of (key, value) tuples for tool input
    """
    plans = []
    
    # Split response into plan sections
    plan_sections = response_content.split("\nPlan: ")
    
    for section in plan_sections:
        if not section.strip():  # Skip empty sections
            continue
            
        try:
            # Split section into description and steps
            parts = section.split("\n#E")
            
            # First part is the plan description
            plan_description = parts[0].strip()
            if plan_description.startswith("Plan: "):  # Handle first section
                plan_description = plan_description[6:].strip()
            
            # Process each step in this plan section
            for step_text in parts[1:]:
                try:
                    # Parse step ID
                    step_parts = step_text.split("=", 1)  # Split on first = only
                    if len(step_parts) != 2:
                        continue
                        
                    step_id = "E" + step_parts[0].strip()
                    tool_part = step_parts[1].strip()
                    
                    # Find tool name (everything before the first [)
                    tool_name_end = tool_part.find("[")
                    if tool_name_end == -1:
                        continue
                    tool_name = tool_part[:tool_name_end].strip()
                    
                    # Find matching brackets for tool input
                    bracket_count = 0
                    start_idx = tool_name_end
                    end_idx = -1
                    
                    for i, char in enumerate(tool_part[start_idx:], start=start_idx):
                        if char == '[':
                            bracket_count += 1
                        elif char == ']':
                            bracket_count -= 1
                            if bracket_count == 0:
                                end_idx = i
                                break
                    
                    if end_idx == -1 or bracket_count != 0:
                        print(f"Warning: Unmatched brackets in step {step_id}")
                        continue
                        
                    # Extract tool input between matched brackets
                    tool_input = tool_part[start_idx + 1:end_idx].strip()
                    
                    # Parse the tool input into a list of (key, value) tuples
                    updates = parse_tool_input(tool_input)
                    plans.append((plan_description, step_id, tool_name, updates))
                    
                except Exception as e:
                    print(f"Error parsing step in section: {e}")
                    continue
                    
        except Exception as e:
            print(f"Error parsing plan section: {e}")
            continue
    
    return plans

def populate_flashcards(topic_id: int) -> Dict[str, Any]:
    """Populate flashcard states with new list of flashcard state entries for a specific topic.
    
    Args:
        topic_id: ID of the topic to filter flashcards by
        
    Returns:
        Dictionary containing the updated flashcard_states
    """
    flashcards = get_flashcards_by_topic_id(topic_id)
    
    # Initialize new flashcard states
    new_flashcard_states = []
    
    # Create state entry for each flashcard
    for flashcard in flashcards:
        new_flashcard_states.append({
            "id": flashcard["id"],
            "status": "queued",
            "question": flashcard["question"],
            "marking_criteria": flashcard["marking_criteria"],
            "attempts": 0,
            "user_answers": [],
            "evaluation": None
        })
    
    # Set first flashcard as active if there are any
    if new_flashcard_states:
        new_flashcard_states[0]["status"] = "active"
    
    return new_flashcard_states

def create_responder_chain():
    """Create the response generation chain for interactive communication.
    
    The chain:
    1. Uses a slightly higher temperature for natural responses
    2. Incorporates user context and emotion
    3. Maintains consistent conversation style
    4. Provides educational feedback based on GCSE marking criteria
    5. Adapts response style based on user's performance and state
    
    Returns:
        A LangChain chain configured for response generation
    """
    model = ChatGroq(
        model="llama-3.3-70b-versatile",
        temperature=0,
        groq_api_key=os.environ["GROQ_API_KEY"]
    )
    
    responder_prompt = load_prompt("responder_prompt.md")
    prompt = ChatPromptTemplate.from_messages([
        ("system", responder_prompt),
        ("human", "Here is the current state:\n\n{state_json}")
    ])
    
    return prompt | model

def load_prompt(prompt_name: str) -> str:
    """Load a prompt from a markdown file
    
    Args:
        prompt_name: Name of the prompt file (e.g. 'learning_session_orchestrator_prompt.md')
        
    Returns:
        The contents of the prompt file as a string
    """
    try:
        # For Jupyter notebook environment, use the current working directory
        prompt_path = Path(os.getcwd()) / prompt_name
        
        # Check if the file exists
        if not prompt_path.exists():
            # Try one directory up if not found
            prompt_path = Path(os.getcwd()).parent / prompt_name
            if not prompt_path.exists():
                raise FileNotFoundError(
                    f"Prompt file not found. Searched in:\n"
                    f"1. {Path(os.getcwd()) / prompt_name}\n"
                    f"2. {prompt_path}"
                )
        
        logger.info(f"Loading prompt from: {prompt_path}")
        with open(prompt_path, "r", encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        logger.error(f"Failed to load prompt {prompt_name}: {e}")
        raise

def create_planner_chain():
    """Create the planner chain with Groq LLM
    
    Returns:
        A LangChain chain configured for learning session orchestration
    """
    # Load the planner prompt
    prompt_template = load_prompt("learning_session_orchestrator_prompt.md")
    
    # Create chain components
    model = ChatGroq(
        model="llama-3.3-70b-versatile",
        temperature=0,
        groq_api_key=os.environ["GROQ_API_KEY"]
    )
    
    # Create a formatted template with escaped JSON braces
    prompt = ChatPromptTemplate.from_messages([
        ("system", prompt_template),
        ("user", f"""Here is the current state:

        Current Topic ID: 
        {{current_topic_id}}

        Topics:
        {{topics}}

        Flashcard States:
        {{flashcard_states}}

        Score:
        {{score}}

        Quiz State:
        {{quiz_state}}

        User:
        {{user}}

        Messages:
        {{messages}}

        Hard Flashcards:
        {{hard_flashcards}}
        """)
])
    
    # Create chain - return raw text output
    chain = prompt | model
    
    return chain

def create_evaluator_chain():
    """Create the evaluator chain with Groq LLM
    
    Returns:
        A LangChain chain configured for answer evaluation using GCSE marking criteria
    """
    # Load the evaluator prompt
    prompt_template = load_prompt("evaluator_prompt.md")
    
    # Create chain components
    model = ChatGroq(
        model="llama-3.3-70b-versatile",
        temperature=0,
        groq_api_key=os.environ["GROQ_API_KEY"]
    )
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", prompt_template),
        ("user", """Please evaluate this student answer:

    Question: {question}

    Marking Criteria:
    {marking_criteria}

    Student Answer:
    {student_answer}

    Return your evaluation as a JSON object with:
    - result: "correct" (score ≥ 0.8), "partial" (0.3 ≤ score < 0.8), or "incorrect" (score < 0.3)
    - score: Float between 0.0 and 1.0
    - feedback: Structured feedback with positive reinforcement, specific points covered, areas for improvement, and GCSE-specific guidance""")
    ])
    
    parser = PydanticOutputParser(pydantic_object=EvaluationResult)
    
    # Create chain
    chain = prompt | model | parser
    
    return chain