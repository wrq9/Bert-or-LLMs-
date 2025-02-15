from datasets import load_dataset
# 设置data_files 
# data_files = {
#     'train': 'stanfordnlp/imdb/train-00000-of-00001.parquet',
#     'test': 'stanfordnlp/imdb/test-00000-of-00001.parquet',
#     'validation': 'stanfordnlp/imdb/unsupervised-00000-of-00001.parquet'}
# 加载arrow数据集
dataset = load_dataset('stanfordnlp/imdb',cache_dir='./datasets', verification_mode='no_checks')
# 保存至本地
dataset.save_to_disk('./datasets')
