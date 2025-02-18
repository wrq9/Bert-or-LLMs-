r"""
Training script to fine-tune a pre-train LLM with PEFT methods using HuggingFace.
  Example to run this conversion script:
    python peft_training.py \
     --in-file <path_to_hf_checkpoints_folder> \
     --out-file <path_to_output_nemo_file> \
"""

import os
os.environ["WANDB_PROJECT"] = "classifier_with_Lora" # log to your project
os.environ["WANDB_API_KEY"] = '2a3daa620b301a74d0558a66c8ed05562fd80235'
# os.environ["WANDB_MODE"] = "offline"
os.environ["WANDB_LOG_MODEL"] = "offline" # log your models
from copy import deepcopy

from argparse import ArgumentParser
from datasets import load_dataset, load_from_disk
import evaluate
import numpy as np
from peft import get_peft_model, LoraConfig, TaskType
from transformers import AutoTokenizer, DataCollatorWithPadding
from transformers import AutoModelForSequenceClassification
from transformers import TrainingArguments, Trainer, TrainerCallback
import torch

POS_WEIGHT, NEG_WEIGHT = (1.1637114032405993, 0.8766697374481806)

def get_args():
    parser = ArgumentParser(description="Fine-tune an LLM model with PEFT")
    parser.add_argument(
        "--data_path",
        type=str,
        default=None,
        required=True,
        help="Path to Huggingface pre-processed dataset",
    )
    parser.add_argument(
        "--output_path",
        type=str,
        default=None,
        required=True,
        help="Path to store the fine-tuned model",
    )
    parser.add_argument(
        "--model_name",
        type=str,
        default=None,
        required=True,
        help="Name of the pre-trained LLM to fine-tune",
    )
    parser.add_argument(
        "--max_length",
        type=int,
        default=512,
        required=False,
        help="Maximum length of the input sequences",
    )
    parser.add_argument(
        "--set_pad_id", 
        action="store_true",
        help="Set the id for the padding token, needed by models such as Mistral-7B",
    )
    parser.add_argument(
        "--lr", type=float, default=1e-3, help="Learning rate for training"
    )
    parser.add_argument(
        "--train_batch_size", type=int, default=64, help="Train batch size"
    )
    parser.add_argument(
        "--eval_batch_size", type=int, default=64, help="Eval batch size"
    )
    parser.add_argument(
        "--num_epochs", type=int, default=5, help="Number of epochs"
    )
    parser.add_argument(
        "--weight_decay", type=float, default=0.1, help="Weight decay"
    )
    parser.add_argument(
        "--lora_rank", type=int, default=4, help="Lora rank"
    )
    parser.add_argument(
        "--lora_alpha", type=float, default=0.0, help="Lora alpha"
    )
    parser.add_argument(
        "--lora_dropout", type=float, default=0.2, help="Lora dropout"
    )
    parser.add_argument(
        "--lora_bias",
        type=str,
        default='none',
        choices={"lora_only", "none", 'all'},
        help="Layers to add learnable bias"
    )

    arguments = parser.parse_args()
    return arguments

def compute_metrics(eval_pred):
    precision_metric = evaluate.load("evaluate/metrics/precision")
    recall_metric = evaluate.load("evaluate/metrics/recall")
    f1_metric = evaluate.load("evaluate/metrics/f1")
    accuracy_metric = evaluate.load("evaluate/metrics/accuracy")

    logits, labels = eval_pred
    predictions = np.argmax(logits, axis=-1)
    precision = precision_metric.compute(predictions=predictions, references=labels)["precision"]
    recall = recall_metric.compute(predictions=predictions, references=labels)["recall"]
    f1 = f1_metric.compute(predictions=predictions, references=labels)["f1"]
    accuracy = accuracy_metric.compute(predictions=predictions, references=labels)["accuracy"]
    return {"precision": precision, "recall": recall, "f1-score": f1, 'accuracy': accuracy}


class CustomCallback(TrainerCallback):
    def __init__(self, trainer) -> None:
        super().__init__()
        self._trainer = trainer

    def on_epoch_end(self, args, state, control, **kwargs):
        if control.should_evaluate:
            control_copy = deepcopy(control)
            self._trainer.evaluate(eval_dataset=self._trainer.train_dataset, metric_key_prefix="train")
            return control_copy


def get_dataset_and_collator(
    data_path,
    model_checkpoints,
    add_prefix_space=True,
    max_length=512,
    truncation=True,
    set_pad_id=False
):
    """
    Load the preprocessed HF dataset with train, valid and test objects
    
    Paramters:
    ---------
    data_path: str 
        Path to the pre-processed HuggingFace dataset 
    model_checkpoints: 
        Name of the pre-trained model to use for tokenization
    """
    data = load_from_disk(data_path)

    tokenizer = AutoTokenizer.from_pretrained(
        model_checkpoints,
        add_prefix_space=add_prefix_space
    )

    if set_pad_id:
        tokenizer.pad_token = tokenizer.eos_token

    def _preprocesscing_function(examples):
        return tokenizer(examples['text'], truncation=truncation, max_length=max_length)

    # col_to_delete = ['id', 'keyword','location', 'text']
    tokenized_datasets = data.map(_preprocesscing_function, batched=False)
    # tokenized_datasets = tokenized_datasets.remove_columns(col_to_delete)
    # tokenized_datasets = tokenized_datasets.rename_column("target", "label")
    tokenized_datasets.set_format("torch")  # 将数据集格式化为torch张量

    padding_collator = DataCollatorWithPadding(tokenizer=tokenizer)

    return tokenized_datasets, padding_collator


def get_lora_model(model_checkpoints, num_labels=2, rank=4, alpha=16, lora_dropout=0.1, bias='none'):
    """
    TODO
    """
    #if model_checkpoints == 'mistralai/Mistral-7B-v0.1' : 
    model =  AutoModelForSequenceClassification.from_pretrained(
            pretrained_model_name_or_path=model_checkpoints,
            num_labels=num_labels,
            device_map="auto",
            offload_folder="offload",
            trust_remote_code=True,
        )
    if model_checkpoints == 'backbone/Qwen2.5-3B-Instruct' or model_checkpoints == 'backbone/Qwen2.5-3B': 
        peft_config = LoraConfig(
            task_type=TaskType.SEQ_CLS, r=rank, lora_alpha=alpha, lora_dropout=lora_dropout, bias=bias,
            # 通过微调 q_proj 和 k_proj，可以调整模型在注意力机制中对输入特征的关注方式，从而更好地适应下游任务
            # 不作用于 v_proj 是为了保持参数效率和训练速度
            target_modules=["q_proj", "k_proj"]  # 只对q_proj和k_proj进行lora
    )
    else: 
        peft_config = LoraConfig(
            task_type=TaskType.SEQ_CLS, r=rank, lora_alpha=alpha, lora_dropout=lora_dropout, bias=bias,
        )
    model = get_peft_model(model, peft_config)
    print(model.print_trainable_parameters())

    return model


def get_weighted_trainer(pos_weight, neg_weight):
    
    class _WeightedBCELossTrainer(Trainer):
        def compute_loss(self, model, inputs, return_outputs=False):
            labels = inputs.pop("labels")
            # forward pass
            outputs = model(**inputs)
            logits = outputs.get("logits")
            # compute custom loss (suppose one has 3 labels with different weights)
            loss_fct = torch.nn.CrossEntropyLoss(weight=torch.tensor([neg_weight, pos_weight], device=labels.device, dtype=logits.dtype))
            loss = loss_fct(logits.view(-1, self.model.config.num_labels), labels.view(-1))
            return (loss, outputs) if return_outputs else loss
    return _WeightedBCELossTrainer

def main(args):
    """
    Training function
    """

    dataset, collator =  get_dataset_and_collator(
        args.data_path,
        args.model_name,
        max_length=args.max_length,
        set_pad_id=args.set_pad_id,
        add_prefix_space=True,
        truncation=True,
    )


    training_args = TrainingArguments(
        output_dir=args.output_path,
        learning_rate=args.lr,
        lr_scheduler_type="cosine",
        warmup_ratio=0.1,
        per_device_train_batch_size=args.train_batch_size,
        per_device_eval_batch_size=args.eval_batch_size,
        num_train_epochs=args.num_epochs,
        weight_decay=args.weight_decay,
        evaluation_strategy="epoch",
        save_strategy="epoch",
        load_best_model_at_end=True,
        gradient_checkpointing=True,
        fp16=True,
        report_to="wandb",
        max_grad_norm= 0.3,
    )

    model = get_lora_model(
        args.model_name,
        rank=args.lora_rank,
        alpha=args.lora_alpha,
        lora_dropout=args.lora_dropout,
        bias=args.lora_bias
    )
    if args.set_pad_id: 
        model.config.pad_token_id = model.config.eos_token_id

    # move model to GPU device
    if model.device.type != 'cuda':
        model=model.to('cuda')

    
    weighted_trainer = get_weighted_trainer(POS_WEIGHT, NEG_WEIGHT)
    
    trainer = weighted_trainer(
        model=model,
        args=training_args,
        train_dataset=dataset['train'],
        eval_dataset=dataset["test"],
        data_collator=collator,
        compute_metrics=compute_metrics
    )
    trainer.add_callback(CustomCallback(trainer))
    trainer.train()


if __name__ == "__main__":
    args = get_args()
    main(args)
