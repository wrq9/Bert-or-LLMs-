# 测试下evaluate好不好用
import evaluate

def compute_metrics():
    precision_metric = evaluate.load("evaluate/metrics/precision")
    recall_metric = evaluate.load("evaluate/metrics/recall")
    f1_metric= evaluate.load("evaluate/metrics/f1")
    accuracy_metric = evaluate.load("evaluate/metrics/accuracy")

    # logits, labels = eval_pred
    # predictions = np.argmax(logits, axis=-1)
    # precision = precision_metric.compute(predictions=predictions, references=labels)["precision"]
    # recall = recall_metric.compute(predictions=predictions, references=labels)["recall"]
    # f1 = f1_metric.compute(predictions=predictions, references=labels)["f1"]
    # accuracy = accuracy_metric.compute(predictions=predictions, references=labels)["accuracy"]
    # return {"precision": precision, "recall": recall, "f1-score": f1, 'accuracy': accuracy}


compute_metrics()