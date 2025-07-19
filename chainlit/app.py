import chainlit as cl
from langchain_core.messages import AIMessageChunk, HumanMessage
from langgraph.checkpoint.memory import InMemorySaver
import uuid
import pandas as pd

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from quiz_agentic_design import create_chill_tutor_graph
from state import OrchestratorState


def create_initial_state():
    """Create initial tutor state with default values"""
    state = {
        "messages": [],
        "topics": [
            {"id": 1, "name": "Computational thinking"},
            {"id": 2, "name": "Data"},
            {"id": 3, "name": "Computers"},
            {"id": 4, "name": "Networks"},
            {"id": 5, "name": "Issues and impact"},
            {"id": 6, "name": "Problem-solving with programming"}
        ],
        "current_topic_id": None,
        "flashcard_states": {},
        "score": {"correct": 0, "incorrect": 0, "total_attempts": 0},
        "quiz_state": {"state": "waiting_topic", "progress": None},
        "user": {"name": None, "emotion": None, "preferences": {"difficulty_level": None}},
        "hard_flashcards": [],
        "execution_results": [],
        "current_plan": {"steps": [], "string": ""},
        "previous_plan": {"steps": [], "string": ""}
    }
    return state

@cl.on_chat_start
async def on_chat_start():
    """Initialize the quiz session"""
    initial_state = create_initial_state()
    cl.user_session.set("tutor_state", initial_state)
    cl.user_session.set("thread_id", str(2))
    cl.user_session.set("topics", initial_state["topics"])
        # Create a sample DataFrame with more than 10 rows to test pagination functionality
    




@cl.on_message
async def on_message(message: cl.Message):
    """Handle quiz interactions"""
    last_human_message = message.content
    msg = cl.Message(content="")
    thread_id = cl.user_session.get("thread_id")
    
    # Get state from session
    current_state = cl.user_session.get("tutor_state")
    if not current_state:
        # Reinitialize state if missing
        current_state = create_initial_state()
        cl.user_session.set("tutor_state", current_state)
    
    current_state["messages"].append(HumanMessage(content=last_human_message))
    cl.user_session.set("tutor_state", current_state)
    current_state["topics"] = cl.user_session.get("topics")
    
    # Initialize checkpointer with current state
    checkpointer = InMemorySaver()
    print("current_state ========>",current_state)

    
    graph = create_chill_tutor_graph(checkpointer=checkpointer)

    # Process message through graph and collect AI response
    # Pass complete state to graph
    async for chunk in graph.astream(
        current_state,  # Pass full state
        {"configurable": {"thread_id": thread_id}},
        stream_mode="messages"):
        if isinstance(chunk[0], AIMessageChunk) and chunk[1]["langgraph_node"] == "responder":
            await msg.stream_token(chunk[0].content)

    output_state = await graph.aget_state(config={"configurable": {"thread_id": thread_id}})
    print("output_state ========>",output_state)

    cl.user_session.set("tutor_state", output_state.values)