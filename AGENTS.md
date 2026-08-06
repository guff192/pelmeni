# 🤖 Multi-Agent System - Technical Documentation

## 🌟 Overview
This document defines the agent structure for a multi-agent system built using pi for custom agentic workflows. The system consists of specialized agents that collaborate to automate different phases of the software development lifecycle, with a focus on minimal context and efficient tool management.

## 🔧 Technology Stack

### Selected Approach: Python with LangGraph
The system uses Python with LangGraph as the foundation for building custom agentic workflows with pi, providing a robust and flexible platform for multi-agent collaboration.

**Primary Stack:**
- **Framework**: LangGraph for agent orchestration
- **Language**: Python 3.10+
- **Libraries**: pi SDK, LangChain, FastAPI, Pydantic
- **Use Case**: General-purpose agents, rapid prototyping

## 🎯 Context Management Approach

### Minimal Context Strategy
The system implements a minimal context approach to prevent context overflow:

#### Context Isolation
- **Isolated Agent Contexts**: Each agent operates with its own isolated context
- **Minimal Tool Sets**: Agents are provided only with tools relevant to their specific tasks
- **Structured Context Passing**: Context is passed between agents in structured formats

#### Overflow Prevention
- **Automatic Summarization**: Context is automatically summarized to prevent overflow
- **Retention Policies**: Context retention policies ensure only relevant information is maintained
- **Checkpointing**: Agent state is checkpointed for efficient context management

#### Tool Access Control
- **Granular Tool Access**: Tools are assigned to agents based on their role and requirements
- **Role-Based Access**: Different agent types have access to different tool sets
- **Dynamic Tool Loading**: Tools are loaded dynamically as needed

## 🔄 Decision Rationale

### Why Python with LangGraph
The decision to use Python with LangGraph for custom agentic workflows was based on several factors:

#### Clarity and Simplicity
- **Clearer Tooling**: pi provides more straightforward tools for building custom workflows
- **Flexible Architecture**: Easier to customize and extend for specific use cases
- **Better Documentation**: More comprehensive documentation for custom implementations

#### Context Management
- **Efficient Context Handling**: pi's token-efficient context compaction features
- **Overflow Prevention**: Built-in mechanisms for preventing context overflow
- **Summarization Capabilities**: Automatic context summarization and checkpointing

#### Development Experience
- **Rapid Prototyping**: Faster iteration and testing cycles
- **Debugging Tools**: Better debugging and monitoring capabilities
- **Community Support**: Larger community and more resources available

## 📚 Libraries and Frameworks

### Core Agent Development Libraries
- **LangGraph**: Primary framework for agent orchestration and workflow management
- **LangChain**: Advanced agent workflows, chains, and tool integration
- **Pydantic AI**: Data validation, settings management, and structured output handling

### Message Queue Integration
- **Redis Pub/Sub**: Lightweight pub/sub messaging for agent communication
- **RabbitMQ/Pika**: Robust message queue system with Python client
- **Apache Kafka**: Distributed event streaming platform
- **Celery**: Distributed task queue with scheduling capabilities

### Testing and Validation
- **Pytest**: Comprehensive testing framework for agent functionality
- **LangSmith Evaluations**: Agent performance evaluation and benchmarking
- **LangChain Evaluators**: Specialized testing for agent workflows

### OpenMP/Parallel Computing
- **pyomp/OMP4Py**: Python bindings for OpenMP parallel processing
- **Numba + OpenMP**: JIT compilation with OpenMP support for performance-critical agents
- **Python 3.13+ GIL Optional**: Native multi-threading capabilities in newer Python versions

### Extensions and Tools
- **LangGraph Visualizer**: Graph visualization for agent workflows
- **LangSmith**: Monitoring, debugging, and analytics platform
- **Community Plugins**: Various plugins for extended functionality

## 🗺️ Development Phases

### Phase 1: Understand Problem
**Purpose**: Agents analyze the problem statement, gather requirements, and identify constraints
**Key Activities**:
- Problem decomposition and scoping
- Requirements gathering and clarification
- Constraint identification and analysis
- Stakeholder needs assessment

### Phase 2: Defining Models
**Purpose**: Agents design data models, domain objects, and system abstractions
**Key Activities**:
- Entity-relationship modeling
- Data structure design
- State management definition
- API contract specification

### Phase 3: Defining Interfaces
**Purpose**: Agents define communication protocols, APIs, and integration points
**Key Activities**:
- API endpoint specification
- Message format definition
- Communication protocol selection
- Integration point identification

### Phase 4: Reviewing
**Purpose**: Agents conduct peer reviews, validate implementations, and ensure quality
**Key Activities**:
- Code review and feedback
- Test case validation
- Performance benchmarking
- Security and compliance checking

## 🛠️ Agent Types

### Investigator Agent
**Role**: Locates code, identifies patterns, finds definitions and references
**Tools**: grep, glob, lsp, read
**Output Format**: File-path-first, line-number-attached findings with backticked symbols

### Builder Agent
**Role**: Makes surgical edits to 1-2 files, implements features
**Tools**: edit, write, bash (limited)
**Output Format**: Concise change descriptions with verification status

### Reviewer Agent
**Role**: Reviews code for bugs, quality issues, and improvement opportunities
**Tools**: read, grep, lsp
**Output Format**: Issue findings with severity levels and suggested fixes

### Tester Agent
**Role**: Creates and executes test cases, validates functionality
**Tools**: bash, write, read
**Output Format**: Test results with pass/fail status and coverage metrics

## 🔧 Agent Communication

Agents communicate through a message queue system:
1. **Message Queue**: RabbitMQ or Kafka for reliable message delivery
2. **Shared State**: Central knowledge base accessible to all agents
3. **Direct Messaging**: Agent-to-agent communication via hub tool
4. **Tool Results**: Output from one agent becomes input to another
### Message Queue Implementation
- **Protocol**: AMQP 1.0 for interoperability
- **Topics**: Separate topics for different message types
- **Durability**: Persistent messages for reliability
- **Security**: TLS encryption and authentication
## 🚀 Deployment

### Hybrid Deployment Approach
The system supports a hybrid deployment model:

#### Cloud Component
- **Platform**: AWS/GCP/Azure
- **Services**: Containerized agents with auto-scaling
- **Management**: Kubernetes for orchestration
- **Use Case**: Production workloads, scalable services

#### Local Component
- **Environment**: Local development machines
- **Services**: Lightweight agent runtime
- **Management**: Docker Compose for local orchestration
- **Use Case**: Development, testing, debugging

#### Integration
- **Communication**: Secure VPN or direct API connections
- **Data Sync**: Periodic synchronization between cloud and local
- **Fallback**: Local agents can operate independently when cloud is unavailable


## 📋 Agent Discovery and Spawning

Agents are discovered through:
- Project-specific `.omp/agents` directory
- User-specific `~/.omp/agent/agents` directory
- Bundled agents (scout, builder, reviewer, tester, etc.)

Spawning mechanism:
- Main thread uses `task` tool with `tasks[]` batch for parallel execution
- Each agent gets isolated context with shared communication channels
- Results are collected and synthesized by the orchestrating agent

## 🧠 Core Business Logic

### Agent Lifecycle
1. **Initialization**: Agent receives task and context
2. **Execution**: Agent performs assigned work using available tools
3. **Communication**: Agent shares results via agreed-upon mechanisms
4. **Completion**: Agent signals completion and makes results available

### Coordination Patterns
- **Pipeline**: Output of one agent becomes input to next
- **Parallel**: Multiple agents work simultaneously on different aspects
- **Feedback Loop**: Agents review and refine each other's work
- **Consensus**: Multiple agents validate critical decisions

## 📱 Communication Tone
- **Style**: Technical, precise, action-oriented
- **Audience**: Developer-to-developer communication
- **Format**: Structured, scannable, minimal corporate jargon
