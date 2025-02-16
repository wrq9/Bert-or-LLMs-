from huggingface_hub import snapshot_download
from huggingface_hub import login

login(token = 'xxx')
snapshot_download(repo_id='Qwen/Qwen2.5-3B',
                  repo_type='model',
                  local_dir='./backbone/Qwen2.5-3B',
                  resume_download=True)