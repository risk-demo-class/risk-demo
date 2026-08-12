# -*- coding: utf-8 -*-
import base64
import json
import os
import re
import time
from collections import deque
from pathlib import Path
from typing import List, Tuple, Deque, Dict

from langchain_openai import ChatOpenAI
from minio.deleteobjects import DeleteObject

from edu_kb.config.config import lm_config, minio_config
from edu_kb.import_process.base import NodeBase
from edu_kb.import_process.prompt import IMAGE_SUMMARY
from edu_kb.import_process.state import ImportGraphState
from edu_kb.tool.logger import logger
from edu_kb.utils.minio_utils import get_minio_client


class NodeMDImg(NodeBase):
    """
    Markdown 图片处理节点：多模态图片理解 + 图片上传 MinIO
    """

    name = "node_md_img"

    def process(self, state: ImportGraphState):
        # 步骤1：获取 md 内容、文件路径、图片路径
        md_content, md_path_obj, images_dir = self._step1_get_content(state)
        if not images_dir.exists():
            logger.info(f"【图片处理】图片目录不存在：{images_dir}")
            return {"md_content": md_content}

        # 步骤2：扫描并筛选 md 文档中引用的所有图片
        images = self._step2_scan_images(md_content, images_dir)
        if not images:
            logger.info("【图片处理】无图片需要处理")
            return {"md_content": md_content}

        # 步骤3：生成图片摘要（VLM）
        file_title = md_path_obj.stem
        summaries = self._step3_generate_summaries(file_title, images)

        # 步骤4：上传图片至 MinIO，填充图片摘要和路径
        new_md_content = self._step4_upload_and_replace(
            file_title, images, summaries, md_content
        )

        # 步骤4.5：将新的内容存入物理文件（不覆盖原文件）
        new_md_file_name = self._step5_backup_new_md_file(state["md_path"], new_md_content)

        return {"md_content": new_md_content, "md_path": new_md_file_name}

    def _step1_get_content(self, state: ImportGraphState):
        md_path = state.get("md_path")
        if not md_path:
            raise ValueError("请指定MD文件路径")
        md_path_obj = Path(md_path)
        if not md_path_obj.exists():
            raise FileNotFoundError(f"指定的MD文件不存在：{md_path}")

        with open(md_path, "r", encoding="utf-8") as f:
            md_content = f.read()
        images_dir = md_path_obj.parent / "images"
        return md_content, md_path_obj, images_dir

    def _step2_scan_images(self, md_content: str, images_dir: Path):
        IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"}
        images = []
        for image_file in os.listdir(images_dir):
            file_ext = Path(image_file).suffix.lower()
            if file_ext not in IMAGE_EXTENSIONS:
                continue
            context = self._find_image_in_md(md_content, image_file)
            if not context:
                logger.warning(f"【图片处理】图片未被MD引用：{image_file}")
                continue
            images.append((image_file, str(images_dir / image_file), context))
        return images

    def _find_image_in_md(self, md_content: str, image_file: str, content_len: int = 100):
        pattern = re.compile(r"!\[.*?\]\(.*?" + re.escape(image_file) + r"\)")
        match = pattern.search(md_content)
        if not match:
            return None
        start, end = match.span()
        pre_text = md_content[max(0, start - content_len):start]
        post_text = md_content[end:min(end + content_len, len(md_content))]
        return pre_text, post_text

    def _step3_generate_summaries(self, file_title, images):
        summaries = {}
        request_deque = deque()
        for image_file, image_path, context in images:
            self._apply_api_rate_limit(request_deque, max_requests=10)
            summaries[image_file] = self._summarize_image(image_path, file_title, context)
        return summaries

    def _apply_api_rate_limit(self, request_deque: Deque[float], max_requests: int, window_size: int = 60):
        current_time = time.time()
        while request_deque and current_time - request_deque[0] >= window_size:
            request_deque.popleft()
        if len(request_deque) >= max_requests:
            sleep_duration = window_size - (current_time - request_deque[0])
            if sleep_duration > 0:
                logger.info(f"【API调用】API请求限速，等待{sleep_duration:.2f}秒")
                time.sleep(sleep_duration)
                current_time = time.time()
                while request_deque and current_time - request_deque[0] >= window_size:
                    request_deque.popleft()
        request_deque.append(current_time)

    def _summarize_image(self, image_path: str, file_title: str, context: Tuple[str, str]):
        with open(image_path, "rb") as f:
            image_data = f.read()
        prompt = IMAGE_SUMMARY.format(file_title=file_title, context=context)
        try:
            image_base64 = base64.b64encode(image_data).decode("utf-8")
            chat_model = ChatOpenAI(
                model=lm_config.vl_model,
                api_key=lm_config.api_key,
                base_url=lm_config.base_url,
                temperature=lm_config.llm_temperature,
            )
            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{image_base64}"
                            },
                        },
                    ],
                }
            ]
            response = chat_model.invoke(messages)
            return response.content.strip().replace("\n", "")
        except Exception:
            logger.error(f"【模型调用】图片摘要总结失败：{image_path}")
            return "图片描述"

    def _step4_upload_and_replace(self, file_title, images, summaries, md_content):
        upload_dir = f"{minio_config.img_dir}/{file_title}".replace(" ", "")
        self._clean_minio_directory(upload_dir)
        urls = self._upload_images_batch(upload_dir, images)
        image_info = {
            image_file: (summaries[image_file], urls[image_file])
            for image_file in summaries
        }
        return self._process_md_file(md_content, image_info)

    def _clean_minio_directory(self, upload_dir: str) -> None:
        """幂等性清理：上传前先删除 MinIO 中指定目录下的旧文件（失败不影响主流程）"""
        try:
            minio_client = get_minio_client()
            objects_to_delete = minio_client.list_objects(
                minio_config.bucket_name, upload_dir, recursive=True
            )
            delete_list = [DeleteObject(obj.object_name) for obj in objects_to_delete]
            if delete_list:
                errors = minio_client.remove_objects(minio_config.bucket_name, delete_list)
                for error in errors:
                    logger.error(f"删除失败: {error}")
        except Exception as e:
            logger.error(f"MinIO清理失败: {e}")

    def _upload_images_batch(self, upload_dir, images):
        urls = {}
        for image_file, image_path, context in images:
            object_name = f"{upload_dir}/{image_file}"
            urls[image_file] = self._upload_to_minio(image_path, object_name)
        return urls

    def _upload_to_minio(self, image_path: str, object_name: str) -> str:
        """上传图片到 MinIO；失败时回退为本地图片路径，不中断导入主流程"""
        try:
            minio_client = get_minio_client()
            minio_client.fput_object(minio_config.bucket_name, object_name, image_path)
            return f"http://{minio_config.endpoint}/{minio_config.bucket_name}/{object_name}"
        except Exception as e:
            logger.warning(f"图片上传MinIO失败，使用本地路径：{image_path}，原因：{e}")
            return str(image_path)

    def _process_md_file(self, md_content: str, image_info: Dict[str, Tuple[str, str]]) -> str:
        for image_file, (summary, url) in image_info.items():
            pattern = re.compile(r"!\[.*?\]\(.*?" + re.escape(image_file) + r"\)")
            md_content = pattern.sub(lambda x: f"![{summary}]({url})", md_content)
        return md_content

    def _step5_backup_new_md_file(self, origin_md_path: str, new_md_content: str) -> str:
        new_md_file_name = os.path.splitext(origin_md_path)[0] + "_new.md"
        with open(new_md_file_name, "w", encoding="utf-8") as f:
            f.write(new_md_content)
        return new_md_file_name
