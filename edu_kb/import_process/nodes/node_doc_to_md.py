# -*- coding: utf-8 -*-
import json
import os
import shutil
import time
from pathlib import Path
from zipfile import ZipFile

import requests

from edu_kb.import_process.base import NodeBase
from edu_kb.import_process.state import ImportGraphState
from edu_kb.tool.logger import logger
from edu_kb.utils.docx_utils import docx_to_markdown


class NodeDocToMD(NodeBase):
    """
    文档转 Markdown 节点：
      - docx -> Markdown（本地解析，纯标准库）
      - pdf  -> Markdown（MinerU 结构化解析）
      - md   -> 直接读取
    """

    name = "node_doc_to_md"

    def process(self, state: ImportGraphState):
        if state.get("is_docx_read_enabled"):
            return self._process_docx(state)
        if state.get("is_pdf_read_enabled"):
            return self._process_pdf(state)
        if state.get("is_md_read_enabled"):
            md_path = state.get("md_path")
            if not md_path:
                raise ValueError("请指定MD文件路径")
            if not os.path.exists(md_path):
                raise FileNotFoundError(f"指定的MD文件不存在：{md_path}")
            logger.info(f"MD文件直接读取：{md_path}")
            return {"md_path": md_path}
        raise ValueError("未指定可处理的文件类型")

    # ------------------------- docx -------------------------
    def _process_docx(self, state: ImportGraphState):
        docx_path = state.get("local_file_path")
        local_dir = state.get("local_dir")
        if not docx_path:
            raise ValueError("请指定docx文件路径")
        if not local_dir:
            raise ValueError("请指定输出目录")
        if not os.path.exists(docx_path):
            raise FileNotFoundError(f"指定的docx文件不存在：{docx_path}")

        result = docx_to_markdown(docx_path, output_dir=local_dir)
        logger.info(
            f"docx转Markdown完成：{result['md_path']}，图片数量：{result['image_count']}"
        )
        return {"md_path": result["md_path"]}

    # ------------------------- pdf (MinerU) -------------------------
    def _process_pdf(self, state: ImportGraphState):
        # 步骤1：校验输入参数
        pdf_path_obj, output_dir_obj = self._step1_validate_paths(state)

        # 步骤2：上传pdf到MinerU并轮询解析结果
        zip_url = self._step2_upload_and_poll(pdf_path_obj)

        # 步骤3：下载zip包并解压
        file_title = pdf_path_obj.stem
        md_path = self._step3_download_and_extract(zip_url, output_dir_obj, file_title)

        return {"md_path": md_path}

    def _step1_validate_paths(self, state: ImportGraphState):
        pdf_path = state.get("pdf_path")
        local_dir = state.get("local_dir")
        if not pdf_path:
            raise ValueError("请指定PDF文件路径")
        if not local_dir:
            raise ValueError("请指定输出目录")

        pdf_path_obj = Path(pdf_path)
        output_dir_obj = Path(local_dir)
        if not pdf_path_obj.exists():
            raise FileNotFoundError(f"指定的PDF文件不存在：{pdf_path}")
        output_dir_obj.mkdir(parents=True, exist_ok=True)
        return pdf_path_obj, output_dir_obj

    @staticmethod
    def _get_api_token():
        token = os.getenv("MINERU_API_TOKEN")
        if not token:
            raise ValueError("请在.env中设置MINERU_API_TOKEN环境变量")
        return token

    @staticmethod
    def _get_base_url():
        base_url = os.getenv("MINERU_BASE_URL")
        if not base_url:
            raise ValueError("请在.env中设置MINERU_BASE_URL环境变量")
        return base_url

    def _step2_upload_and_poll(self, pdf_path_obj: Path):
        # 1. 申请文件上传链接
        token = self._get_api_token()
        url = f"{self._get_base_url()}/file-urls/batch"
        header = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        }
        data = {
            "files": [{"name": pdf_path_obj.name}],
            "model_version": "vlm",
        }

        response = requests.post(url, headers=header, json=data)
        if response.status_code != 200:
            raise RuntimeError(
                f"申请文件上传连接失败：{response.text}，状态码：{response.status_code}"
            )
        result = response.json()
        if result["code"] != 0:
            raise RuntimeError(f"申请文件上传连接失败，原因:{result['msg']}")

        batch_id = result["data"]["batch_id"]
        signed_url = result["data"]["file_urls"][0]

        # 2. 执行文件上传
        with open(pdf_path_obj, "rb") as f:
            res_upload = requests.put(signed_url, data=f)
            if res_upload.status_code != 200:
                raise RuntimeError(
                    f"上传文件失败：{res_upload}，状态码：{res_upload.status_code}"
                )

        # 3. 批量获取任务结果（轮询）
        url = f"{self._get_base_url()}/extract-results/batch/{batch_id}"
        start_time = time.time()
        timeout_seconds = 600
        poll_interval = 3

        while True:
            elapsed_time = time.time() - start_time
            if elapsed_time > timeout_seconds:
                raise RuntimeError(
                    f"【轮询中】任务超时，任务处理超过{timeout_seconds}s！batch_id:{batch_id}"
                )
            try:
                res = requests.get(url, headers=header, timeout=5)
            except Exception as e:
                logger.warning(f"【轮询中】网络请求异常:{e}，{poll_interval}s后重试")
                time.sleep(poll_interval)
                continue

            if res.status_code != 200:
                raise RuntimeError(f"【轮询中】获取任务结果失败，状态码：{res.status_code}")
            poll_data = res.json()
            if poll_data["code"] != 0:
                raise RuntimeError(f"【轮询中】获取任务结果失败，原因：{poll_data['msg']}")

            result_item = poll_data["data"]["extract_result"][0]
            data_state = result_item["state"]
            if data_state == "done":
                return result_item["full_zip_url"]
            elif data_state == "failed":
                err_msg = result_item.get("err_msg", "未知错误")
                raise RuntimeError(f"【轮询失败】任务失败，原因：{err_msg}")
            else:
                time.sleep(poll_interval)

    def _step3_download_and_extract(self, zip_url, output_dir_obj, file_title):
        response = requests.get(zip_url)
        if response.status_code != 200:
            raise RuntimeError(f"【下载失败】状态码：{response.status_code}")

        zip_save_path = output_dir_obj / f"{file_title}.zip"
        with open(zip_save_path, "wb") as f:
            f.write(response.content)

        unzip_dir_obj = output_dir_obj / file_title
        if unzip_dir_obj.exists():
            shutil.rmtree(unzip_dir_obj)
        unzip_dir_obj.mkdir(parents=True, exist_ok=True)

        with ZipFile(zip_save_path, "r") as zip_file:
            zip_file.extractall(unzip_dir_obj)

        md_file_obj = unzip_dir_obj / "full.md"
        new_md_path = md_file_obj.with_name(file_title + ".md")
        if md_file_obj.exists():
            md_file_obj.rename(new_md_path)
        else:
            # 容错：找不到 full.md 时直接查找目录内 md 文件
            md_files = list(unzip_dir_obj.glob("*.md"))
            if not md_files:
                raise RuntimeError("MinerU 解析结果中未找到 Markdown 文件")
            new_md_path = md_files[0]
        return str(new_md_path.absolute())


if __name__ == "__main__":
    init_state = {
        "local_file_path": r"D:\demo\课程文档\尚硅谷大模型技术之Python1.0.docx",
        "local_dir": r"D:\demo\output",
        "is_docx_read_enabled": True,
    }
    node = NodeDocToMD()
    print(json.dumps(node(init_state), ensure_ascii=False, indent=2))
