# Quiz Buddy Agent

Quiz Buddy is an intelligent tutoring agent that helps students practice and learn through interactive quizzes. Built with LangGraph and Chainlit, it provides a conversational interface for quiz-based learning.

## Features

- Interactive quiz sessions with natural language understanding
- Intelligent evaluation of answers using GCSE marking criteria
- Adaptive learning based on student performance
- Progress tracking and session management
- User-friendly web interface

## Prerequisites

- Python 3.10 or higher
- pip (Python package installer)

## Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/quiz-buddy-agent.git
cd quiz-buddy-agent
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Initialize the database:
```bash
python seed_db.py
```

## Running the Application

Start the Chainlit web interface:
```bash
chainlit run chainlit/app.py
```

The application will be available at `http://localhost:8000`

## Project Structure

- `chainlit/` - Web interface and application entry point
- `base_models.py` - Core data models and structures
- `quiz_agentic_design.py` - Quiz logic and flow management
- `state.py` - State management utilities
- `tutor_db.py` - Database interactions
- `prompts/` - System prompts for different components:
  - `evaluator_prompt.md` - Answer evaluation guidelines
  - `learning_session_orchestrator_prompt.md` - Session management
  - `responder_prompt.md` - Response generation

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the LICENSE file for details.
