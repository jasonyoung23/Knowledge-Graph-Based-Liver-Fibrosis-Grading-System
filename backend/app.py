from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import os
from pathlib import Path
from typing import List, Dict, Any, Optional
from py2neo import Graph

# Import existing project functions
# Import parsing/grading/ingest lazily inside endpoints to avoid
# requiring optional LLM-related packages at server start.

DATA_DIR = Path(__file__).resolve().parents[1] / "data"

app = FastAPI(title="Pathology Ingest API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class TextIn(BaseModel):
    text: str


class StructIn(BaseModel):
    struct: Dict[str, Any]


class IngestIn(BaseModel):
    struct: Dict[str, Any]
    grading: Dict[str, Any]
    slice_hint: Optional[str] = None


class BatchProcessIn(BaseModel):
    files_to_process: Optional[List[str]] = None


def get_graph() -> Graph:
    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    user = os.getenv("NEO4J_USER", "neo4j")
    pwd = os.getenv("NEO4J_PASSWORD", "password")
    try:
        g = Graph(uri, auth=(user, pwd))
        # Test connection
        g.run("RETURN 1")
        return g
    except Exception as e:
        raise ValueError(f"Neo4j connection failed: {uri} - {e}")


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/neo4j/health")
def neo4j_health():
    try:
        g = get_graph()
        return {"ok": True, "message": "Neo4j connected"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.get("/api/cases")
def list_cases():
    files = []
    if DATA_DIR.exists():
        for p in sorted(DATA_DIR.glob("*.txt")):
            # Use relative path from data directory instead of cwd
            files.append({"name": p.name, "path": f"data/{p.name}"})
    return {"cases": files}


@app.get("/api/case/{name}/raw")
def get_case_raw(name: str):
    p = DATA_DIR / name
    if p.exists():
        return {"name": name, "raw": p.read_text(encoding="utf-8")}
    raise HTTPException(status_code=404, detail="case file not found")


@app.post("/api/case/upload")
async def upload_case(file: UploadFile = File(...)):
    try:
        # Only allow .txt files
        if not file.filename.endswith('.txt'):
            raise HTTPException(status_code=400, detail="Only .txt files allowed")
        
        # Save to data directory
        file_path = DATA_DIR / file.filename
        content = await file.read()
        file_path.write_bytes(content)
        return {"ok": True, "filename": file.filename, "path": str(file_path)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/case/{name}")
def delete_case(name: str):
    try:
        # Only allow deleting from data directory (not test)
        p = DATA_DIR / name
        if not p.exists():
            raise HTTPException(status_code=404, detail="case file not found")

        # Remove from UI only - don't delete the actual file
        # p.unlink()  # Comment out file deletion
        return {"ok": True, "message": f"Removed {name} from UI"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/case/parse")
def api_parse(body: TextIn):
    try:
        # lazy import to avoid top-level dependency on LLM packages
        from next_version_ingest import parse_case_text
        
        # Parse handles LLM normalization internally
        struct = parse_case_text(body.text)
        
        # Extract normalized text from struct
        normalized = struct.get("cn_norm", "")
        
        return {"ok": True, "normalized": normalized, "struct": struct}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/case/grade")
def api_grade(body: StructIn):
    try:
        from kg_grade import grade_case
        grading = grade_case(body.struct)
        return {"ok": True, "grading": grading}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/case/ingest")
def api_ingest(body: IngestIn):
    try:
        g = get_graph()
        from next_version_ingest import ingest_struct as ingest_struct_fn, extract_slice_id, ingest_decision_graph

        # compute slice id and case id (include optional slice_hint)
        sid = extract_slice_id(body.struct.get("cn_norm", "") or body.struct.get("raw", ""))
        case_id = f"{body.slice_hint}::{sid}" if body.slice_hint else sid

        # ingest the main nodes (Slice, Lesion, Feature, etc.)
        # Note: ingest_struct_fn only takes 3 params: graph, struct, grading
        ingest_struct_fn(g, body.struct, body.grading)

        # Build feature -> lesion mapping and add decision/grade graph (Grade/Rule/Evidence)
        try:
            feature_evidence: Dict[str, List[str]] = {}
            for lesion in body.struct.get("lesions", []):
                lid = lesion.get("lesion_id")
                for f in lesion.get("features", []):
                    feature_evidence.setdefault(f, []).append(lid)

            stage = body.grading.get("stage")
            if stage:
                ingest_decision_graph(g, sid, feature_evidence, stage)
        except Exception as e:
            print(f"[WARN] ingest_decision_graph failed for {case_id}: {e}")

        return {"ok": True, "slice_id": sid}
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        print(f"Ingest error: {e}\n{tb}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/batch-process")
def api_batch_process(body: BatchProcessIn):
    """Batch process specified .txt files or all files in data directory: parse -> grade -> ingest."""
    try:
        from next_version_ingest import parse_case_text, ingest_struct as ingest_struct_fn, extract_slice_id, ingest_decision_graph
        from kg_grade import grade_case

        results = []
        g = get_graph()

        if not DATA_DIR.exists():
            return {"ok": False, "error": "data directory not found"}

        if body.files_to_process:
            # 只处理指定的文件
            files = []
            for filename in body.files_to_process:
                file_path = DATA_DIR / filename
                if file_path.exists() and file_path.suffix == '.txt':
                    files.append(file_path)
        else:
            # 处理所有文件（向后兼容）
            files = sorted([p for p in DATA_DIR.glob("*.txt")])

        if not files:
            return {"ok": True, "results": [], "message": "No .txt files found to process"}

        for file_path in files:
            result = {"file": file_path.name, "status": "pending"}
            try:
                # Read raw text
                raw_text = file_path.read_text(encoding="utf-8")
                
                # Parse
                struct = parse_case_text(raw_text)
                struct["slice_id"] = file_path.stem
                
                # Grade
                grading = grade_case(struct)
                
                # Ingest
                sid = extract_slice_id(struct.get("cn_norm", "") or struct.get("raw", ""))
                case_id = f"{file_path.stem}::{sid}"
                
                # Call ingest_struct with correct signature (no slice_hint param)
                ingest_struct_fn(g, struct, grading)
                
                # Ingest decision graph
                try:
                    feature_evidence: Dict[str, List[str]] = {}
                    for lesion in struct.get("lesions", []):
                        lid = lesion.get("lesion_id")
                        for f in lesion.get("features", []):
                            feature_evidence.setdefault(f, []).append(lid)
                    
                    stage = grading.get("stage")
                    if stage:
                        ingest_decision_graph(g, sid, feature_evidence, stage)
                except Exception as e:
                    print(f"[WARN] ingest_decision_graph failed for {case_id}: {e}")
                
                result["status"] = "success"
                result["slice_id"] = sid
                result["grade"] = grading.get("stage")
            except Exception as e:
                result["status"] = "failed"
                result["error"] = str(e)
            
            results.append(result)
        
        return {"ok": True, "results": results, "total": len(files), "processed": sum(1 for r in results if r["status"] == "success")}
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        print(f"Batch error: {e}\n{tb}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/clear-database")
def api_clear_database():
    """Clear all data from Neo4j database"""
    try:
        g = get_graph()

        # Delete all nodes and relationships
        g.run("MATCH (n) DETACH DELETE n")

        # Optional: Clear schema constraints and indexes
        try:
            g.run("DROP CONSTRAINT slice_id IF EXISTS")
            g.run("DROP CONSTRAINT feature_name IF EXISTS")
            g.run("DROP CONSTRAINT staining_key IF EXISTS")
            g.run("DROP CONSTRAINT fibrosis_key IF EXISTS")
        except:
            pass  # Constraints might not exist, ignore errors

        return {"ok": True, "message": "Database cleared successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to clear database: {str(e)}")

@app.get("/api/report")
def api_report():
    try:
        import kg_report
        by_slice = kg_report.fetch_data()
        return {"ok": True, "by_slice": by_slice}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.app:app", host="0.0.0.0", port=8000, reload=True)
