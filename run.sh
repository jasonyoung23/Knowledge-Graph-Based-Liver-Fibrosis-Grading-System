#!/bin/bash

# Knowledge Graph Based Liver Fibrosis Grading System Runner
# Usage: ./run.sh [command] [options]

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
PROJECT_NAME="liver-fibrosis-grader"
BACKEND_PORT=8000
FRONTEND_PORT=3000
NEO4J_PORT=7474
NEO4J_BOLT_PORT=7687

# Docker image name
DOCKER_IMAGE="${PROJECT_NAME}:latest"

# Print colored output
print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Open URL in default browser
open_browser() {
    local url="$1"
    print_info "Opening $url in browser..."

    # Try different commands based on OS
    if command_exists open; then
        # macOS
        open "$url" 2>/dev/null &
    elif command_exists xdg-open; then
        # Linux
        xdg-open "$url" 2>/dev/null &
    elif command_exists start; then
        # Windows
        start "$url" 2>/dev/null &
    else
        print_warning "Could not automatically open browser. Please visit: $url"
    fi
}

# Check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Check system dependencies
check_dependencies() {
    local missing_deps=()
    local warnings=()

    if ! command_exists python3; then
        missing_deps+=("python3")
    fi

    # Check for pip (may be python3 -m pip on some systems)
    if ! command_exists pip && ! python3 -m pip --version >/dev/null 2>&1; then
        missing_deps+=("pip")
    fi

    # Node.js will be installed in virtual environment if not available globally
    # No warning needed - we'll install it during setup if missing

    if ! command_exists docker; then
        warnings+=("docker (optional, for Neo4j)")
    fi

    if ! command_exists docker-compose; then
        warnings+=("docker-compose (optional, for Neo4j)")
    fi

    if [ ${#missing_deps[@]} -ne 0 ]; then
        print_error "Missing required dependencies: ${missing_deps[*]}"
        echo ""
        print_info "Installation instructions:"
        for dep in "${missing_deps[@]}"; do
            case $dep in
                python3)
                    echo "  - Python 3: https://www.python.org/downloads/"
                    ;;
                pip)
                    echo "  - pip: python3 -m ensurepip --upgrade"
                    ;;
                node)
                    echo "  - Node.js: https://nodejs.org/ (includes npm)"
                    ;;
                npm)
                    echo "  - npm: Usually included with Node.js"
                    ;;
            esac
        done
        exit 1
    fi

    if [ ${#warnings[@]} -ne 0 ]; then
        print_warning "Optional dependencies not found: ${warnings[*]}"
        print_info "Neo4j will not be available. You can still run backend and frontend."
        echo ""
    fi
}

# Setup Python environment
setup_python() {
    if [ ! -d "venv" ]; then
        print_info "Creating Python virtual environment..."
        python3 -m venv venv
    fi

    print_info "Activating virtual environment and installing dependencies..."
    source venv/bin/activate
    pip install -r backend/requirements.txt
}

# Setup Node.js environment
setup_nodejs() {
    # Check if Node.js is available in virtual environment
    if ! command_exists node; then
        print_info "Installing Node.js in virtual environment..."
        source venv/bin/activate

        # Install nodeenv if not already installed
        if ! python -c "import nodeenv" 2>/dev/null; then
            pip install nodeenv
        fi

        # Install Node.js in virtual environment
        nodeenv -p --node=18.17.0

        # Reactivate virtual environment to get Node.js in PATH
        source venv/bin/activate

        print_success "Node.js installed in virtual environment"
    else
        print_info "Node.js already available"
    fi
}

setup_frontend() {
    # Ensure Node.js is available
    setup_nodejs

    if [ ! -d "frontend/node_modules" ]; then
        print_info "Installing frontend dependencies..."
        source venv/bin/activate
        cd frontend
        npm install
        cd ..
        print_success "Frontend dependencies installed"
    else
        print_info "Frontend dependencies already installed"
    fi
}

# Start Neo4j (using Docker)
start_neo4j() {
    if command_exists docker; then
        print_info "Checking Docker daemon..."

        # Check if Docker daemon is running
        if ! docker info >/dev/null 2>&1; then
            print_warning "Docker daemon is not running."
            echo ""
            print_info "🚀 To start all services including Neo4j, please:"
            echo "   1. Start Docker Desktop: open -a Docker"
            echo "   2. Wait for Docker to fully start (check with: docker ps)"
            echo "   3. Run this command again: ./run.sh start"
            echo ""
            print_info "⏭️  Continuing with backend and frontend only..."
            echo ""
            return 1
        fi

        print_info "Starting Neo4j with Docker..."

        # Clean up any existing neo4j containers
        if docker ps -a 2>/dev/null | grep -q neo4j; then
            print_info "Cleaning up existing Neo4j containers..."
            docker stop neo4j-liver kg_neo4j 2>/dev/null || true
            docker rm neo4j-liver kg_neo4j 2>/dev/null || true
        fi

        # Start Neo4j container
        print_info "Starting Neo4j container (this may take a moment to download image)..."
        local container_id
        if container_id=$(docker run -d \
            --name neo4j-liver \
            -p ${NEO4J_BOLT_PORT}:7687 \
            -p ${NEO4J_PORT}:7474 \
            -e NEO4J_AUTH=neo4j/password \
            neo4j:latest 2>/dev/null); then

            print_info "Waiting for Neo4j to initialize..."
            # Wait for Neo4j to be ready (check if port 7474 responds)
            local retries=0
            while [ $retries -lt 30 ]; do
                if curl -f http://localhost:${NEO4J_PORT} >/dev/null 2>&1; then
                    print_success "Neo4j started successfully!"
                    print_info "  - Neo4j Browser: http://localhost:${NEO4J_PORT}"
                    print_info "  - Neo4j Bolt: bolt://localhost:${NEO4J_BOLT_PORT}"
                    print_info "  - Default credentials: neo4j/password"
                    open_browser "http://localhost:${NEO4J_PORT}"
                    return 0
                fi
                sleep 2
                retries=$((retries + 1))
                echo -n "."
            done

            print_error "Neo4j container started but service didn't respond within 60 seconds."
            print_info "Container ID: $container_id"
            print_info "Check logs with: docker logs neo4j-liver"
            return 1
        else
            print_error "Failed to start Neo4j container."
            print_info "Check Docker status with: docker ps -a"
            return 1
        fi
    else
        print_warning "Docker not found. Neo4j will not be available."
        print_info "You can still use backend and frontend services."
        return 1
    fi
}

# Stop Neo4j
stop_neo4j() {
    if command_exists docker; then
        print_info "Stopping Neo4j container..."
        docker stop neo4j-liver || true
        docker rm neo4j-liver || true
        print_success "Neo4j stopped"
    fi
}

# Start backend
start_backend() {
    print_info "Starting backend server on port ${BACKEND_PORT}..."
    source venv/bin/activate
    cd backend
    # Set PYTHONPATH to include project root so backend can import modules from parent directory
    PYTHONPATH="${PYTHONPATH}:$(cd .. && pwd)" uvicorn app:app --reload --host 0.0.0.0 --port ${BACKEND_PORT}
}

# Start frontend
start_frontend() {
    print_info "Starting frontend on port ${FRONTEND_PORT}..."
    cd frontend
    npm run dev -- --port ${FRONTEND_PORT}
}

# Show help
show_help() {
    cat << EOF
${PROJECT_NAME} - Runner Script

USAGE:
    $0 start         Start all services (backend, frontend, neo4j)
    $0 stop          Stop all running services
    $0 test <file>   Test single case file

SERVICES:
    - Backend API: http://localhost:8000
    - API Docs: http://localhost:8000/docs
    - Frontend: http://localhost:3000
    - Neo4j Browser: http://localhost:7474 (requires Docker Desktop)

EOF
}

# Stop all services
stop_services() {
    print_info "Stopping all services..."

    # Stop Neo4j container
    if command_exists docker && docker ps 2>/dev/null | grep -q neo4j; then
        print_info "Stopping Neo4j container..."
        docker stop neo4j-liver 2>/dev/null || true
        docker rm neo4j-liver 2>/dev/null || true
        print_success "Neo4j stopped"
    else
        print_info "Neo4j container not running"
    fi

    # Stop backend processes (uvicorn)
    local backend_pids
    backend_pids=$(pgrep -f "uvicorn.*app:app" 2>/dev/null || true)
    if [ -n "$backend_pids" ]; then
        print_info "Stopping backend processes..."
        echo "$backend_pids" | xargs kill -TERM 2>/dev/null || true
        sleep 2
        # Force kill if still running
        echo "$backend_pids" | xargs kill -KILL 2>/dev/null || true
        print_success "Backend stopped"
    else
        print_info "Backend not running"
    fi

    # Stop frontend processes (vite)
    local frontend_pids
    frontend_pids=$(pgrep -f "vite.*--port" 2>/dev/null || true)
    if [ -n "$frontend_pids" ]; then
        print_info "Stopping frontend processes..."
        echo "$frontend_pids" | xargs kill -TERM 2>/dev/null || true
        sleep 1
        # Force kill if still running
        echo "$frontend_pids" | xargs kill -KILL 2>/dev/null || true
        print_success "Frontend stopped"
    else
        print_info "Frontend not running"
    fi

    print_success "All services stopped"
}

# Test single case
test_case() {
    local file_path="$1"
    if [ -z "$file_path" ]; then
        print_error "Please provide a file path"
        echo "Usage: $0 test <file_path>"
        exit 1
    fi

    if [ ! -f "$file_path" ]; then
        print_error "File not found: $file_path"
        exit 1
    fi

    print_info "Testing single case: $file_path"

    # Check if Neo4j is available
    if command_exists docker && command_exists docker-compose && docker ps | grep -q neo4j; then
        print_info "Neo4j is running. Will store results in database."
    else
        print_warning "Neo4j is not running. Processing will fail when trying to store results."
        print_info "Start Neo4j first with: docker run -d --name neo4j-liver -p 7474:7474 -p 7687:7687 -e NEO4J_AUTH=neo4j/password neo4j:latest"
        echo ""
    fi

    source venv/bin/activate
    if python3 next_version_ingest.py -i "$file_path"; then
        print_success "Case processing completed successfully"
    else
        print_error "Case processing failed. Check Neo4j connection or file format."
        exit 1
    fi
}

# Main command handling
main() {
    local command="$1"

    # Show help if no command provided
    if [ -z "$command" ]; then
        show_help
        exit 0
    fi

    shift

    case "$command" in
        start)
            check_dependencies
            setup_python
            setup_frontend
            FRONTEND_AVAILABLE=true

            # Start Neo4j if Docker is available
            if start_neo4j; then
                NEO4J_STARTED=true
            else
                NEO4J_STARTED=false
            fi

            # Start backend in background
            start_backend &
            BACKEND_PID=$!

            # Start frontend only if available
            if [ "$FRONTEND_AVAILABLE" = true ]; then
                start_frontend &
                FRONTEND_PID=$!
                print_info "  - Frontend: http://localhost:3000"
                # Give frontend a moment to start, then open browser
                (sleep 3 && open_browser "http://localhost:3000") &
            fi

            print_success "Services started successfully!"
            print_info "  - Backend API: http://localhost:8000"
            print_info "  - API Docs: http://localhost:8000/docs"

            if [ "$NEO4J_STARTED" = true ]; then
                print_info "  - Neo4j Browser: http://localhost:7474"
            fi

            if [ "$FRONTEND_AVAILABLE" = true ]; then
                print_info "Press Ctrl+C to stop all services"
                trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; stop_neo4j" INT
            else
                print_info "Press Ctrl+C to stop backend service"
                if [ "$NEO4J_STARTED" = true ]; then
                    trap "kill $BACKEND_PID 2>/dev/null; stop_neo4j" INT
                else
                    trap "kill $BACKEND_PID 2>/dev/null" INT
                fi
            fi

            wait
            ;;
        stop)
            stop_services
            ;;
        test)
            check_dependencies
            setup_python
            test_case "$@"
            ;;
        *)
            show_help
            ;;
    esac
}

# Run main function with all arguments
main "$@"
