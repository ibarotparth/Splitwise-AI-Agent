# Splitwise AI Agent

## Project Overview

The Splitwise AI Agent is an innovative project that combines agentic AI with the Splitwise expense-sharing platform. This application provides a natural language chatbot interface that allows users to manage their expenses conversationally, while ensuring secure API key handling through a proxy architecture.

### Key Features

- **Conversational Expense Management**: Add expenses using natural language commands like "Add $45 for lunch with Mike and Sarah"
- **Agentic AI Integration**: Powered by Large Language Models (LLMs) for intelligent intent recognition and expense parsing
- **Secure API Proxy**: Encrypted storage and proxy-based access to Splitwise API keys
- **Web-based Chat Interface**: Simple, intuitive UI for interacting with the AI agent
- **Multi-turn Conversations**: Context-aware dialogues with follow-up question handling

### MVP Scope

The Minimum Viable Product focuses on core expense operations:

- Expense creation with automatic parsing of amount, description, participants, and dates
- Basic expense retrieval and balance queries
- Secure authentication and API key management
- Error handling and user feedback

## Architecture

The project follows a modular architecture with:

- **Backend API**: FastAPI-based REST API for business logic
- **AI Agent**: LangChain-powered agent for natural language processing
- **Frontend**: Streamlit-based chat interface
- **Security Layer**: Encrypted proxy for Splitwise API interactions

## Tech Stack

### Core Technologies

- **Python 3.10+**: Primary programming language
- **LangChain**: Agent framework for LLM integration
- **OpenAI API**: LLM provider (with $5 free credit for new users)
- **FastAPI**: Backend web framework
- **Streamlit**: Frontend chat interface

### Supporting Libraries

- **Pydantic**: Data validation and serialization
- **Requests/httpx**: HTTP client libraries
- **cryptography**: Security and encryption
- **python-dotenv**: Environment variable management

### Development Tools

- **VS Code**: Primary IDE
- **Git**: Version control
- **Virtualenv**: Python environment management
- **Black/Flake8**: Code formatting and linting

## Prerequisites

- Python 3.10 or higher
- VS Code with Python extensions
- OpenAI API key (free tier available)
- Splitwise developer account

## Installation

1. **Clone the repository**

   ```bash
   git clone https://github.com/yourusername/splitwise-ai-agent.git
   cd splitwise-ai-agent
   ```

2. **Create virtual environment**

   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**

   ```bash
   pip install -r requirements.txt
   ```

4. **Set up environment variables**

   ```bash
   cp .env.example .env
   # Edit .env with your API keys
   ```

5. **Run the application**

   ```bash
   # Backend API
   uvicorn app.main:app --reload

   # Chat interface (in another terminal)
   streamlit run ui/chat_app.py
   ```

## Usage

1. Open the Streamlit chat interface in your browser
2. Authenticate with your Splitwise credentials
3. Start chatting with the AI agent using natural language
4. Examples:
   - "Add $25 for coffee with John"
   - "What's my balance with Sarah?"
   - "Show my recent expenses"

## Project Structure

```
splitwise-ai-agent/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI application
│   ├── agent.py             # LangChain agent logic
│   ├── splitwise_client.py  # Splitwise API client
│   └── security.py          # API key management
├── ui/
│   └── chat_app.py          # Streamlit chat interface
├── tests/
│   └── test_agent.py
├── requirements.txt
├── .env.example
├── requirements.md          # Detailed project requirements
├── tech-stack.md           # Technology stack documentation
└── README.md
```

## API Requirements

- **Splitwise API**: REST API for expense management (free for development)
- **OpenAI API**: LLM services (pay-per-use, $5 free credit available)

## Development Roadmap

### Phase 1: MVP (Current)

- Basic expense creation and retrieval
- Simple chat interface
- Secure API key proxy

### Phase 2: Enhanced Features

- Advanced expense analytics
- Group management
- Multi-currency support
- Voice input capabilities

### Phase 3: Production

- Scalable deployment
- Advanced security features
- Mobile app interface
- Integration with other expense platforms

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- Splitwise API for expense management capabilities
- OpenAI for powerful LLM technology
- LangChain for agent framework
- FastAPI and Streamlit communities

## Contact

For questions or support, please open an issue on GitHub or contact the maintainers.

---

_This project demonstrates advanced AI agent capabilities in a practical expense management application._
