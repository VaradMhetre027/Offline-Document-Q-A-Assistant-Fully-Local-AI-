# test_ollama.py
import ollama

try:
    print("Testing Ollama connection...")
    models = ollama.list()
    print("Available models:")
    for model in models.get('models', []):
        print(f"  - {model.get('name', 'unknown')}")
        
    # Test if we can use a model
    print("\nTesting model response...")
    response = ollama.chat(
        model='llama3',
        messages=[{"role": "user", "content": "Say 'Hello' in one word."}]
    )
    print(f"Model response: {response['message']['content']}")
    
except Exception as e:
    print(f"Error: {e}")