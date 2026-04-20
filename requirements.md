# Project Requirements: Splitwise AI Agent

## Overview

This project implements an AI-powered agent that securely interacts with the Splitwise API through a natural language chatbot interface. The Minimum Viable Product (MVP) focuses on demonstrating agentic AI capabilities by allowing users to add and manage expenses via conversational commands, while ensuring API key security through a proxy mechanism.

## MVP Scope

The MVP will include the following core features:

### 1. Conversational Expense Management

- **Natural Language Input**: Users can describe expenses in plain English (e.g., "Add $45 for lunch with Mike and Sarah at Italian restaurant")
- **Expense Creation**: Automatically parse amount, description, participants, and date from user input
- **Basic Expense Retrieval**: Allow users to query recent expenses or balances

### 2. Agentic AI Implementation

- **Intent Recognition**: Use LLM to understand user requests and extract relevant expense data
- **API Integration**: Seamlessly call Splitwise API endpoints for expense operations
- **Error Handling**: Provide helpful feedback when requests fail or data is incomplete

### 3. Secure API Key Management

- **Proxy Architecture**: All Splitwise API calls go through a secure proxy
- **Key Storage**: Encrypted storage of user API keys
- **Access Control**: Ensure only authorized requests reach the Splitwise API

## Detailed Requirements

### Functional Requirements

#### User Interface

- **Chat Interface**: Simple web-based chat UI for user interaction
- **Message History**: Display conversation history with the AI agent
- **Expense Confirmation**: Show parsed expense details before submission for user approval

#### AI Agent Capabilities

- **Expense Parsing**: Extract from natural language:
  - Amount (currency and value)
  - Description
  - Participants (by name or Splitwise user ID)
  - Date (default to current date if not specified)
  - Split method (equal, exact amounts, percentages)
- **Context Awareness**: Remember user preferences and common participants
- **Multi-turn Conversations**: Handle follow-up questions and clarifications

#### Splitwise API Integration

- **Authentication**: Secure OAuth or API key-based authentication
- **Expense Operations**:
  - Create new expenses
  - Retrieve user expenses
  - Get group information
  - Handle currency conversion
- **Error Handling**: Graceful handling of API errors, rate limits, and invalid data

#### Security Requirements

- **API Key Protection**: Never expose user API keys in client-side code
- **HTTPS Only**: All communications must be encrypted
- **Input Validation**: Sanitize all user inputs to prevent injection attacks
- **Rate Limiting**: Implement reasonable limits to prevent API abuse

### Non-Functional Requirements

#### Performance

- **Response Time**: AI responses within 3-5 seconds
- **Concurrent Users**: Support at least 10 simultaneous users for MVP
- **API Latency**: Splitwise API calls should complete within reasonable time limits

#### Reliability

- **Error Recovery**: Automatic retry for transient failures
- **Data Consistency**: Ensure expense data integrity
- **Logging**: Comprehensive logging for debugging and monitoring

#### Usability

- **Intuitive Interface**: Clean, simple chat interface
- **Help Commands**: Built-in help and example commands
- **Feedback**: Clear success/error messages

#### Scalability

- **Modular Architecture**: Easy to add new features
- **Database Flexibility**: Support for different storage backends
- **API Extensibility**: Framework for adding more Splitwise features

## User Stories

1. **Expense Addition**
   - As a user, I want to say "Add $20 for coffee with Alice" so that a new expense is created in Splitwise
   - As a user, I want the bot to ask for clarification if information is missing

2. **Expense Query**
   - As a user, I want to ask "What are my recent expenses?" to see my latest transactions
   - As a user, I want to check "What's my balance with John?" to see outstanding amounts

3. **Security**
   - As a user, I want my Splitwise API key to be stored securely so that it's not compromised
   - As a user, I want all API calls to go through a secure proxy

## Acceptance Criteria

- [ ] Users can successfully add expenses via natural language chat
- [ ] AI agent correctly parses expense details from various input formats
- [ ] API keys are stored encrypted and never exposed to client
- [ ] Basic error handling for invalid inputs and API failures
- [ ] Simple web interface for chat interaction
- [ ] Integration with Splitwise API for expense creation and retrieval

## Future Enhancements (Post-MVP)

- Advanced expense analytics
- Group management features
- Multi-currency support
- Integration with other expense tracking apps
- Voice input capabilities
- Mobile app interface
