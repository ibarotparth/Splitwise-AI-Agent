# Tech Stack: Splitwise AI Agent

## Overview

This document outlines the technologies and tools required to implement the Splitwise AI Agent project. The stack is designed for rapid development, security, and scalability while being accessible for developers with VS Code on macOS.

## Core Technologies

### Programming Language

- **Python 3.10+**: Primary language for backend logic, AI integration, and API handling
  - Why: Excellent support for AI/ML libraries, web frameworks, and API development
  - Installation: Already available on macOS, ensure version 3.10 or higher

### AI and Agent Frameworks

- **LangChain**: Framework for building applications with LLMs
  - Why: Provides agent capabilities, prompt management, and tool integration
  - Installation: `pip install langchain`
- **OpenAI API**: Large Language Model provider
  - Why: Powerful GPT models for natural language understanding and generation
  - Setup: Requires API key from OpenAI platform
  - Cost: Pay-per-use pricing

### Web Framework

- **FastAPI**: Modern, fast web framework for building APIs
  - Why: High performance, automatic API documentation, type safety with Pydantic
  - Installation: `pip install fastapi uvicorn`
  - Alternative: Flask (simpler but less feature-rich)

### Chat Interface

- **Streamlit**: Framework for building interactive web apps quickly
  - Why: Perfect for chat interfaces, easy to implement MVP
  - Installation: `pip install streamlit`
  - Alternative: Gradio (more focused on ML interfaces)

## Supporting Libraries

### HTTP and API

- **Requests**: HTTP library for API calls
  - Installation: `pip install requests`
- **httpx**: Modern async HTTP client
  - Installation: `pip install httpx`
  - Why: Better performance for concurrent requests

### Data Validation and Serialization

- **Pydantic**: Data validation and settings management
  - Installation: `pip install pydantic`
  - Why: Type safety and automatic validation

### Security and Encryption

- **cryptography**: Cryptographic recipes and primitives
  - Installation: `pip install cryptography`
  - Why: Secure API key encryption
- **python-jose**: JSON Web Token implementation
  - Installation: `pip install python-jose[cryptography]`
  - Why: JWT handling for authentication

### Environment and Configuration

- **python-dotenv**: Environment variable management
  - Installation: `pip install python-dotenv`
  - Why: Secure storage of API keys and configuration

### Development Tools

- **VS Code Extensions**:
  - Python (Microsoft)
  - Pylance (Microsoft) - for better Python support
  - Jupyter (Microsoft) - for notebook development
  - GitLens (GitKraken) - for Git integration

## Development Environment Setup

### Package Management

- **pip**: Standard Python package installer
- **virtualenv**: Isolated Python environments
  - Installation: `pip install virtualenv`
  - Usage: `virtualenv venv && source venv/bin/activate`

### Version Control

- **Git**: Distributed version control
  - Installation: Already available on macOS
  - Setup: Initialize repository with `git init`

### Code Quality

- **Black**: Code formatter
  - Installation: `pip install black`
- **Flake8**: Linting tool
  - Installation: `pip install flake8`
- **mypy**: Static type checker
  - Installation: `pip install mypy`

## APIs and Services

### External APIs

- **Splitwise API**: REST API for expense management
  - Documentation: https://dev.splitwise.com/
  - Authentication: API key or OAuth
  - Rate Limits: Check documentation for limits
- **OpenAI API**: LLM services
  - Documentation: https://platform.openai.com/docs
  - Models: GPT-4, GPT-3.5-turbo
  - Cost: Monitor usage and costs

## Infrastructure and Deployment

### Local Development

- **macOS**: Native development environment
- **VS Code**: Primary IDE
- **Terminal**: zsh (default on macOS)

### Database (Optional for MVP)

- **SQLite**: File-based database for simple storage
  - Why: No setup required, good for MVP
  - Installation: Built-in with Python
- **PostgreSQL**: Production-ready database
  - Installation: `brew install postgresql`
  - Python client: `pip install psycopg2`

### Deployment (Future)

- **Heroku**: Easy deployment for Python apps
- **Vercel**: For frontend components
- **Docker**: Containerization for consistent environments
  - Installation: `brew install docker`

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
└── README.md
```

## Installation Commands

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install fastapi uvicorn streamlit langchain openai requests pydantic python-dotenv cryptography

# Install development tools
pip install black flake8 mypy

# Run the application
# Backend: uvicorn app.main:app --reload
# Frontend: streamlit run ui/chat_app.py
```

## Prerequisites

- **Python 3.10+**: Check with `python --version`
- **VS Code**: Already installed
- **Git**: Already available
- **OpenAI API Key**: Obtain from https://platform.openai.com/
- **Splitwise API Access**: Register at https://dev.splitwise.com/

## Learning Resources

- **FastAPI**: https://fastapi.tiangolo.com/
- **LangChain**: https://python.langchain.com/
- **Streamlit**: https://docs.streamlit.io/
- **Splitwise API**: https://dev.splitwise.com/
- **OpenAI API**: https://platform.openai.com/docs

## Cost Considerations

- **OpenAI API**: ~$0.002 per 1K tokens for GPT-3.5, higher for GPT-4
- **Splitwise API**: Free for development
- **Hosting**: Free tiers available on Heroku/Vercel for MVP

## Security Notes

- Never commit API keys to Git
- Use environment variables for sensitive data
- Implement proper error handling to avoid exposing sensitive information
- Regular dependency updates for security patches
