"""Image generator adapters. Workflow, service URL and credentials stay server-side."""

import asyncio
import copy
import json
import os
import re
import time
from io import BytesIO
from pathlib import Path
from typing import Protocol
from threading import BoundedSemaphore
from urllib.parse import urlparse
import httpx
from PIL import Image, ImageOps, UnidentifiedImageError

IMAGE_DECODERS = BoundedSemaphore(2)


class GenerationError(RuntimeError):
    pass


def normalized_image(data: bytes, minimum=128) -> bytes:
    if not data or len(data) > 8 * 1024 * 1024:
        raise GenerationError("图片为空或超过8MB。")
    try:
        with IMAGE_DECODERS, Image.open(BytesIO(data)) as image:
            if image.format not in {"PNG", "JPEG", "WEBP"} or getattr(
                image, "is_animated", False
            ):
                raise GenerationError("仅支持静态 PNG、JPEG、WebP 图片。")
            if (
                min(image.size) < minimum
                or max(image.size) > 4096
                or image.width * image.height > 16_000_000
            ):
                raise GenerationError("图片尺寸需为128至4096像素，且不超过1600万像素。")
            image.load()
            output = BytesIO()
            # Preserve phone-photo orientation, then copy pixels without metadata.
            with ImageOps.exif_transpose(image).convert("RGBA") as pixels:
                with Image.new("RGBA", pixels.size) as clean:
                    clean.paste(pixels)
                    clean.save(output, format="PNG")
            result = output.getvalue()
            if len(result) > 8 * 1024 * 1024:
                raise GenerationError("图片转换后超过8MB，请缩小尺寸。")
            return result
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as error:
        raise GenerationError("图片内容损坏或无法解码。") from error


class ImageGenerator(Protocol):
    mode: str

    async def submit(self, spec: dict, reference: bytes) -> str: ...
    async def poll(self, remote_id: str, spec: dict) -> list[bytes] | None: ...
    async def cancel(self, remote_id: str) -> None: ...


class MockCharacterGenerator:
    mode = "mock"

    async def submit(self, spec, reference):
        return f"mock-{int(time.time()*1000)}"

    async def poll(self, remote_id, spec):
        if time.time() * 1000 - int(remote_id.split("-")[1]) < 1500:
            return None
        directory = Path(__file__).resolve().parent / "demo_assets"
        if not directory.exists():
            directory = (
                Path(__file__).resolve().parent.parent
                / "frontend"
                / "public"
                / "assets"
            )
        path = directory / (spec["demo_template"] + ".png")
        return [await asyncio.to_thread(normalized_image, path.read_bytes())]

    async def cancel(self, remote_id):
        return None


class ComfyUICharacterGenerator:
    mode = "comfyui"

    def __init__(self, base_url, workflow_path, api_key="", transport=None):
        parsed = urlparse(base_url)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise GenerationError("ComfyUI 服务端地址配置无效。")
        self.base_url = base_url.rstrip("/")
        self.workflow_path = Path(workflow_path)
        self.headers = {"Authorization": "Bearer " + api_key} if api_key else {}
        self.transport = transport

    def workflow(self, spec, reference_name):
        try:
            template = json.loads(self.workflow_path.read_text(encoding="utf-8"))
            if not template.get("enabled"):
                raise GenerationError("ComfyUI 工作流尚未启用，请管理员配置。")
            graph = copy.deepcopy(template["prompt"])
            values = {
                "reference_image": reference_name,
                "positive_prompt": f'{spec["appearance"]}, {spec["persona"]}, visual novel character sprite',
                "seed": int(time.time_ns() % 2**31),
            }
            allowed = {
                "reference_image": ("LoadImage", "image"),
                "positive_prompt": ("CLIPTextEncode", "text"),
                "seed": ("KSampler", "seed"),
            }
            for key, value in values.items():
                binding = template["bindings"][key]
                node = graph[binding["node_id"]]
                if (node.get("class_type"), binding["input"]) != allowed[key]:
                    raise GenerationError("工作流绑定不在已审核的节点输入白名单内。")
                if binding["input"] not in node["inputs"]:
                    raise GenerationError("工作流输入白名单配置无效。")
                node["inputs"][binding["input"]] = value
            outputs = template["output_node_ids"]
            if not outputs or any(node_id not in graph for node_id in outputs):
                raise GenerationError("工作流输出节点尚未配置。")
            return graph, outputs
        except (OSError, ValueError, KeyError, TypeError) as error:
            raise GenerationError("ComfyUI 工作流配置无法读取。") from error

    def client(self):
        return httpx.AsyncClient(
            base_url=self.base_url + "/",
            headers=self.headers,
            timeout=20,
            follow_redirects=False,
            transport=self.transport,
        )

    async def submit(self, spec, reference):
        self.workflow(spec, "reference.png")
        try:
            async with self.client() as client:
                upload = await client.post(
                    "upload/image",
                    files={"image": ("reference.png", reference, "image/png")},
                    data={"type": "input", "overwrite": "false"},
                )
                upload.raise_for_status()
                name = upload.json()["name"]
                if (
                    not isinstance(name, str)
                    or "/" in name
                    or "\\" in name
                    or ".." in name
                ):
                    raise GenerationError("ComfyUI 返回了无效图片名称。")
                graph, _ = self.workflow(spec, name)
                result = await client.post("prompt", json={"prompt": graph})
                result.raise_for_status()
                remote_id = result.json()["prompt_id"]
                if not isinstance(remote_id, str) or not re.fullmatch(
                    r"[\w-]{1,120}", remote_id
                ):
                    raise GenerationError("ComfyUI 返回了无效任务编号。")
                return remote_id
        except (httpx.HTTPError, ValueError, KeyError) as error:
            raise GenerationError("ComfyUI 提交失败，请核查服务配置后重试。") from error

    async def poll(self, remote_id, spec):
        _, output_nodes = self.workflow(spec, "reference.png")
        try:
            async with self.client() as client:
                response = await client.get("history/" + remote_id)
                response.raise_for_status()
                record = response.json().get(remote_id)
                if not record:
                    return None
                if record.get("status", {}).get("status_str") == "error":
                    raise GenerationError("ComfyUI 生成失败，生成权益将恢复。")
                outputs = record.get("outputs", {})
                images = [
                    image
                    for node in output_nodes
                    for image in outputs.get(node, {}).get("images", [])
                ]
                if not images:
                    return None
                results = []
                expected = 1 + spec["expressions"] + spec["poses"]
                for image in images[:expected]:
                    name = image["filename"]
                    folder = image.get("subfolder", "")
                    if (
                        "/" in name
                        or "\\" in name
                        or ".." in name
                        or folder.startswith(("/", "\\"))
                        or ":" in folder
                        or ".." in folder.replace("\\", "/").split("/")
                        or image.get("type", "output") != "output"
                    ):
                        raise GenerationError("ComfyUI 输出路径校验失败。")
                    async with client.stream(
                        "GET",
                        "view",
                        params={
                            "filename": name,
                            "subfolder": folder,
                            "type": "output",
                        },
                    ) as asset:
                        asset.raise_for_status()
                        data = bytearray()
                        async for chunk in asset.aiter_bytes():
                            data.extend(chunk)
                            if len(data) > 8 * 1024 * 1024:
                                raise GenerationError("生成图片超过8MB，任务已停止。")
                    results.append(
                        await asyncio.to_thread(normalized_image, bytes(data))
                    )
                if len(results) < expected:
                    raise GenerationError("当前工作流未输出完整角色包，请调整工作流。")
                return results
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as error:
            raise GenerationError("ComfyUI 状态或输出读取失败，请重试。") from error

    async def cancel(self, remote_id):
        try:
            async with self.client() as client:
                await client.post("queue", json={"delete": [remote_id]})
        except httpx.HTTPError:
            pass


def configured_generator() -> ImageGenerator:
    if os.getenv("IMAGE_GENERATOR", "mock") == "comfyui":
        return ComfyUICharacterGenerator(
            os.getenv("COMFYUI_BASE_URL", ""),
            os.getenv(
                "COMFYUI_WORKFLOW_PATH", "backend/workflows/character.template.json"
            ),
            os.getenv("COMFYUI_API_KEY", ""),
        )
    return MockCharacterGenerator()


image_generator = configured_generator()
