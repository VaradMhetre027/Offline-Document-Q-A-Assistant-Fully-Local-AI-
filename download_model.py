# download_model.py
import os
import sys
import time

def download_model():
    print('Starting model download...')
    try:
        # Set environment variables to avoid SSL issues
        os.environ['TRANSFORMERS_OFFLINE'] = '0'
        os.environ['HF_HUB_OFFLINE'] = '0'
        
        print('Downloading embedding model (this may take a few minutes)...')
        print('File size: ~90MB')
        
        # Import here to catch errors early
        from sentence_transformers import SentenceTransformer
        
        # Download with progress indication
        model = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')
        
        print('Model downloaded successfully!')
        print('Saving model locally for offline use...')
        
        # Create models directory if it doesn't exist
        os.makedirs('./models', exist_ok=True)
        model.save('./models/all-MiniLM-L6-v2')
        
        print('✓ Embedding model saved locally!')
        print(f'Model location: {os.path.abspath("./models/all-MiniLM-L6-v2")}')
        
        # Verify the model was saved
        if os.path.exists('./models/all-MiniLM-L6-v2'):
            print('✓ Model verification: SUCCESS')
            return True
        else:
            print('✗ Model verification: FAILED')
            return False
            
    except ImportError as e:
        print(f'✗ Import error: {e}')
        print('Please check if sentence-transformers is installed correctly.')
        return False
    except Exception as e:
        print(f'✗ Error downloading model: {e}')
        print('Please check your internet connection and try again.')
        return False

if __name__ == "__main__":
    success = download_model()
    sys.exit(0 if success else 1)