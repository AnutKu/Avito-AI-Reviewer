from lib.train.train import prepare_tokenizer, create_model
import torch
from safetensors.torch import load_file

tokenizer = prepare_tokenizer()
model = create_model(tokenizer)

def generate_text(model, tokenizer, prompt, max_length=100):
    model.eval()
    
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model.to(device)
    
    with torch.no_grad():
        inputs = tokenizer(prompt, return_tensors="pt").to(device)
        
        outputs = model.generate(
            **inputs,
            max_length=max_length,
            num_return_sequences=1,
            temperature=0.7,
            do_sample=True,
            pad_token_id=tokenizer.eos_token_id,
            eos_token_id=tokenizer.eos_token_id
        )
        
        generated_text = tokenizer.decode(outputs[0], skip_special_tokens=True)
        answer = generated_text[len(prompt):].strip()
        
        return answer

if __name__ == "__main__":
    model_path = input("Enter model path: ")
    
    try:
        state_dict = load_file(model_path)
        model.load_state_dict(state_dict)
        print("Model loaded from safetensors!")
    except Exception as e:
        print(f"Error loading model: {e}")
        exit(1)
    
    while True:
        prompt = input("Prompt: ")
        if prompt.lower() in ['quit', 'exit', 'q']:
            break
            
        answer = generate_text(model, tokenizer, prompt)
        print("Answer:", answer)
        print("-" * 50)