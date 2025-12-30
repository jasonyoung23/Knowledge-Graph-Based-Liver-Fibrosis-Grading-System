# Pathology Case Parser & Grader

A comprehensive web application for parsing, grading, and ingesting pathology case data using rule-based Ishak fibrosis grading with optional LLM-powered case normalization.

## 🎯 Features

- **Case Parsing**: Extract structured information from raw pathology reports (patient data, staining quality, fibrosis level, lesions)
- **Intelligent Feature Extraction**: Rule-based + optional LLM feature detection (假小叶, 桥接, 汇管区纤维化, etc.)
- **Ishak Fibrosis Grading**: Rule-based F0-F6 staging with evidence-grounded reasoning
- **Neo4j Graph Ingestion**: Store cases, lesions, features, and grading relationships in a knowledge graph
- **Batch Processing**: Process multiple case files in one operation
- **File Management**: Upload, view, and delete case files via web interface
- **RESTful API**: FastAPI backend with comprehensive endpoints

## 🏗️ Architecture

### Backend
- **FastAPI** - REST API server
- **py2neo** - Neo4j Python driver for graph operations
- **Ollama** (optional) - Local LLM for case normalization and explanations

### Frontend
- **React 18** - UI framework
- **Vite** - Build tool and dev server
- **Fetch API** - HTTP client for API communication

### Database
- **Neo4j** - Graph database for storing pathology knowledge
  - Nodes: Slice, Lesion, Feature, Grade, Evidence, Rule, Metadata, Staining, Fibrosis
  - Relationships: HAS_LESION, HAS_FEATURE, HAS_GRADE, HAS_EVIDENCE, TRIGGERS, SUPPORTS

## 📋 Prerequisites

- Python 3.9+
- Node.js 14+
- Neo4j 4.0+ (local or remote)
- (Optional) Ollama with qwen2.5:14b-instruct model

## 🏃 Quick Start

### Option 1: Using Docker (Recommended)

1. **Prerequisites**: Install Docker and Docker Compose
2. **Clone and run**:
   ```bash
   git clone <your-repo-url>
   cd liver-fibrosis-grading-system
   ./run.sh docker-build
   ./run.sh docker-init    # Initialize Ollama models (optional)
   ./run.sh docker-start
   ```
3. **Access the application**:
   - Frontend: http://localhost:3000
   - Backend API: http://localhost:8000
   - API Docs: http://localhost:8000/docs
   - Neo4j Browser: http://localhost:7474

### Option 2: Using run.sh Script

1. **Prerequisites**: Python 3.9+, Node.js 14+, Docker
2. **Setup and run**:
   ```bash
   git clone <your-repo-url>
   cd liver-fibrosis-grading-system
   ./run.sh setup          # Setup environments
   ./run.sh start          # Start all services
   ```
3. **Batch processing**:
   ```bash
   ./run.sh batch          # Process all case files
   ./run.sh process data/case1.txt  # Process single file
   ```

### Available run.sh Commands

```bash
./run.sh setup           # Setup Python and Node.js environments
./run.sh start           # Start all services (backend, frontend, neo4j)
./run.sh stop            # Stop all services
./run.sh backend         # Start only backend server
./run.sh frontend        # Start only frontend server
./run.sh neo4j           # Start Neo4j database
./run.sh batch           # Batch process all case files
./run.sh process <file>  # Process a single case file
./run.sh docker-build    # Build Docker image
./run.sh docker-start    # Start services with Docker Compose
./run.sh docker-stop     # Stop Docker services
./run.sh docker-init     # Initialize Ollama models
./run.sh docker-batch    # Run batch processing with Docker
./run.sh logs [service]  # Show logs (all services or specific service)
./run.sh cleanup         # Clean up environments and containers
./run.sh help            # Show help message
```

## 🚀 Manual Installation

*(For advanced users or development)*

### 1. Clone Repository
```bash
git clone <your-repo-url>
cd src
```

### 2. Install Python Dependencies
```bash
pip install -r requirements.txt
```

**Key dependencies:**
- fastapi
- uvicorn
- py2neo==2021.2.4
- requests
- openai

### 3. Install Frontend Dependencies
```bash
cd frontend
npm install
cd ..
```

### 4. Setup Environment Variables (Optional)
Create a `.env` file in the project root (only needed for manual setup):

```bash
# Neo4j Configuration
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=password

# LLM Configuration (Optional)
# For Docker setup (recommended)
LLM_ENDPOINT=http://ollama:11434/v1/chat/completions
LLM_MODEL=qwen2.5:14b-instruct

# For local Ollama installation
# LLM_ENDPOINT=http://localhost:11434/v1/chat/completions

# For remote LLM service
# LLM_ENDPOINT=http://202.120.40.86:11445/v1/chat/completions
```

## 🔧 Configuration

### Neo4j Setup

**Option 1: Homebrew (macOS/Linux)**
```bash
# Install
brew install neo4j

# Start service
brew services start neo4j

# Change password (default: neo4j)
# Visit http://localhost:7474 and set new password
```

**Option 2: Docker**
```bash
docker run -d \
  --name neo4j \
  -p 7687:7687 \
  -p 7474:7474 \
  -e NEO4J_AUTH=neo4j/your_password \
  neo4j:latest
```

### LLM Setup (Optional)

**Using Docker** (recommended):
```bash
./run.sh docker-init    # Initialize Ollama with required models
```

**Manual setup**:
If you have Ollama running locally:
```bash
# Update LLM_ENDPOINT in .env
LLM_ENDPOINT=http://localhost:11434/v1/chat/completions
```

To disable LLM (use rule-based only):
```python
# In next_version_ingest.py
USE_LLM = False
```

### Docker Configuration

The project includes comprehensive Docker support:

- **Multi-stage builds** for optimized images
- **docker-compose.yml** with all services (backend, frontend, neo4j, ollama)
- **Automated model initialization** for Ollama
- **Health checks** for all services
- **Volume persistence** for databases

**Service Ports**:
- Frontend: 3000
- Backend API: 8000
- Neo4j Browser: 7474
- Neo4j Bolt: 7687
- Ollama API: 11434

## ▶️ Running the Application

*(See [Quick Start](#-quick-start) section above for recommended methods)*

### Manual Startup (Alternative)

#### Start Backend
```bash
# From project root
uvicorn backend.app:app --reload --port 8000
```

Backend will be available at: `http://localhost:8000`

#### Start Frontend
```bash
cd frontend
npm run dev -- --port 3000
```

Frontend will be available at: `http://localhost:3000`

#### View API Documentation
Once backend is running, visit: `http://localhost:8000/docs` (Swagger UI)

## 📖 Usage Guide

### 1. Upload Case Files

1. Open web interface: `http://localhost:3000`
2. Click **📤 Upload .txt** button in the left sidebar
3. Select pathology report text files (.txt format)
4. Files are saved to `data/` directory

### 2. Parse a Case

1. Select a case from the list (left panel)
2. Click **Parse** button
3. View LLM-normalized case text in right panel
4. System automatically extracts: patient info, staining quality, fibrosis level, lesions, features

### 3. Grade a Case

1. After parsing, click **Grade** button
2. System applies Ishak rules to determine F-stage (F0-F6)
3. View grading result with medical reasoning

### 4. Ingest to Neo4j

1. After grading, click **Ingest** button
2. Data is stored in Neo4j graph database
3. Creates nodes: Slice, Lesion, Feature, Grade, Evidence, Rule

### 5. Batch Process All Cases

1. Click green **▶ Run All Cases** button in left sidebar
2. System sequentially: parses → grades → ingests all files
3. View results with status, grades, and errors
4. Results show: file name, status (success/failed), F-stage, and error details

### 6. View Neo4j Graph

Visit Neo4j Browser: `http://localhost:7474`

Example queries:
```cypher
// View all grades
MATCH (s:Slice)-[:HAS_GRADE]->(g:Grade) RETURN s.id, g.stage

// Find evidence for specific feature
MATCH (e:Evidence {feature: "桥接"})-[:SUPPORTS]->(g:Grade) RETURN e, g

// Get full case with lesions and features
MATCH (s:Slice {id: "case1"})-[:HAS_LESION]->(l:Lesion)-[:HAS_FEATURE]->(f:Feature) 
RETURN s, l, f
```

## 🗂️ File Structure

```
├── backend/                    # FastAPI backend application
│   ├── app.py                  # Main FastAPI application
│   └── requirements.txt        # Python dependencies
├── frontend/                   # React frontend application
│   ├── src/
│   │   ├── pages/
│   │   │   ├── CaseList.jsx    # Case list + batch processing UI
│   │   │   └── CaseView.jsx    # Case detail + parse/grade/ingest
│   │   └── services/
│   │       └── api.js          # API client wrapper
│   ├── package.json
│   └── vite.config.js
├── data/                       # Case files (uploaded/managed)
│   ├── case1.txt
│   ├── case2.txt
│   └── ...
├── run.sh                      # Main runner script
├── Dockerfile                  # Docker image definition
├── docker-compose.yml          # Multi-service Docker configuration
├── init-ollama.sh              # Ollama model initialization script
├── .dockerignore               # Docker ignore file
├── next_version_ingest.py      # Core parsing & ingestion logic
├── kg_grade.py                 # Ishak grading rules & LLM explanation
├── kg_ingest_cn.py             # Batch ingestion script
├── kg_report.py                # Report generation (optional)
├── requirements.txt            # Legacy Python dependencies
└── README.md                   # This file
```

## 🔌 API Endpoints

### Health Checks
- `GET /api/health` - Server health
- `GET /api/neo4j/health` - Neo4j connection status

### Case Management
- `GET /api/cases` - List all case files
- `GET /api/case/{name}/raw` - Get raw case text
- `POST /api/case/upload` - Upload new case file
- `DELETE /api/case/{name}` - Delete case file

### Processing
- `POST /api/case/parse` - Parse case text
- `POST /api/case/grade` - Grade structured case
- `POST /api/case/ingest` - Ingest to Neo4j
- `POST /api/batch-process` - Batch process all files

### Reports
- `GET /api/report` - Generate summary report

## 📊 Case Text Format

Expected pathology report format:

```
患者信息: 女, 50岁; 乙肝携带者
切片染色质量: 优
切片整体纤维化程度: 中-高

病灶列举:
病灶1: 假小叶结构，局部纤维隔增厚
病灶2: 桥接纤维化，门-门连接明显
病灶3: 汇管区纤维化，炎症活动轻度
```

The system is flexible and handles various formats with pattern matching.

## 🐛 Troubleshooting

### Neo4j Connection Error
```
Error: Neo4j connection failed: bolt://localhost:7687
```
**Solution:**
- Ensure Neo4j is running: `brew services list` or `docker ps`
- Check URI, username, password in `.env`
- Test connection: `neo4j-admin dbms test-connection`

### LLM 502 Error
```
[WARN] LLM normalize failed: Ollama API error 502
```
**Solution:**
- Ollama service is unavailable (expected if not running)
- System will gracefully fallback to rule-based processing
- No impact on functionality; set `USE_LLM = False` to disable

### Frontend Port Already in Use
```
Error: Port 3000 is already in use
```
**Solution:**
```bash
# Use different port
npm run dev -- --port 3001
```

### Backend Import Errors
```
ModuleNotFoundError: No module named 'openai'
```
**Solution:**
```bash
pip install -r requirements.txt
```

## 📝 Example Workflow

1. **Prepare**: Add `.txt` case files to `data/` or upload via UI
2. **Parse**: Extract structured data from free-text reports
3. **Grade**: Apply Ishak rules for F0-F6 staging
4. **Ingest**: Store in Neo4j with evidence relationships
5. **Analyze**: Query Neo4j to extract insights

```bash
# Using run.sh (recommended)
./run.sh process data/case1.txt    # Process single file
./run.sh batch                     # Process all files
./run.sh docker-batch              # Process with Docker

# Or direct CLI (requires manual environment setup)
python3 next_version_ingest.py -i data/case1.txt
python3 next_version_ingest.py -i data/*.txt
```

## 🔐 Security Notes

- Keep `NEO4J_PASSWORD` secure; don't commit `.env` to git
- Frontend CORS is restricted to `localhost:3000` (update in `backend/app.py` for production)
- File uploads are limited to `.txt` format only

## 📚 Key Modules

### `next_version_ingest.py`
- **L1 Parse Layer**: `parse_case_text()` - Text → Structured dict
- **Normalization**: `normalize_case_with_llm()` - LLM case restructuring
- **Feature Extraction**: `find_features_llm()` / `find_features_cn()` - Detect pathology features
- **Ingestion**: `ingest_struct()` - Create graph nodes
- **Decision Graph**: `ingest_decision_graph()` - Create Grade/Evidence/Rule nodes

### `kg_grade.py`
- **Evidence Building**: `build_feature_evidence()` - Map features to lesions
- **Rule-Based Grading**: `rule_based_ishak_grade()` - F0-F6 determination
- **LLM Explanation**: `explain_with_llm()` - Medical reasoning
- **Main Entry**: `grade_case()` - Comprehensive grading

### `backend/app.py`
- RESTful endpoints wrapping core functions
- Neo4j connection management
- Error handling and logging

## 🤝 Contributing

Contributions welcome! Areas for enhancement:
- Additional grading systems (METAVIR, Brunt)
- Advanced query builder UI
- Batch result export (CSV)
- Docker Compose for full stack
- Unit tests

## 📄 License

[Add your license here]

## 📧 Support

For issues or questions, open a GitHub issue or contact the maintainers.

---

**Last Updated**: December 2025
**Version**: 1.0
