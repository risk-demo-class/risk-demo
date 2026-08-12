# -*- coding: utf-8 -*-
import json
from minio import Minio
from edu_kb.config.config import minio_config
from edu_kb.tool.logger import logger


minio_client = None


def get_minio_client():
    global minio_client
    if minio_client is not None:
        return minio_client
    try:
        # 1. 创建 MinIO 客户端对象
        minio_client = Minio(
            endpoint=minio_config.endpoint,
            access_key=minio_config.access_key,
            secret_key=minio_config.secret_key,
            secure=False,
        )

        # 2. 如果 Bucket 不存在，则创建 Bucket
        found = minio_client.bucket_exists(minio_config.bucket_name)
        if not found:
            minio_client.make_bucket(minio_config.bucket_name)

        # 3. 设置公开读权限（便于前端直接展示图片）
        policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"AWS": ["*"]},
                    "Action": ["s3:GetObject"],
                    "Resource": [f"arn:aws:s3:::{minio_config.bucket_name}/*"],
                }
            ],
        }
        minio_client.set_bucket_policy(minio_config.bucket_name, json.dumps(policy))
    except Exception as e:
        logger.error(f"MinIO初始化失败: {e}")
    return minio_client
