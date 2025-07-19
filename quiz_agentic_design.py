from typing import Dict, Optional
from pathlib import Path
import json
import os
import re
import logging
from datetime import datetime
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_groq import ChatGroq
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langchain.prompts.chat import ChatPromptTemplate

from state_utils import (
    bulk_set_state, parse_llm_plan_response, populate_flashcards,
    load_prompt, create_responder_chain, create_evaluator_chain,
    create_planner_chain
)
from IPython.display import display, JSON
from state import OrchestratorState
from langchain_core.messages import AIMessage, HumanMessage
# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()


# ==================== Node Definitions ====================

# ---------- Learning Session Orchestrator (Planner) ----------

# ---------- Planner Node ----------
def convert_message(msg):
    """Convert a message object to a serializable dict."""
    if isinstance(msg, (HumanMessage, AIMessage)):
        return {"role": msg.type, "content": msg.content}
    elif isinstance(msg, dict):
        if "message" in msg:
            # Convert old format to new format
            return {"role": msg["role"], "content": msg["message"]}
        return msg
    return msg

def generate_plan(state: OrchestratorState):
    """Learning Session Orchestrator node that plans the next steps in the learning journey.
    
    This node is responsible for:
    1. Strategic planning of the educational journey
    2. Progress analysis and adapting to user performance
    3. Session flow control and transitions
    4. Learning optimization based on patterns
    5. Incrementing attempts counter and managing flashcard states
    
    Args:
        state: Current orchestrator state containing user progress, flashcards, and session info
        
    Returns:
        Updated state with new plan and any state transitions
    """
    # Validate state
    if not isinstance(state, dict):
        raise TypeError("State must be a dictionary")
        
    # Extract only the essential fields required by the orchestrator prompt
    essential_state = {
        "current_topic_id": state.get("current_topic_id"),
        "flashcard_states": state.get("flashcard_states", []),
        "score": state.get("score", {"correct": 0, "incorrect": 0, "total_attempts": 0}),
        "quiz_state": state.get("quiz_state", {}),
        "user": state.get("user", {}),
        "messages": [convert_message(msg) for msg in state.get("messages", [])],
        "hard_flashcards": state.get("hard_flashcards", []),
        "session": state.get("session", {
            "intent": "start_quizzing",
            "metadata": {"start_time": datetime.now().isoformat()}
        }),
        "topics": state.get("topics", [])
    }
    
    
    try:
        # Create and invoke the planner chain
        planner_chain = create_planner_chain()
        response = planner_chain.invoke({
            "current_topic_id": essential_state.get("current_topic_id"),
            "topics": essential_state.get("topics", []),
            "flashcard_states": essential_state.get("flashcard_states", []),
            "score": essential_state.get("score", {"correct": 0, "incorrect": 0, "total_attempts": 0}),
            "quiz_state": essential_state.get("quiz_state", {}),
            "user": essential_state.get("user", {}),
            "messages": essential_state.get("messages", []),
            "hard_flashcards": essential_state.get("hard_flashcards", [])
        })
        
        # Parse the raw text response
        result = parse_llm_plan_response(response.content)
        
        # Create new state object with updates from planner
        new_state = dict(state)  # Create a copy to avoid modifying the original
    
        # Update current and previous plans
        new_state["previous_plan"] = state.get("current_plan", {"steps": [], "string": ""})
        
        # Get the plan description from the first tuple (if any)
        plan_description = result[0][0] if result else ""
        
        # Convert parsed steps to the expected format
        new_state["current_plan"] = {
            "steps": [
                {
                    "description": plan_desc,
                    "step_id": step_id,
                    "tool": tool_name,
                    "tool_input": tool_input
                } for plan_desc, step_id, tool_name, tool_input in result
            ],
            "string": plan_description
        }
        
        return new_state
        
    except Exception as e:
        logger.error(f"Failed to generate plan: {e}")
        raise


# ---------- Evaluator Node ----------
def evaluate(state: OrchestratorState):
    """Evaluate the current answer in the state"""
    
    # Create a mutable copy of the state
    current_state = dict(state)
    
    # Find the active flashcard and its index
    active_index = next(
        (i for i, card in enumerate(current_state["flashcard_states"]) 
         if card["status"] == "active"),
        None
    )
    
    if active_index is None:
        raise ValueError("No active flashcard found in state")
    
    active_flashcard = current_state["flashcard_states"][active_index]
    
    # Get the latest user answer
    if not active_flashcard["user_answers"]:
        raise ValueError("No user answer found for active flashcard")
    
    student_answer = active_flashcard["user_answers"][-1]
    
    # Prepare input for the evaluator chain
    evaluator_input = {
        "question": active_flashcard["question"],
        "marking_criteria": active_flashcard["marking_criteria"],
        "student_answer": student_answer
    }
    
    # Get evaluation from the chain
    evaluation_chain = create_evaluator_chain()
    evaluation_result = evaluation_chain.invoke(evaluator_input)

    # Create updated flashcard with new evaluation
    updated_flashcard = dict(active_flashcard)
    updated_flashcard["evaluation"] = {
        "result": evaluation_result.result,
        "score": evaluation_result.score,
        "feedback": evaluation_result.feedback
    }
    
    # Update the flashcard in the state's flashcard_states list
    current_state["flashcard_states"][active_index] = updated_flashcard
    
    # Update score in state
    if "score" not in current_state:
        current_state["score"] = {"correct": 0, "incorrect": 0, "total_attempts": 0}
 
    current_state["score"]["total_attempts"] = current_state["score"].get("total_attempts", 0) + 1
    if evaluation_result.result == "correct":
        current_state["score"]["correct"] = current_state["score"].get("correct", 0) + 1
    elif evaluation_result.result == "incorrect":
        current_state["score"]["incorrect"] = current_state["score"].get("incorrect", 0) + 1
    
    return current_state

# ---------- Plan Executor ----------
def execute_plan(state: OrchestratorState):
    """Execute the plan generated by the Learning Session Orchestrator.
    
    This node:
    1. Executes each step in the current plan
    2. Updates state based on tool outcomes
    3. Handles state transitions
    4. Maintains execution logs
    5. Manages flashcard difficulty tracking
    
    Args:
        state: Current orchestrator state containing the plan to execute
        
    Returns:
        Updated state after plan execution
    """
    print("\n=== Starting Plan Execution ===")
    print(f"Initial State Keys: {list(state.keys())}")
    
    # Get the current plan from state
    current_plan = state.get("current_plan", {"steps": [], "string": ""})
    print(f"\nCurrent Plan: {current_plan['string']}")
    print(f"Number of Steps: {len(current_plan['steps'])}")

    # Get the current plan from state
    current_plan = state.get("current_plan", {"steps": [], "string": ""})
    
    # Create a mutable copy of the state
    current_state = dict(state)
    
    # Process each step in the plan
    for step in current_plan["steps"]:
        print(f"\nStep {current_plan['steps'].index(step)+1} of {len(current_plan['steps'])}")
        

        tool_name = step["tool"]
        tool_input = step["tool_input"]
        print(f"\nTool input: {tool_input}")
        if tool_name == "bulk_set_state":
            updated_values = bulk_set_state(current_state, tool_input)
            if updated_values:
                current_state.update(updated_values)
            #print(f"\nExecution Result: {updated_values}")
        if tool_name == "populate_flashcards":
            flashcard_states = populate_flashcards(tool_input[0][1])
            if flashcard_states:
                current_state["flashcard_states"] = flashcard_states
            #print(f"\nExecution Result: {flashcard_states}")
    # Return in LangGraph format
    print(f"\nExecution Result: {current_state}")
    return current_state

# ---------- Response Generator ----------

def respond(state: OrchestratorState):
    """Generate contextual responses based on current state.
    
    This node:
    1. Prepares relevant context from state
    2. Generates appropriate responses
    3. Manages message history using LangGraph's add_messages
    4. Handles error cases gracefully
    5. Provides feedback based on flashcard difficulty levels
    
    Args:
        state: Current orchestrator state containing context for response generation
        
    Returns:
        Updated state with new response added to message history
    """
    print("\n=== Starting Response Generation ===")
    
    # Create serializable state by converting messages
    serializable_state = state.copy()
    serializable_state["messages"] = [convert_message(msg) for msg in state.get("messages", [])]
    
    # Create the responder chain
    chain_input = {
        "state_json": json.dumps(serializable_state, indent=2)
    }
    
    # Create chain
    chain = create_responder_chain()
    
    # Invoke the chain
    try:
        response = chain.invoke(chain_input)
        print(f"Generated response: {response.content}")
        
        # Use LangGraph's add_message utility to append the new message
        new_message = [{"role": "assistant", "content": response.content}]
        state["messages"] = add_messages(state.get("messages", []), new_message)
        return state
        
    except Exception as e:
        logger.error(f"Response generation failed: {e}")
        # Return original state on error
        return state
# ---------- Conditional Edge Function ----------
def route_to_evaluation_or_response(state: OrchestratorState):
    """Route the workflow to evaluation or direct response based on quiz state.
    
    This function determines whether the user's answer needs evaluation:
    - If quiz_state is 'awaiting_evaluation', routes to the evaluator node
    - Otherwise, routes directly to the response generator
    
    Args:
        state: Current orchestrator state containing quiz progress
        
    Returns:
        String indicating the next node ("evaluator" or "responder")
    """
    quiz_state = state.get("quiz_state")
    if isinstance(quiz_state, dict):
        if quiz_state.get("state") == "awaiting_evaluation":
            return "evaluator"
    elif isinstance(quiz_state, str) and quiz_state == "awaiting_evaluation":
        return "evaluator"
    return "responder"

# ==================== Graph Configuration ====================

def create_chill_tutor_graph(checkpointer=None):
    """Create and configure the Learning Session Orchestrator workflow graph.
    
    Graph Structure:
    1. Planner (Learning Session Orchestrator)
       - Analyzes state and generates strategic plans
       - Controls educational flow and adaptivity
    
    2. Executor
       - Implements planned actions
       - Manages state transitions
       - Tracks flashcard difficulty
    
    3. Responder
       - Generates contextual responses
       - Maintains conversation flow
       - Provides educational feedback
    
    Flow: planner -> executor -> responder -> END
    
    Returns:
        Compiled LangGraph workflow ready for execution
    """
    try:
        # Initialize workflow with typed state
        workflow = StateGraph(OrchestratorState)
        
        # Add all nodes first
        workflow.add_node("planner", generate_plan)  # Strategic planning and adaptation
        workflow.add_node("executor", execute_plan)  # Plan execution and state management
        workflow.add_node("evaluator", evaluate)    # Answer evaluation
        workflow.add_node("responder", respond)     # Interactive communication

        # Set entry point
        workflow.set_entry_point("planner")

        # Add edges after all nodes are defined
        workflow.add_edge("planner", "executor")
        workflow.add_edge("executor", "responder")
        workflow.add_edge("evaluator", "responder")
        workflow.add_edge("responder", END)

        # Add conditional edges
        workflow.add_conditional_edges(
            "executor",
            route_to_evaluation_or_response,
            {"evaluator": "evaluator", "responder": "responder"}
        )

        # Compile with checkpointer if provided
        return workflow.compile(checkpointer=checkpointer)
    except Exception as e:
        logger.error(f"Failed to create or compile graph: {e}")
        raise

# ---------- Main Function ----------
def main() -> None:
    """Main function to run the Learning Session Orchestrator"""
    try:
        # Create the graph
        graph = create_chill_tutor_graph()
        
        # Define initial state with proper typing
        initial_state: Dict = {
            "messages":[],
            "quiz_state": {"state": "waiting_for_topic", "progress": None},
            "topics": [
                {"id": 1, "name": "Computational thinking"},
                {"id": 2, "name": "Data"},
                {"id": 3, "name": "Computers"},
                {"id": 4, "name": "Networks"},
                {"id": 5, "name": "Issues and impact"},
                {"id": 6, "name": "Problem-solving with programming"}
            ],
            "current_topic_id": None,
            "flashcard_states": [],
            "score": {"correct": 0, "incorrect": 0, "total_attempts": 0},
            "user": {
                "name": "Mo",
                "emotion": None,
                "preferences": {"difficulty_level": None}
            },
            "hard_flashcards": [],
            "current_plan": {"steps": [], "string": ""},
            "previous_plan": {"steps": [], "string": ""}
        }
        evaluation_state: Dict = {
            "messages": [
                HumanMessage(content="Binary representation is a way of representing numbers using only 0s and 1s. It's fundamental to how computers store and process data. Each digit position represents a power of 2, and we can convert between binary and decimal by adding up these powers of 2 where 1s appear.")
            ],
            "quiz_state": {"state": "waiting_answer", "progress": None},
            "topics": [
                {"id": 1, "name": "Computational thinking"},
                {"id": 2, "name": "Data"},
                {"id": 3, "name": "Computers"},
                {"id": 4, "name": "Networks"},
                {"id": 5, "name": "Issues and impact"},
                {"id": 6, "name": "Problem-solving with programming"}
            ],
            "current_topic_id": 2,
            "flashcard_states": [{'id': 1,
                'status': 'active',
                'question': 'What do you know about: Binary representation?',
                'marking_criteria': 'Key points for full marks:\n1. Definition: Binary is a base-2 number system using only 0s and 1s\n2. Structure: Each position represents a power of 2 (e.g., 2^0, 2^1, 2^2)\n3. Conversion: Explain decimal to binary conversion using powers of 2\n4. Computing relevance: Fundamental to digital data storage and processing\n5. Examples: Show binary representation of simple numbers (e.g., 8 = 1000)',
                'attempts': 0,
                'user_answers': [],
                'evaluation': None},
                {'id': 2,
                'status': 'queued',
                'question': 'What do you know about: Data storage and compression?',
                'marking_criteria': 'Key points for full marks:\n1. Storage types: Primary (RAM) vs Secondary (HDD, SSD)\n2. Storage units: Bits, bytes, KB, MB, GB, TB\n3. Compression types: Lossy vs Lossless with examples\n4. Compression benefits: Reduced file size, faster transmission\n5. Common formats: ZIP for lossless, JPEG/MP3 for lossy',
                'attempts': 0,
                'user_answers': [],
                'evaluation': None},
                {'id': 3,
                'status': 'queued',
                'question': 'What do you know about: Encryption?',
                'marking_criteria': 'Key points for full marks:\n1. Definition: Encryption is the process of converting data into a secure format to protect it from unauthorized access.\n2. Types: Symmetric (e.g., AES) vs Asymmetric (e.g., RSA)\n3. Common uses: Data at rest, data in transit, authentication\n4. Importance: Ensures data confidentiality and integrity\n5. Examples: SSL/TLS for secure web connections, AES for file encryption',
                'attempts': 0,
                'user_answers': [],
                'evaluation': None}],
            "score": {"correct": 0, "incorrect": 0, "total_attempts": 0},
            "user": {
                "name": "Mo",
                "emotion": None,
                "preferences": {"difficulty_level": None}
            },
            "hard_flashcards": [],
            "current_plan": {"steps": [], "string": ""},
            "previous_plan": {"steps": [], "string": ""}
        }
        
        # Run the graph with the initial state
        try:
            result = graph.invoke(evaluation_state)
            logger.info("\nLearning Session Orchestrator Plan:")
            from pprint import pprint
            pprint(result)
        except Exception as e:
            logger.error(f"Failed to invoke graph: {e}")
            raise
            
    except Exception as e:
        logger.error(f"Main execution failed: {e}")
        raise
if __name__ == "__main__":
    main()
