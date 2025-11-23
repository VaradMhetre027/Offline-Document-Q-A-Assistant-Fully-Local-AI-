from flask import Flask, request, jsonify, send_from_directory, send_file
from flask_cors import CORS
import os
import json
import uuid
from datetime import datetime
import threading
import fitz
import numpy as np
import faiss
from sentence_transformers import SentenceTransformer
import ollama
import glob
import logging
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('app.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Set environment variables for strict offline mode
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["HF_DATASETS_OFFLINE"] = "1" 
os.environ["HF_HUB_OFFLINE"] = "1"

app = Flask(__name__, static_folder='.', static_url_path='')
CORS(app)

CONFIG = {
    "embedding_model": "all-MiniLM-L6-v2",
    "local_embedding_model_path": "./models/all-MiniLM-L6-v2",
    "ollama_model": "llama3:latest",  # Fixed: using exact model name
    "top_k": 5,
    "upload_folder": "uploads",
    "data_folder": "data",
    "index_folder": "indexed_documents"
}

class OfflineModelManager:
    """Manages offline model loading and validation"""
    
    @staticmethod
    def validate_environment():
        """Check if all required components are available for offline operation"""
        issues = []
        
        # Check if models directory exists
        if not Path("models").exists():
            issues.append("Models directory not found. Run setup.bat first.")
            return issues
        
        # Check if embedding model exists locally
        if not Path(CONFIG["local_embedding_model_path"]).exists():
            issues.append(f"Embedding model not found at {CONFIG['local_embedding_model_path']}. Run setup.bat to download models.")
        
        # Check if Ollama is available and model exists
        try:
            ollama_list = ollama.list()
            available_models = ollama_list.get('models', [])
            
            # Check for llama3 model with different naming patterns
            found_model = None
            for model in available_models:
                model_name = model.get('name', '')
                # Check for various llama3 naming patterns
                if any(pattern in model_name for pattern in ['llama3:latest', 'llama3', 'llama3:']):
                    found_model = model_name
                    break
            
            if found_model:
                # Update config to use the exact model name found
                CONFIG["ollama_model"] = found_model
                logger.info(f"Using Ollama model: {found_model}")
            else:
                # List available models for debugging
                available_names = [model.get('name', 'unknown') for model in available_models]
                issues.append(f"Llama3 model not found. Available models: {', '.join(available_names)}")
                    
        except Exception as e:
            issues.append(f"Ollama not accessible: {e}. Make sure Ollama is installed and running.")
        
        return issues

class DocumentProcessor:
    def __init__(self):
        self.embedder = None
        self.current_index = None
        self.current_paragraphs = []
        self.load_embedding_model()
        self.load_existing_index()
    
    def load_embedding_model(self):
        """Load embedding model from local storage only"""
        try:
            local_model_path = CONFIG["local_embedding_model_path"]
            
            # Check if local model exists
            if not os.path.exists(local_model_path):
                logger.error(f"Local model not found at {local_model_path}")
                logger.error("Please run setup.bat first to download models")
                raise FileNotFoundError(f"Local model not found. Run setup.bat to download models.")
            
            logger.info(f"Loading embedding model from local cache: {local_model_path}")
            self.embedder = SentenceTransformer(local_model_path)
            logger.info("✓ Embedding model loaded successfully from local cache")
            
        except Exception as e:
            logger.error(f"Failed to load embedding model: {e}")
            # Provide helpful error message
            print("\n" + "="*60)
            print("OFFLINE MODEL LOADING ERROR")
            print("="*60)
            print("To fix this issue:")
            print("1. Connect to the internet")
            print("2. Run 'setup.bat' to download models")
            print("3. Then you can run offline anytime!")
            print("="*60)
            raise
    
    def load_existing_index(self):
        """Load the most recent index on startup"""
        try:
            # Ensure index folder exists
            os.makedirs(CONFIG["index_folder"], exist_ok=True)
            
            index_files = glob.glob(os.path.join(CONFIG["index_folder"], "*.json"))
            if index_files:
                # Get the most recent index file
                latest_file = max(index_files, key=os.path.getctime)
                session_id = os.path.basename(latest_file).replace('.json', '')
                logger.info(f"Loading existing index: {session_id}")
                self.load_index(session_id)
                return session_id
            else:
                logger.info("No existing indexes found. Ready for new document uploads.")
        except Exception as e:
            logger.error(f"Error loading existing index: {e}")
        return None
    
    def extract_text_from_pdf(self, pdf_path):
        paragraphs = []
        try:
            doc = fitz.open(pdf_path)
            for page_num, page in enumerate(doc):
                text = page.get_text()
                if text.strip():
                    raw_paragraphs = text.split('\n\n')
                    for para in raw_paragraphs:
                        clean_para = para.strip()
                        if len(clean_para) > 20:
                            paragraphs.append({
                                "text": clean_para,
                                "page": page_num + 1,
                                "source": os.path.basename(pdf_path),
                                "file_name": os.path.basename(pdf_path)
                            })
            doc.close()
            logger.info(f"Extracted {len(paragraphs)} paragraphs from {os.path.basename(pdf_path)}")
        except Exception as e:
            logger.error(f"Error processing PDF {pdf_path}: {e}")
        return paragraphs
    
    def create_index(self, paragraphs, session_id):
        if not paragraphs:
            logger.warning("No paragraphs to index")
            return False
        
        try:
            texts = [p["text"] for p in paragraphs]
            logger.info(f"Creating embeddings for {len(texts)} paragraphs...")
            embeddings = self.embedder.encode(texts, convert_to_numpy=True)
            embeddings = np.asarray(embeddings, dtype=np.float32)
            
            dim = embeddings.shape[1]
            index = faiss.IndexFlatL2(dim)
            index.add(embeddings)
            
            # Save index data
            os.makedirs(CONFIG["index_folder"], exist_ok=True)
            index_data_file = os.path.join(CONFIG["index_folder"], f"{session_id}.json")
            
            index_data = {
                "paragraphs": paragraphs,
                "embeddings_shape": embeddings.shape,
                "files": list(set([p["file_name"] for p in paragraphs])),
                "created_at": datetime.now().isoformat(),
                "paragraph_count": len(paragraphs)
            }
            
            with open(index_data_file, 'w', encoding='utf-8') as f:
                json.dump(index_data, f, ensure_ascii=False, indent=2)
            
            # Save FAISS index
            faiss_index_file = os.path.join(CONFIG["index_folder"], f"{session_id}.faiss")
            faiss.write_index(index, faiss_index_file)
            
            self.current_index = index
            self.current_paragraphs = paragraphs
            
            logger.info(f"Created index for session {session_id} with {len(paragraphs)} paragraphs")
            return True
            
        except Exception as e:
            logger.error(f"Index creation error: {e}")
            return False
    
    def load_index(self, session_id):
        try:
            index_data_file = os.path.join(CONFIG["index_folder"], f"{session_id}.json")
            faiss_index_file = os.path.join(CONFIG["index_folder"], f"{session_id}.faiss")
            
            if os.path.exists(index_data_file) and os.path.exists(faiss_index_file):
                with open(index_data_file, 'r', encoding='utf-8') as f:
                    index_data = json.load(f)
                
                self.current_index = faiss.read_index(faiss_index_file)
                self.current_paragraphs = index_data["paragraphs"]
                
                logger.info(f"Loaded index {session_id} with {len(self.current_paragraphs)} paragraphs")
                return True
            else:
                logger.warning(f"Index files not found for session: {session_id}")
        except Exception as e:
            logger.error(f"Error loading index {session_id}: {e}")
        return False
    
    def get_available_indexes(self):
        """Get list of all available indexes"""
        indexes = []
        try:
            os.makedirs(CONFIG["index_folder"], exist_ok=True)
            index_files = glob.glob(os.path.join(CONFIG["index_folder"], "*.json"))
            for file_path in index_files:
                session_id = os.path.basename(file_path).replace('.json', '')
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    indexes.append({
                        'session_id': session_id,
                        'files': data.get('files', []),
                        'created_at': data.get('created_at'),
                        'paragraph_count': data.get('paragraph_count', 0)
                    })
            # Sort by creation date (newest first)
            indexes.sort(key=lambda x: x.get('created_at', ''), reverse=True)
        except Exception as e:
            logger.error(f"Error getting available indexes: {e}")
        return indexes
    
    def find_similar_paragraphs(self, query, top_k=5):
        if not self.current_index or not self.current_paragraphs:
            return []
        
        try:
            q_vec = self.embedder.encode([query], convert_to_numpy=True)
            q_vec = np.asarray(q_vec, dtype=np.float32)
            D, I = self.current_index.search(q_vec, top_k)
            
            results = []
            for idx in I[0]:
                if 0 <= idx < len(self.current_paragraphs):
                    results.append(self.current_paragraphs[idx])
            return results
        except Exception as e:
            logger.error(f"Search error: {e}")
            return []
    
    def query_documents(self, question):
        if not self.current_index:
            return "No documents are loaded. Please upload PDF files first."
        
        results = self.find_similar_paragraphs(question, CONFIG["top_k"])
        if not results:
            return "I couldn't find relevant information in the documents to answer your question."
        
        context_parts = []
        for i, r in enumerate(results, 1):
            source = r.get('source', 'Unknown Document')
            page = r.get('page', 'Unknown Page')
            context_parts.append(f"Source {i}: {source} (Page {page})\n{r['text']}\n")
        
        combined_context = "\n".join(context_parts)
        
        prompt = f"""You are a helpful AI assistant. Use the provided context to answer the user's question thoroughly and in detail.

CONTEXT FROM DOCUMENTS:
{combined_context}

USER QUESTION: {question}

INSTRUCTIONS:
1. Provide a comprehensive, detailed answer based ONLY on the context above
2. If the answer cannot be fully found in the context, say what information is available and what is missing
3. Be specific and include relevant details from the context
4. Use proper formatting and structure in your response
5. If referring to specific documents, mention the source and page numbers when available

ANSWER:"""
        
        try:
            response = ollama.chat(
                model=CONFIG["ollama_model"],
                messages=[{"role": "user", "content": prompt}],
                options={
                    'num_predict': 2048,
                    'temperature': 0.3,
                    'top_k': 40,
                    'top_p': 0.9
                }
            )
            return response['message']['content']
        except Exception as e:
            logger.error(f"Ollama query error: {e}")
            return f"Error generating response: {str(e)}"

# Initialize document processor
doc_processor = DocumentProcessor()
chat_sessions = {}

@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint to verify offline status"""
    environment_issues = OfflineModelManager.validate_environment()
    
    return jsonify({
        'status': 'healthy' if not environment_issues else 'issues_detected',
        'offline_mode': True,
        'environment_issues': environment_issues,
        'embedding_model_loaded': doc_processor.embedder is not None,
        'current_index_loaded': doc_processor.current_index is not None
    })

@app.route('/uploads', methods=['POST'])
def upload_documents():
    try:
        if 'files' not in request.files:
            return jsonify({'error': 'No files provided'}), 400
        
        files = request.files.getlist('files')
        if not files or files[0].filename == '':
            return jsonify({'error': 'No files selected'}), 400
        
        session_id = str(uuid.uuid4())
        session_folder = os.path.join(CONFIG["upload_folder"], session_id)
        os.makedirs(session_folder, exist_ok=True)
        
        saved_files = []
        all_paragraphs = []
        
        for file in files:
            if file and file.filename.lower().endswith('.pdf'):
                filename = file.filename
                file_path = os.path.join(session_folder, filename)
                file.save(file_path)
                saved_files.append(filename)
                
                paragraphs = doc_processor.extract_text_from_pdf(file_path)
                all_paragraphs.extend(paragraphs)
        
        def index_in_background():
            try:
                seen_texts = set()
                unique_paragraphs = []
                for para in all_paragraphs:
                    if para["text"] not in seen_texts:
                        seen_texts.add(para["text"])
                        unique_paragraphs.append(para)
                
                success = doc_processor.create_index(unique_paragraphs, session_id)
                
                chat_sessions[session_id] = {
                    'id': session_id,
                    'files': saved_files,
                    'indexed': success,
                    'created_at': datetime.now().isoformat(),
                    'chat_history': []
                }
                
                logger.info(f"Indexing complete for session {session_id}. Success: {success}")
            except Exception as e:
                logger.error(f"Background indexing error: {e}")
        
        threading.Thread(target=index_in_background).start()
        
        return jsonify({
            'session_id': session_id,
            'message': f'Successfully uploaded {len(saved_files)} document(s). Processing...',
            'documents': saved_files,
            'paragraphs_extracted': len(all_paragraphs)
        })
        
    except Exception as e:
        logger.error(f"Upload error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/query', methods=['POST'])
def query_documents():
    try:
        data = request.get_json()
        question = data.get('question', '').strip()
        session_id = data.get('session_id')
        
        if not question:
            return jsonify({'error': 'No question provided'}), 400
        
        response = doc_processor.query_documents(question)
        
        if session_id and session_id in chat_sessions:
            chat_sessions[session_id]['chat_history'].append({
                'question': question,
                'answer': response,
                'timestamp': datetime.now().isoformat()
            })
        
        return jsonify({
            'response': response,
            'session_id': session_id
        })
        
    except Exception as e:
        logger.error(f"Query error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/load_index', methods=['POST'])
def load_index():
    try:
        data = request.get_json()
        session_id = data.get('session_id')
        
        if doc_processor.load_index(session_id):
            return jsonify({
                'success': True,
                'message': 'Index loaded successfully',
                'session_id': session_id
            })
        else:
            return jsonify({'error': 'Failed to load index'}), 400
            
    except Exception as e:
        logger.error(f"Load index error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/export_chat', methods=['POST'])
def export_chat():
    try:
        data = request.get_json()
        session_id = data.get('session_id')
        chat_messages = data.get('chat_messages', [])
        
        if not chat_messages:
            return jsonify({'error': 'No chat messages to export'}), 400
        
        export_text = "Document Q&A Chat Export\n"
        export_text += "=" * 50 + "\n"
        export_text += f"Export Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        export_text += "Mode: OFFLINE (Local AI Models)\n"
        
        if session_id and session_id in chat_sessions:
            session_data = chat_sessions[session_id]
            export_text += f"Session ID: {session_id}\n"
            export_text += f"Documents: {', '.join(session_data['files'])}\n"
        
        export_text += "=" * 50 + "\n\n"
        
        for i, msg in enumerate(chat_messages, 1):
            if msg.get('type') == 'user':
                export_text += f"Q{i}: {msg.get('content', '')}\n\n"
            elif msg.get('type') == 'bot':
                export_text += f"A{i}: {msg.get('content', '')}\n"
                export_text += "-" * 40 + "\n\n"
        
        os.makedirs('exports', exist_ok=True)
        filename = f"chat_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        filepath = os.path.join('exports', filename)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(export_text)
        
        return jsonify({
            'success': True,
            'message': 'Chat exported successfully',
            'filename': filename,
            'filepath': filepath
        })
        
    except Exception as e:
        logger.error(f"Export chat error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/download_export/<filename>')
def download_export(filename):
    try:
        return send_file(os.path.join('exports', filename), as_attachment=True)
    except Exception as e:
        logger.error(f"Download export error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/list_indexes', methods=['GET'])
def list_indexes():
    try:
        indexes = doc_processor.get_available_indexes()
        current_files = []
        if doc_processor.current_paragraphs:
            current_files = list(set([p.get('file_name', '') for p in doc_processor.current_paragraphs]))
        
        return jsonify({
            'indexes': indexes,
            'current_files': current_files,
            'has_loaded_index': doc_processor.current_index is not None,
            'offline_mode': True
        })
    except Exception as e:
        logger.error(f"List indexes error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/current_index', methods=['GET'])
def current_index():
    current_files = []
    if doc_processor.current_paragraphs:
        current_files = list(set([p.get('file_name', '') for p in doc_processor.current_paragraphs]))
    
    return jsonify({
        'has_loaded_index': doc_processor.current_index is not None,
        'current_files': current_files,
        'paragraph_count': len(doc_processor.current_paragraphs) if doc_processor.current_paragraphs else 0,
        'offline_mode': True
    })

@app.route('/system_status', methods=['GET'])
def system_status():
    """Comprehensive system status endpoint"""
    environment_issues = OfflineModelManager.validate_environment()
    
    return jsonify({
        'offline_mode': True,
        'environment_issues': environment_issues,
        'system_ready': len(environment_issues) == 0,
        'embedding_model_loaded': doc_processor.embedder is not None,
        'current_index_loaded': doc_processor.current_index is not None,
        'current_paragraph_count': len(doc_processor.current_paragraphs) if doc_processor.current_paragraphs else 0,
        'available_indexes': len(doc_processor.get_available_indexes())
    })

if __name__ == '__main__':
    # Create necessary directories
    os.makedirs(CONFIG["upload_folder"], exist_ok=True)
    os.makedirs(CONFIG["data_folder"], exist_ok=True)
    os.makedirs(CONFIG["index_folder"], exist_ok=True)
    os.makedirs('exports', exist_ok=True)
    os.makedirs('models', exist_ok=True)
    
    # Print startup banner
    print("\n" + "="*60)
    print("       DOCUMENT Q&A SYSTEM - OFFLINE MODE")
    print("="*60)
    print("✓ Running completely offline")
    print("✓ Using locally cached models") 
    print("✓ No internet connection required")
    print("="*60)
    
    # Validate environment
    environment_issues = OfflineModelManager.validate_environment()
    if environment_issues:
        print("\n⚠️  ENVIRONMENT ISSUES DETECTED:")
        for issue in environment_issues:
            print(f"   - {issue}")
        print("\n💡 SOLUTION: Run 'setup.bat' with internet connection first")
        print("="*60)
    else:
        print("✓ All systems ready for offline operation")
        print("="*60)
    
    print("Starting Document Q&A Web Server...")
    print("Access the application at: http://localhost:5001")
    print("Health check: http://localhost:5001/health")
    app.run(host='0.0.0.0', port=5001, debug=False)