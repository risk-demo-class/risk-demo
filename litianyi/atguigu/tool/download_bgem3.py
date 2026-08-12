from modelscope.hub.snapshot_download import snapshot_download
from atguigu.tool.logger import logger

# 下载模型到当前目录下的 models/bge-m3 文件夹
# model_dir = snapshot_download('Xorbits/bge-m3', cache_dir='D:/ai_models/modelscope_cache/models')
# print(f"模型已下载到: {model_dir}")


from modelscope.hub.snapshot_download import snapshot_download

# 下载模型到当前目录下的 models/bge-m3 文件夹
model_dir = snapshot_download('BAAI/bge-m3', cache_dir='D:/SGGLearning/14.尚硅谷大模型项目之掌柜智库/My_project/models')
print(f"模型已下载到: {model_dir}")

logger.info(f"模型已下载到: {model_dir}")