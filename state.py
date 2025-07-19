from typing import Dict, List, Optional, Any, Union
from langgraph.graph import MessagesState
class OrchestratorState(MessagesState):
    """
    Represents the state of the learning session orchestrator.
    
    Attributes:
        session (Dict): Contains session metadata like intent and timestamps
        topics (List[Dict]): List of available topics
        current_topic_id (Optional[int]): ID of the currently selected topic
        flashcards (List[Dict]): List of all flashcards for the current topic
        score (Dict): Tracks correct/incorrect answers and total attempts
        quiz_state (Dict): Current quiz progress and state
        flashcard_states (List[Dict]): State of each flashcard (active, completed, etc.)
        user (Dict): User information including name, emotion, and preferences
        checkpoint (str): Timestamp for state serialization
        next_node (str): Next node to execute in the workflow
        hard_flashcards (List[int]): IDs of flashcards marked as difficult
        execution_results (List[Any]): Results from executing each step in the current plan
    """
    session: Dict[str, Any]
    topics: List[Dict[str, Any]]
    current_topic_id: Optional[str]
    flashcards: List[Dict[str, Any]]
    score: Dict[str, int]
    quiz_state: Dict[str, Any]
    flashcard_states: Dict[str, Any]
    user: Dict[str, Any]
    next_node: Optional[str]
    checkpoint: Optional[str]
    hard_flashcards: List[str]
    execution_results: List[Any] = []

    current_plan: Dict[str, Union[List, str]] = {
        "steps": [],
        "string": ""
    }
    previous_plan: Dict[str, Union[List, str]] = {
        "steps": [],
        "string": ""
    }
    
