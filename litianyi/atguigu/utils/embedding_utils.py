# atguigu/utils/embedding_utils.py

from pymilvus.model.hybrid import BGEM3EmbeddingFunction
from atguigu.config.config import embedding_config
from atguigu.tool.logger import logger

# 1. 定义模型单例对象，避免重复初始化
_bge_m3_ef = None

# 2. 获取模型单例对象
def get_bge_m3_ef():
    """
    获取BGE-M3模型单例对象，自动加载环境变量配置
    """
    # 2.1 如果模型已经被实例化，则获取实例化对象
    global _bge_m3_ef
    if _bge_m3_ef is not None:
        return _bge_m3_ef

    try:
    # 2.2 如果模型没有被提前下载，这里也会自动下载
        _bge_m3_ef = BGEM3EmbeddingFunction(
            model_name=embedding_config.bge_m3_path,
            device=embedding_config.bge_device,
            use_fp16=embedding_config.bge_fp16
        )

    except Exception as e:
        logger.error(f"BGEM3初始化失败: {e}" )
    # 2.3 返回模型对象
    return _bge_m3_ef

# 3. 生成向量嵌入
def generate_embeddings(texts):
    """
    为文本生成向量嵌入:包含dense和sparse向量
    """
    model = get_bge_m3_ef()
    embeddings = model.encode_documents(texts)
    # embeddings 的数据结构：
    # 稠密向量：这是一个包含两个 array 的列表。每个 array 长度为 1024，数据类型是 float16（半精度）。
    # 稀疏向量：这是一个 Compressed Sparse Row sparse array（压缩稀疏行矩阵），
    #          形状是 (2, 250002)，250002 代表模型词汇表的大小（大约有 25 万个可能的词），2表示当前是2个词的向量

    return {
        "dense": [emb.tolist() for emb in embeddings["dense"]],
        "sparse": [{int (k):float (v) for k, v in zip(row.indices, row.data)} for row in embeddings["sparse"]]
    }

if __name__ == '__main__':

    result = generate_embeddings(["测试", "test"])
    logger.info(result)