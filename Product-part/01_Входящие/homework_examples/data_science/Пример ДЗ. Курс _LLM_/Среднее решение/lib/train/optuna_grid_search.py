import optuna
import wandb
from train import TRAINING_CONFIG, prepare_tokenizer, load_tokenized_dataset, TimeoutCallback, create_model, split_dataset, MAX_TRAINING_TIME_SECONDS
from transformers import Trainer, TrainingArguments
import os

# Конфигурация для Optuna
OPTUNA_CONFIG = {
    'n_trials': 10,  # Количество испытаний
    'timeout': 8*3600,  # Максимальное время в секундах
    'direction': 'minimize',  # Минимизируем loss
}


def objective(trial):
    """
    Objective function for Optuna hyperparameter optimization.
    """
    # Гиперпараметры
    per_device_train_batch_size = trial.suggest_categorical('per_device_train_batch_size', [2, 4, 8, 16])
    learning_rate = trial.suggest_float('learning_rate', 1e-6, 1e-3, log=True)
    learning_rate_scheduler = trial.suggest_categorical('learning_rate_scheduler', ['linear', 'cosine', 'constant'])
    optim = trial.suggest_categorical('optim', ['adamw_torch', 'adamw_torch_fused', 'adamw_bnb_8bit'])
    dtype = trial.suggest_categorical('dtype', ['float16', 'bfloat16', 'float32'])
    
    # Обновляем конфигурацию обучения
    TRAINING_CONFIG.update({
        'per_device_train_batch_size': per_device_train_batch_size,
        'learning_rate': learning_rate,
        'lr_scheduler_type': learning_rate_scheduler,
        'optim': optim,
        'fp16': dtype == 'float16',
        'bf16': dtype == 'bfloat16',
        'gradient_accumulation_steps': max(1, 16 // per_device_train_batch_size),
    })
    
    try:
        # 1. Инициализация wandb для этого trial
        wandb.init(
            project=wandb.run.project if wandb.run else "gpt2-hyperparameter-tuning",
            config={
                'trial_number': trial.number,
                'per_device_train_batch_size': per_device_train_batch_size,
                'learning_rate': learning_rate,
                'learning_rate_scheduler': learning_rate_scheduler,
                'optim': optim,
                'dtype': dtype,
                'gradient_accumulation_steps': TRAINING_CONFIG['gradient_accumulation_steps'],
            },
            name="bs",
            settings=wandb.Settings(
            http_proxy=os.getenv('AVITO_HTTP_PROXY'),
            https_proxy=os.getenv('AVITO_HTTPS_PROXY'),
                ),
            reinit=True
        )
        
        # 2. Токенизатор (для инициализации модели)
        tokenizer = prepare_tokenizer()

        # 3. Загрузка датасета
        dataset = load_tokenized_dataset()
        train_dataset, eval_dataset = split_dataset(dataset)

        # 4. Модель
        model = create_model(tokenizer)

        # 5. Аргументы обучения
        training_args = TrainingArguments(**TRAINING_CONFIG)

        # 6. Создание Trainer
        trainer = Trainer(
            model=model,
            args=training_args,
            train_dataset=train_dataset,
            eval_dataset=eval_dataset,
            callbacks=[TimeoutCallback(timeout_seconds=MAX_TRAINING_TIME_SECONDS)]
        )

        # 7. Обучение
        trainer.train()

        # 8. Финальная оценка
        eval_results = trainer.evaluate()
        final_loss = eval_results['eval_loss']
        
        print(f"Trial {trial.number} completed with loss: {final_loss}")
        
        return final_loss
        
    except Exception as e:
        print(f"Trial {trial.number} failed with error: {e}")
        return float('inf')
    
    finally:
        # Завершаем wandb run
        if wandb.run:
            wandb.finish()

def hyperparameter_tuning():
  
    # Создаем study
    study = optuna.create_study(
        direction=OPTUNA_CONFIG['direction'],
        pruner=optuna.pruners.HyperbandPruner()
    )
    
    # Запускаем оптимизацию
    study.optimize(
        objective, 
        n_trials=OPTUNA_CONFIG['n_trials'],
        timeout=OPTUNA_CONFIG['timeout'],
        #TODO: add wandb callback
    )
    
    # Выводим результаты
    print("Best trial:")
    best_trial = study.best_trial
    print(f"--- Value (loss): {best_trial.value}")
    
    return study.best_params

if __name__ == "__main__":
    best_params = hyperparameter_tuning()
    print(best_params)
    