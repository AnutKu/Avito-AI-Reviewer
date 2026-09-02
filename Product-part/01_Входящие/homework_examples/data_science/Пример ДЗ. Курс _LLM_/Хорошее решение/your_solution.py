import os
from datasets import load_dataset
from transformers import (
    AutoTokenizer,
    Qwen3Config,
    Qwen3ForCausalLM,
    Trainer,
    TrainingArguments,
    TrainerCallback
)
import torch
import mlflow
import time
import math
import json
from datetime import datetime


# Don't change this parameters
MAX_TRAINING_TIME_SECONDS = 60 * 30
MAX_LENGTH = 512
INPUT_IDS = 'input_ids'
ATTENTION_MASK = 'attention_mask'
LABELS = 'labels'

# Don't change these parameters
TOKENIZER_NAME = "ai-forever/rugpt3small_based_on_gpt2"
OUTPUT_DIR = "./output_dir"
NUM_SHARDS = 32
VALIDATION_SIZE = 5000


# TODO: Configure training parameters
TRAINING_CONFIG = {
    'output_dir': f'{OUTPUT_DIR}/gpt2-1b-russian',
    'optim': 'adamw',
    'num_train_epochs': 1,
    'per_device_train_batch_size': 4,
    'save_steps': 10,
    'save_total_limit': 20,
    'learning_rate': 5e-5,
    'weight_decay': 0.01,
    'warmup_steps': 200,
    'logging_steps': 1,
    'eval_steps': 10,
    'eval_strategy': 'steps',
    'load_best_model_at_end': True,
    'metric_for_best_model': 'eval_loss',
    'gradient_checkpointing': False,
    'gradient_accumulation_steps': 1,
    'dataloader_num_workers': 4,
    'torch_compile': True,
    'report_to': 'none',  # Изменено с 'wandb' на 'none'
}


class TimeoutCallback(TrainerCallback):
    """Callback to stop training after a specified timeout."""
    def __init__(self, timeout_seconds):
        self.timeout_seconds = timeout_seconds
        self.start_time = None
    
    def on_train_begin(self, args, state, control, **kwargs):
        self.start_time = time.time()
    
    def on_step_end(self, args, state, control, **kwargs):
        if self.start_time is not None:
            elapsed = time.time() - self.start_time
            if elapsed > self.timeout_seconds:
                control.should_training_stop = True
                print(f"Training stopped after {elapsed:.2f} seconds")
        return control


def prepare_tokenizer():
    """
    TODO: Implement tokenizer preparation.
    - Load the tokenizer from TOKENIZER_NAME
    - Set pad_token to eos_token
    - Return the tokenizer
    """
    tokenizer = AutoTokenizer.from_pretrained(TOKENIZER_NAME)
    tokenizer.pad_token = tokenizer.eos_token
    return tokenizer


def tokenize_function(examples, tokenizer):
    """
    TODO: Implement tokenization function.
    - Tokenize the text with truncation and padding to MAX_LENGTH
    - Create labels from input_ids
    - Return dictionary with 'labels', 'input_ids', and 'attention_mask'
    """
    tokenized = tokenizer(
        examples['text'],
        truncation=True,
        padding='max_length',
        max_length=MAX_LENGTH,
        return_tensors=None
    )
    tokenized[LABELS] = tokenized[INPUT_IDS].copy()
    return tokenized


def save_as_parquets(ds, output_dir=OUTPUT_DIR, num_shards=NUM_SHARDS):
    """
    TODO: Implement saving dataset as parquet shards.
    - Create output directory if it doesn't exist
    - Split dataset into num_shards shards
    - Save each shard as a parquet file with format: {output_dir}/{index:05d}.parquet
    """
    os.makedirs(output_dir, exist_ok=True)
    
    shard_size = len(ds) // num_shards
    for i in range(num_shards):
        start_idx = i * shard_size
        end_idx = start_idx + shard_size if i < num_shards - 1 else len(ds)
        
        shard = ds.select(range(start_idx, end_idx))
        shard.to_parquet(f"{output_dir}/{i:05d}.parquet")
    
    print(f"Saved {num_shards} shards to {output_dir}")


def prepare_dataset():
    """
    TODO: Implement dataset preparation.
    - Load the Wikipedia dataset: "wikimedia/wikipedia", "20231101.ru", split="train"
    - Tokenize the dataset using tokenize_function
    - Save as parquet files
    """
    print('Started loading dataset...')
    dataset = load_dataset("wikimedia/wikipedia", "20231101.ru", split="train")
    tokenizer = prepare_tokenizer()
    
    tokenized_dataset = dataset.map(
        lambda examples: tokenize_function(examples, tokenizer),
        batched=True,
        remove_columns=dataset.column_names
    )
    save_as_parquets(tokenized_dataset)
    
    return tokenized_dataset


def load_tokenized_dataset(data_dir=OUTPUT_DIR):
    """
    TODO: Implement loading of tokenized dataset from parquet files.
    - List all parquet files in data_dir
    - Load them using load_dataset('parquet', data_files=...)
    - Return the 'train' split
    """
    parquet_files = [os.path.join(data_dir, f) for f in os.listdir(data_dir) if f.endswith('.parquet')]
    parquet_files.sort()
    
    dataset = load_dataset('parquet', data_files=parquet_files, split='train')
    
    print(f"Loaded dataset with {len(dataset)} samples")
    return dataset


def split_dataset(dataset, validation_size=VALIDATION_SIZE):
    dataset_size = len(dataset)
    train_dataset = dataset.select(range(validation_size, dataset_size))
    eval_dataset = dataset.select(range(validation_size))
    
    print(f"Training samples: {len(train_dataset)}")
    print(f"Validation samples: {len(eval_dataset)}")
    
    return train_dataset, eval_dataset


def create_model(tokenizer):
    # Don't change this parameter
    MODEL_CONFIG = {
        'hidden_size': 2048,
        'num_hidden_layers': 12,
        'num_attention_heads': 16,
        'num_key_value_heads': 8,
        'intermediate_size': 8192,
        'head_dim': 128,
        'hidden_act': 'silu',
        'initializer_range': 0.02,
        'scale_attn_weights': True,
        'use_cache': True,
    }

    config = Qwen3Config(
        vocab_size=tokenizer.vocab_size,
        bos_token_id=tokenizer.bos_token_id,
        eos_token_id=tokenizer.eos_token_id,
        pad_token_id=tokenizer.pad_token_id,
        **MODEL_CONFIG
    )
    
    model = Qwen3ForCausalLM._from_config(
        config,
        attn_implementation='flash_attention_2',
        torch_dtype=torch.bfloat16
    )
    
    print(f"Model pad token id: {model.config.pad_token_id}")
    
    with torch.no_grad():
        total_params = sum(p.numel() for p in model.parameters())
        print(f"Total params: {total_params:,}")
    
    return model


def initialize_mlflow():
    """Initialize MLflow tracking"""
    mlflow.set_tracking_uri("./mlruns")
    mlflow.set_experiment("qwen-training")
    

def log_metrics_to_mlflow(metrics, step=None):
    """Log metrics to MLflow"""
    for key, value in metrics.items():
        if isinstance(value, (int, float)):
            mlflow.log_metric(key, value, step=step)


def train_model():
    """
    TODO: Implement the training pipeline.
    - Initialize mlflow
    - Prepare tokenizer
    - Load tokenized dataset and split it
    - Create the model
    - Create TrainingArguments from TRAINING_CONFIG
    - Create Trainer with TimeoutCallback
    - Train the model
    - Run final evaluation and print results
    """
    initialize_mlflow()
    
    with mlflow.start_run():

        mlflow.log_params({
            'model_type': 'Qwen3ForCausalLM',
            'tokenizer': TOKENIZER_NAME,
            'max_length': MAX_LENGTH,
            **{f'training_{k}': v for k, v in TRAINING_CONFIG.items()}
        })
        
        tokenizer = prepare_tokenizer()
        
        dataset = load_tokenized_dataset()
        
        train_dataset, eval_dataset = split_dataset(dataset)
        
        model = create_model(tokenizer)
        
        training_args = TrainingArguments(
            **TRAINING_CONFIG
        )
        
        class MLflowCallback(TrainerCallback):
            def on_log(self, args, state, control, logs=None, **kwargs):
                if logs:
                    log_metrics_to_mlflow(logs, step=state.global_step)
        
        trainer = Trainer(
            model=model,
            args=training_args,
            train_dataset=train_dataset,
            eval_dataset=eval_dataset,
            tokenizer=tokenizer,
            callbacks=[
                TimeoutCallback(timeout_seconds=MAX_TRAINING_TIME_SECONDS),
                MLflowCallback()
            ]
        )
        
        trainer.train()
        
        print("Running final evaluation...")
        eval_results = trainer.evaluate()
        print(f"Final evaluation results: {eval_results}")
        
        # Log final metrics
        log_metrics_to_mlflow({
            'final_eval_loss': eval_results['eval_loss'],
            'final_eval_perplexity': math.exp(eval_results['eval_loss'])
        })
        
        # Log model
        # mlflow.transformers.log_model(
        #     transformers_model={
        #         'model': model,
        #         'tokenizer': tokenizer
        #     },
        #     artifact_path="model",
        #     registered_model_name="qwen3-russian"
        # )


# ========== MANUAL GRID SEARCH ==========

def manual_runs():
    grid_configs = [
        # Batch size variations
        # {
        #     'batch_size': 2,
        #     'gradient_accumulation_steps': 8,
        #     'learning_rate': 5e-5,
        #     'optimizer': 'adamw_torch',
        #     'lr_scheduler': 'cosine',
        #     'torch_compile': True,
        #     'experiment_name': 'small_batch_high_accumulation'
        # },
        # {
        #     'batch_size': 4,
        #     'gradient_accumulation_steps': 4,
        #     'learning_rate': 5e-5,
        #     'optimizer': 'adamw_torch',
        #     'lr_scheduler': 'cosine',
        #     'torch_compile': True,
        #     'experiment_name': 'medium_batch_medium_accumulation'
        # },
        # {
        #     'batch_size': 8,
        #     'gradient_accumulation_steps': 2,
        #     'learning_rate': 5e-5,
        #     'optimizer': 'adamw_torch',
        #     'lr_scheduler': 'cosine',
        #     'torch_compile': True,
        #     'experiment_name': 'large_batch_low_accumulation'
        # },
        # # Learning rate variations
        # {
        #     'batch_size': 4,
        #     'gradient_accumulation_steps': 4,
        #     'learning_rate': 1e-5,
        #     'optimizer': 'adamw_torch',
        #     'lr_scheduler': 'cosine',
        #     'torch_compile': True,
        #     'experiment_name': 'low_lr'
        # },
        # {
        #     'batch_size': 4,
        #     'gradient_accumulation_steps': 4,
        #     'learning_rate': 1e-4,
        #     'optimizer': 'adamw_torch',
        #     'lr_scheduler': 'cosine',
        #     'torch_compile': True,
        #     'experiment_name': 'high_lr'
        # },
        # # Optimizer variations
        # {
        #     'batch_size': 4,
        #     'gradient_accumulation_steps': 4,
        #     'learning_rate': 5e-5,
        #     'optimizer': 'adafactor',
        #     'lr_scheduler': 'cosine',
        #     'torch_compile': True,
        #     'experiment_name': 'adafactor_optimizer'
        # },
        # # Scheduler variations
        # {
        #     'batch_size': 4,
        #     'gradient_accumulation_steps': 4,
        #     'learning_rate': 5e-5,
        #     'optimizer': 'adamw_torch',
        #     'lr_scheduler': 'linear',
        #     'torch_compile': True,
        #     'experiment_name': 'linear_scheduler'
        # },
        # {
        #     'batch_size': 4,
        #     'gradient_accumulation_steps': 4,
        #     'learning_rate': 5e-5,
        #     'optimizer': 'adamw_torch',
        #     'lr_scheduler': 'constant',
        #     'torch_compile': True,
        #     'experiment_name': 'constant_scheduler'
        # },
        # # torch_compile variations
        # {
        #     'batch_size': 4,
        #     'gradient_accumulation_steps': 4,
        #     'learning_rate': 5e-5,
        #     'optimizer': 'adamw_torch',
        #     'lr_scheduler': 'cosine',
        #     'torch_compile': False,
        #     'experiment_name': 'no_torch_compile'
        # },
        # # Combined variation
        # {
        #     'batch_size': 8,
        #     'gradient_accumulation_steps': 2,
        #     'learning_rate': 1e-4,
        #     'optimizer': 'adafactor',
        #     'lr_scheduler': 'linear',
        #     'torch_compile': False,
        #     'experiment_name': 'combined_variation'
        # },
        # # Combined variation with high lr
        # {
        #     'batch_size': 8,
        #     'gradient_accumulation_steps': 2,
        #     'learning_rate': 2e-4,
        #     'optimizer': 'adamw_torch',
        #     'lr_scheduler': 'linear',
        #     'torch_compile': False,
        #     'experiment_name': 'combined_variation_lr_2e4'
        # },
        # # New variation with lr
        # {
        #     'batch_size': 3,
        #     'gradient_accumulation_steps': 8,
        #     'learning_rate': 3e-4,
        #     'optimizer': 'adamw_torch_fused',
        #     'lr_scheduler': 'cosine',
        #     'torch_compile': False,
        #     'warmup_steps': 0,
        # },
        # New variation with lr 2
        {
            'batch_size': 10,
            'gradient_accumulation_steps': 3,
            'learning_rate': 1e-4,
            'optimizer': 'adamw_torch_fused',
            'lr_scheduler': 'cosine',
            'torch_compile': True,
            'warmup_steps': 0,
        },
    ]
    
    results = []
    
    print(f"Starting manual grid search with {len(grid_configs)} experiments...")
    print("=" * 60)
    
    for i, config in enumerate(grid_configs):
        print(f"\nExperiment {i+1}/{len(grid_configs)}")
        print(f"Config: {config}")
        print("-" * 40)

        experiment_name = f"""bs{config['batch_size']}gas{config['gradient_accumulation_steps']}lr{config['learning_rate']}\
        optimizer{config['optimizer']}lr_scheduler{config['lr_scheduler']}torch_compile{config['torch_compile']}warmup_steps{config['warmup_steps']}"""
        
        try:
            # Run single experiment
            final_loss = run_single_experiment(config, experiment_id=i)
            
            result = {
                'experiment_id': i,
                'experiment_name': experiment_name,
                'config': config,
                'final_eval_loss': final_loss,
                'final_eval_perplexity': math.exp(final_loss),
                'timestamp': datetime.now().isoformat(),
                'status': 'success'
            }
            
            results.append(result)
            
            print(f"Experiment {i+1} completed - Final loss: {final_loss:.4f}")
            
        except Exception as e:
            print(f"Experiment {i+1} failed: {e}")
            result = {
                'experiment_id': i,
                'experiment_name': experiment_name,
                'config': config,
                'error': str(e),
                'timestamp': datetime.now().isoformat(),
                'status': 'failed'
            }
            results.append(result)
        
        save_results(results)
        
        print(f"Progress: {i+1}/{len(grid_configs)} experiments completed")
    
    print("\n" + "=" * 60)
    print("GRID SEARCH SUMMARY")
    print("=" * 60)
    
    successful_results = [r for r in results if r['status'] == 'success']
    if successful_results:
        best_result = min(successful_results, key=lambda x: x['final_eval_loss'])
        worst_result = max(successful_results, key=lambda x: x['final_eval_loss'])
        
        print(f"Best experiment: {best_result['experiment_name']}")
        print(f"Best loss: {best_result['final_eval_loss']:.4f}")
        print(f"Best perplexity: {best_result['final_eval_perplexity']:.2f}")
        print(f"Best config: {best_result['config']}")
        print(f"Worst loss: {worst_result['final_eval_loss']:.4f}")
    else:
        print("No successful experiments!")
    
    return results


def run_single_experiment(config, experiment_id):
    """
    Run a single experiment with given configuration
    """

    os.environ['CUDA_VISIBLE_DEVICES'] = '1'
    
    initialize_mlflow()

    experiment_name = f"""bs{config['batch_size']}gas{config['gradient_accumulation_steps']}lr{config['learning_rate']}\
    optimizer{config['optimizer']}lr_scheduler{config['lr_scheduler']}torch_compile{config['torch_compile']}warmup_steps{config['warmup_steps']}"""
    
    with mlflow.start_run(run_name=f"exp-{experiment_id}-{experiment_name}"):

        mlflow.log_params(config)
        
        tokenizer = prepare_tokenizer()
        print('loading tokenized dataset...')
        dataset = load_tokenized_dataset()
        train_dataset, eval_dataset = split_dataset(dataset)
        print('creating model...')
        model = create_model(tokenizer)
        
        training_config = {
            'output_dir': f'{OUTPUT_DIR}/manual-exp-{experiment_id}',
            'optim': config['optimizer'],
            'num_train_epochs': 1,
            'per_device_train_batch_size': config['batch_size'],
            'gradient_accumulation_steps': config['gradient_accumulation_steps'],
            'learning_rate': config['learning_rate'],
            'lr_scheduler_type': config['lr_scheduler'],
            'warmup_steps': config['warmup_steps'],
            'weight_decay': 0.01,
            'save_strategy': "no",
            'save_steps': 2200,
            'logging_steps': 10,
            'eval_steps': 2000,
            'eval_strategy': 'steps',
            'metric_for_best_model': 'eval_loss',
            'gradient_checkpointing': False,
            'torch_compile': config['torch_compile'],
            'dataloader_num_workers': 6,
            'report_to': 'none',
        }
        
        training_args = TrainingArguments(**training_config)
        
        class MLflowCallback(TrainerCallback):
            def on_log(self, args, state, control, logs=None, **kwargs):
                if logs:
                    log_metrics_to_mlflow(logs, step=state.global_step)
        
        trainer = Trainer(
            model=model,
            args=training_args,
            train_dataset=train_dataset,
            eval_dataset=eval_dataset,
            tokenizer=tokenizer,
            callbacks=[
                TimeoutCallback(timeout_seconds=MAX_TRAINING_TIME_SECONDS),
                MLflowCallback()
            ]
        )
        
        trainer.train()
        eval_results = trainer.evaluate()
        trainer.save_model(output_dir=f'{OUTPUT_DIR}/manual-exp-{experiment_id}')
        
        mlflow.log_metrics({
            'final_eval_loss': eval_results['eval_loss'],
            'final_eval_perplexity': math.exp(eval_results['eval_loss']),
            'train_runtime': eval_results.get('train_runtime', 0),
            'train_samples_per_second': eval_results.get('train_samples_per_second', 0),
        })
        
        return eval_results['eval_loss']


def save_results(results):
    """
    Save results to JSON file
    """
    results_file = f"{OUTPUT_DIR}/grid_search_results.json"
    with open(results_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"Results saved to {results_file}")




if __name__ == "__main__":
    # prepare_dataset()
    
    # single model training
    # train_model()
    
    # manual grid search with 10 experiments
    manual_runs()