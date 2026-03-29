#!/usr/bin/env python3
"""
ComfyUI Workflow Runner

A unified script for executing ComfyUI workflows including:
- Text-to-Image (文生图)
- Image Editing (图像编辑)
- Image-to-Video (图生视频)

Supports easy extension for new workflows.
"""

import json
import os
import random
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import requests
from PIL import Image


# =============================================================================
# Script Directory (for resolving relative paths)
# =============================================================================

# Get the directory where this script is located
_SCRIPT_DIR = Path(__file__).parent.absolute()
_DEFAULT_WORKFLOWS_DIR = _SCRIPT_DIR / "workflows"


# =============================================================================
# LoRA Keyword Mapping Configuration
# =============================================================================
# Format: "LoRA Name Pattern": ["keyword1", "keyword2", ...]
# When a keyword is detected in the prompt, the corresponding LoRA will be enabled
# LoRA name matching is case-insensitive and uses substring matching
LORA_KEYWORD_MAPPING = {
    # Portrait/Character LoRAs
    "Instagirl": ["portrait", "selfie", "instagram", "girl", "woman", "face"],
    "r3v3rs3_c0wg1rl": ["cowgirl", "riding", "reverse", "sex", "r3v3rs3_c0wg1rl", "c0wg1rl"],
    "Lenovo": ["phone", "mobile", "smartphone", "handheld"],

    # Style LoRAs
    "cyberpunk": ["cyberpunk", "neon", "futuristic", "sci-fi"],
    "anime": ["anime", "manga", "cartoon", "2d"],
    "realistic": ["realistic", "photorealistic", "photo"],
    "cinematic": ["cinematic", "movie", "film"],

    # Action/Motion LoRAs
    "dance": ["dance", "dancing", "choreography"],
    "run": ["run", "running", "sprint"],
    "walk": ["walk", "walking", "stroll"],

    # Add more mappings below as needed
}


# =============================================================================
# Configuration
# =============================================================================

class WorkflowType(Enum):
    """Supported workflow types"""
    TEXT_TO_IMAGE = "text_to_image"
    IMAGE_EDIT = "image_edit"
    IMAGE_TO_VIDEO = "image_to_video"
    ADD_AUDIO_TO_VIDEO = "add_audio_to_video"


@dataclass
class ComfyUIConfig:
    """ComfyUI server configuration"""
    server_address: str = "192.168.1.179:8188"
    default_output_dir: str = "./outputs"
    request_timeout: int = 30
    poll_interval: int = 5
    max_poll_retries: int = 600  # 50 minutes max for long video generation
    # Service manager configuration
    service_manager_enabled: bool = True
    service_manager_address: str = "192.168.1.179:9999"


# =============================================================================
# Workflow Parameters
# =============================================================================

@dataclass
class WorkflowParams(ABC):
    """Base class for workflow parameters"""
    seed: Optional[int] = None

    def __post_init__(self):
        if self.seed is None:
            self.seed = random.randint(0, sys.maxsize)


@dataclass
class TextToImageParams(WorkflowParams):
    """Parameters for text-to-image workflow"""
    positive_prompt: str = ""
    negative_prompt: str = "低分辨率，低画质，肢体畸形，手指畸形，画面过饱和，蜡像感，人脸无细节，过度光滑，画面具有AI感。构图混乱。文字模糊，扭曲"
    width: int = 928
    height: int = 1664
    steps: int = 4
    cfg: float = 1.0
    sampler_name: str = "sa_solver"
    scheduler: str = "beta"
    denoise: float = 1.0


@dataclass
class ImageEditParams(WorkflowParams):
    """Parameters for image editing workflow"""
    image_path: str = ""
    edit_prompt: str = ""
    negative_prompt: str = ""
    steps: int = 4
    cfg: float = 1.0
    sampler_name: str = "sa_solver"
    scheduler: str = "beta"
    denoise: float = 1.0


@dataclass
class ImageToVideoParams(WorkflowParams):
    """Parameters for image-to-video workflow"""
    image_path: str = ""
    prompt: str = ""
    negative_prompt: str = "色调艳丽，过曝，静态，细节模糊不清，字幕，风格，作品，画作，画面，静止，整体发灰，最差质量，低质量，JPEG压缩残留，丑陋的，残缺的，多余的手指，画得不好的手部，画得不好的脸部，畸形的，毁容的，形态畸形的肢体，手指融合，静止不动的画面，杂乱的背景，三条腿，背景人很多，倒着走"
    width: int = 480
    height: int = 832
    length: int = 81
    steps: int = 4
    cfg: float = 1.0
    fps: int = 16
    service_name: Optional[str] = None  # Service to switch to before generation
    # Model selection
    model: str = "default"  # "default" or "smooth"
    # LoRA control
    lora_keywords: bool = True  # Enable automatic LoRA keyword detection
    lora_mapping: Dict[str, List[str]] = field(default_factory=dict)  # Custom keyword mapping (overrides default)


@dataclass
class AddAudioToVideoParams(WorkflowParams):
    """Parameters for add-audio-to-video workflow (MMAudio)"""
    video_path: str = ""
    prompt: str = ""
    negative_prompt: str = ""
    steps: int = 100
    cfg: float = 6.0
    source_fps: int = 16
    target_fps: int = 25
    filename_prefix: str = "MMAudio"
    service_name: Optional[str] = None  # Service to switch to before generation


# =============================================================================
# Workflow Base Classes
# =============================================================================

class Workflow(ABC):
    """Base class for ComfyUI workflows"""

    def __init__(self, workflow_path: str, config: ComfyUIConfig):
        self.workflow_path = workflow_path
        self.config = config
        self.client_id = f"workflow_runner_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.session: Optional[requests.Session] = None
        self.prompt_data: Dict[str, Any] = {}
        self._load_workflow()

    def _load_workflow(self):
        """Load workflow from JSON file"""
        try:
            with open(self.workflow_path, "r", encoding="utf-8") as f:
                self.prompt_data = json.load(f)
        except FileNotFoundError:
            raise FileNotFoundError(f"Workflow file not found: {self.workflow_path}")
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid workflow JSON: {e}")

    def connect(self):
        """Initialize HTTP session"""
        if self.session is None:
            self.session = requests.Session()

    def close(self):
        """Close HTTP session"""
        if self.session is not None:
            self.session.close()
            self.session = None

    def _check_server_status(self) -> bool:
        """Check if ComfyUI server is running and responsive"""
        try:
            response = requests.get(
                f"http://{self.config.server_address}/system_stats",
                timeout=5
            )
            return response.status_code == 200
        except Exception:
            return False

    def _ensure_server_running(self) -> bool:
        """
        Ensure ComfyUI server is running before operations.

        If service manager is enabled and server is down, try to start a service.
        Returns True if server is running, False otherwise.
        """
        if self._check_server_status():
            return True

        print("[ComfyUI] Server is not running...")

        if self.config.service_manager_enabled:
            print("[Service Manager] Attempting to start 'normal' service...")
            import time

            # Try to start the normal service
            if self._switch_service("normal", wait_for_recovery=True, timeout=120):
                print("[Service Manager] Service started successfully")
                return True
            else:
                print("[Service Manager] Failed to start service")
                return False
        else:
            print("[ComfyUI] Please start ComfyUI server or check service manager")
            print("[ComfyUI] Service manager is enabled by default, use --disable-service-manager to disable")
            return False

    def _reboot_server(self, wait_for_recovery: bool = True, timeout: int = 300) -> bool:
        """
        Reboot ComfyUI server via manager API

        Args:
            wait_for_recovery: If True, wait for server to come back online
            timeout: Maximum seconds to wait for recovery

        Returns:
            True if reboot was initiated (regardless of recovery status)
        """
        import time

        print("[ComfyUI] Sending reboot request...")

        try:
            # Send reboot request - may return 400 or other errors, which is normal
            response = requests.get(
                f"http://{self.config.server_address}/manager/reboot",
                timeout=10
            )
            # Any response (including errors) means reboot was initiated
            print(f"[ComfyUI] Reboot initiated (HTTP {response.status_code})")
        except Exception as e:
            # Connection error is also OK - server may be shutting down
            print(f"[ComfyUI] Reboot request sent (server may be shutting down)")

        if not wait_for_recovery:
            return True

        # Wait for server to recover
        print(f"[ComfyUI] Waiting for server to recover (max {timeout}s)...")

        start_time = time.time()
        retry_count = 0
        recovered = False

        while time.time() - start_time < timeout:
            if self._check_server_status():
                recovered = True
                break

            retry_count += 1
            wait_time = min(2 + retry_count * 0.5, 10)  # Progressive backoff, max 10s
            time.sleep(wait_time)

        if recovered:
            elapsed = int(time.time() - start_time)
            print(f"[ComfyUI] Server recovered after {elapsed}s")
            # Additional wait for services to fully initialize
            time.sleep(3)
        else:
            print(f"[ComfyUI] Warning: Server not recovered after {timeout}s")

        return recovered

    def _get_current_service(self) -> Optional[str]:
        """
        Get the currently active service from service manager

        Returns:
            Service name if service manager is enabled, None otherwise
        """
        if not self.config.service_manager_enabled:
            return None

        try:
            response = requests.get(
                f"http://{self.config.service_manager_address}/status",
                timeout=5
            )
            if response.status_code == 200:
                result = response.json()
                return result.get("active_service")
        except Exception as e:
            print(f"[Service Manager] Error getting status: {e}")

        return None

    def _switch_service(self, service_name: str, wait_for_recovery: bool = True, timeout: int = 120) -> bool:
        """
        Switch to a different ComfyUI service via service manager

        Args:
            service_name: Name of the service to switch to
            wait_for_recovery: If True, wait for service to be ready
            timeout: Maximum seconds to wait for recovery

        Returns:
            True if switch was successful
        """
        if not self.config.service_manager_enabled:
            print(f"[Service Manager] Service manager not enabled, skipping switch")
            return False

        import time

        print(f"[Service Manager] Switching to service '{service_name}'...")

        try:
            response = requests.post(
                f"http://{self.config.service_manager_address}/switch/{service_name}",
                timeout=30
            )

            if response.status_code != 200:
                print(f"[Service Manager] Switch failed (HTTP {response.status_code}): {response.text}")
                return False

            result = response.json()
            if not result.get("success", False):
                print(f"[Service Manager] Switch failed: {result.get('message', 'Unknown error')}")
                return False

            print(f"[Service Manager] Service switch initiated")

        except Exception as e:
            print(f"[Service Manager] Error switching service: {e}")
            return False

        if not wait_for_recovery:
            return True

        # Wait for service to be ready
        print(f"[Service Manager] Waiting for service to be ready (max {timeout}s)...")

        start_time = time.time()
        retry_count = 0
        recovered = False

        while time.time() - start_time < timeout:
            if self._check_server_status():
                # Additional check: verify it's the correct service
                recovered = True
                break

            retry_count += 1
            wait_time = min(2 + retry_count * 0.5, 10)
            time.sleep(wait_time)

        if recovered:
            elapsed = int(time.time() - start_time)
            print(f"[Service Manager] Service '{service_name}' ready after {elapsed}s")
            time.sleep(2)  # Additional wait for full initialization
        else:
            print(f"[Service Manager] Warning: Service not ready after {timeout}s")

        return recovered

    def _queue_prompt(self) -> str:
        """Queue workflow for execution and return prompt_id"""
        payload = {"prompt": self.prompt_data, "client_id": self.client_id}
        response = self.session.post(
            f"http://{self.config.server_address}/prompt",
            json=payload,
            timeout=self.config.request_timeout
        )
        if response.status_code != 200:
            # Print error details for debugging
            print(f"Error response: {response.text}")
        response.raise_for_status()
        result = response.json()
        if "prompt_id" not in result:
            raise ValueError("Server response missing prompt_id")
        return result["prompt_id"]

    def _poll_completion(self, prompt_id: str) -> Dict[str, Any]:
        """Poll for workflow completion"""
        retry_count = 0
        while retry_count < self.config.max_poll_retries:
            try:
                response = self.session.get(
                    f"http://{self.config.server_address}/history/{prompt_id}",
                    timeout=self.config.request_timeout
                )
                response.raise_for_status()
                history = response.json()

                if prompt_id in history and "outputs" in history[prompt_id]:
                    return history[prompt_id]

                # Still processing
                time.sleep(self.config.poll_interval)
                retry_count += 1
            except Exception as e:
                if retry_count >= self.config.max_poll_retries:
                    raise TimeoutError(f"Timeout waiting for prompt {prompt_id}: {e}")
                time.sleep(self.config.poll_interval)
                retry_count += 1

        raise TimeoutError(f"Timeout waiting for prompt {prompt_id}")

    def _upload_image(self, image_path: str, subfolder: str = "") -> str:
        """Upload image to ComfyUI server"""
        with open(image_path, "rb") as f:
            files = {"image": (os.path.basename(image_path), f)}
            data = {"subfolder": subfolder, "type": "input"}
            response = self.session.post(
                f"http://{self.config.server_address}/upload/image",
                files=files,
                data=data,
                timeout=self.config.request_timeout
            )
            response.raise_for_status()
            result = response.json()
            subfolder = result.get('subfolder', '')
            if subfolder:
                return f"{subfolder}/{result['name']}"
            else:
                return result['name']

    @abstractmethod
    def set_parameters(self, params: WorkflowParams):
        """Set workflow-specific parameters"""
        pass

    @abstractmethod
    def execute(self, params: WorkflowParams, output_dir: str) -> List[str]:
        """Execute workflow and return list of output file paths"""
        pass


# =============================================================================
# Concrete Workflow Implementations
# =============================================================================

class TextToImageWorkflow(Workflow):
    """Text-to-image generation workflow"""

    # Node IDs in the workflow
    NODE_POSITIVE_CLIP = "264"
    NODE_NEGATIVE_CLIP = "250"
    NODE_KSAMPLER = "263"
    NODE_EMPTY_LATENT = "260"
    NODE_SAVE_IMAGE = "60"

    def set_parameters(self, params: TextToImageParams):
        """Set text-to-image parameters"""
        # Set positive prompt
        if self.NODE_POSITIVE_CLIP in self.prompt_data:
            self.prompt_data[self.NODE_POSITIVE_CLIP]["inputs"]["text"] = params.positive_prompt

        # Set negative prompt
        if self.NODE_NEGATIVE_CLIP in self.prompt_data:
            self.prompt_data[self.NODE_NEGATIVE_CLIP]["inputs"]["text"] = params.negative_prompt

        # Set KSampler parameters
        if self.NODE_KSAMPLER in self.prompt_data:
            self.prompt_data[self.NODE_KSAMPLER]["inputs"].update({
                "seed": params.seed,
                "steps": params.steps,
                "cfg": params.cfg,
                "sampler_name": params.sampler_name,
                "scheduler": params.scheduler,
                "denoise": params.denoise
            })

        # Set image dimensions
        if self.NODE_EMPTY_LATENT in self.prompt_data:
            self.prompt_data[self.NODE_EMPTY_LATENT]["inputs"].update({
                "width": params.width,
                "height": params.height
            })

    def execute(self, params: TextToImageParams, output_dir: str = "./outputs") -> List[str]:
        """Execute text-to-image workflow"""
        import time
        start_time = time.time()

        # Ensure server is running
        if not self._ensure_server_running():
            raise ConnectionError("ComfyUI server is not available")

        # Auto-switch to normal service for image generation
        if self.config.service_manager_enabled:
            current_service = self._get_current_service()
            if current_service != "normal":
                print(f"[Service Manager] Auto-switching to 'normal' service for image generation")
                self._switch_service("normal", wait_for_recovery=True, timeout=120)

        self.connect()
        try:
            self.set_parameters(params)
            prompt_id = self._queue_prompt()
            result = self._poll_completion(prompt_id)
            outputs = self._save_outputs(result, output_dir, params.seed)

            elapsed = time.time() - start_time
            print(f"[Text-to-Image] Completed in {elapsed:.2f}s ({elapsed/60:.1f} minutes)")
            return outputs
        finally:
            self.close()

    def _save_outputs(self, result: Dict, output_dir: str, seed: int) -> List[str]:
        """Save generated images"""
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        saved_files = []

        for node_id, node_output in result.get("outputs", {}).items():
            if "images" in node_output:
                for img in node_output["images"]:
                    filename = img["filename"]
                    subfolder = img.get("subfolder", "")
                    folder_type = img.get("type", "output")

                    # Download image
                    params = {
                        "filename": filename,
                        "subfolder": subfolder,
                        "type": folder_type
                    }
                    response = self.session.get(
                        f"http://{self.config.server_address}/view",
                        params=params,
                        timeout=self.config.request_timeout
                    )
                    response.raise_for_status()

                    # Save with timestamp and seed
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    output_filename = f"t2i_{timestamp}_seed{seed}_{filename}"
                    output_file_path = output_path / output_filename

                    with open(output_file_path, "wb") as f:
                        f.write(response.content)

                    saved_files.append(str(output_file_path))
                    print(f"Saved: {output_file_path}")

        return saved_files


class ImageEditWorkflow(Workflow):
    """Image editing workflow"""

    # Node IDs in the workflow
    NODE_LOAD_IMAGE = "41"
    NODE_POSITIVE_EDIT = "176"
    NODE_NEGATIVE_EDIT = "174"
    NODE_KSAMPLER = "193"
    NODE_SAVE_IMAGE = "9"

    def set_parameters(self, params: ImageEditParams):
        """Set image editing parameters"""
        # Upload and set input image
        image_ref = self._upload_image(params.image_path, subfolder="")
        if self.NODE_LOAD_IMAGE in self.prompt_data:
            self.prompt_data[self.NODE_LOAD_IMAGE]["inputs"]["image"] = image_ref

        # Set edit prompt
        if self.NODE_POSITIVE_EDIT in self.prompt_data:
            self.prompt_data[self.NODE_POSITIVE_EDIT]["inputs"]["prompt"] = params.edit_prompt

        # Set negative prompt
        if self.NODE_NEGATIVE_EDIT in self.prompt_data:
            self.prompt_data[self.NODE_NEGATIVE_EDIT]["inputs"]["prompt"] = params.negative_prompt

        # Set KSampler parameters
        if self.NODE_KSAMPLER in self.prompt_data:
            self.prompt_data[self.NODE_KSAMPLER]["inputs"].update({
                "seed": params.seed,
                "steps": params.steps,
                "cfg": params.cfg,
                "sampler_name": params.sampler_name,
                "scheduler": params.scheduler,
                "denoise": params.denoise
            })

    def execute(self, params: ImageEditParams, output_dir: str = "./outputs") -> List[str]:
        """Execute image editing workflow"""
        import time
        start_time = time.time()

        # Ensure server is running
        if not self._ensure_server_running():
            raise ConnectionError("ComfyUI server is not available")

        # Auto-switch to normal service for image editing
        if self.config.service_manager_enabled:
            current_service = self._get_current_service()
            if current_service != "normal":
                print(f"[Service Manager] Auto-switching to 'normal' service for image editing")
                self._switch_service("normal", wait_for_recovery=True, timeout=120)

        self.connect()
        try:
            self.set_parameters(params)
            prompt_id = self._queue_prompt()
            result = self._poll_completion(prompt_id)
            outputs = self._save_outputs(result, output_dir, params.seed)

            elapsed = time.time() - start_time
            print(f"[Image Edit] Completed in {elapsed:.2f}s ({elapsed/60:.1f} minutes)")
            return outputs
        finally:
            self.close()

    def _save_outputs(self, result: Dict, output_dir: str, seed: int) -> List[str]:
        """Save edited images"""
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        saved_files = []

        for node_id, node_output in result.get("outputs", {}).items():
            if "images" in node_output:
                for img in node_output["images"]:
                    filename = img["filename"]
                    subfolder = img.get("subfolder", "")
                    folder_type = img.get("type", "output")

                    # Download image
                    params = {
                        "filename": filename,
                        "subfolder": subfolder,
                        "type": folder_type
                    }
                    response = self.session.get(
                        f"http://{self.config.server_address}/view",
                        params=params,
                        timeout=self.config.request_timeout
                    )
                    response.raise_for_status()

                    # Save with timestamp and seed
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    output_filename = f"edit_{timestamp}_seed{seed}_{filename}"
                    output_file_path = output_path / output_filename

                    with open(output_file_path, "wb") as f:
                        f.write(response.content)

                    saved_files.append(str(output_file_path))
                    print(f"Saved: {output_file_path}")

        return saved_files


class ImageToVideoWorkflow(Workflow):
    """Image-to-video generation workflow"""

    # Node IDs in the workflow (for new workflow with EasyLoraStack)
    NODE_LOAD_IMAGE = "97"
    NODE_POSITIVE_CLIP = "152"
    NODE_NEGATIVE_CLIP = "150"
    NODE_VIDEO_GEN = "149"
    NODE_SAVE_VIDEO = "108"
    # Model loader nodes (UnetLoaderGGUF)
    NODE_HIGH_MODEL = "175"  # High noise model
    NODE_LOW_MODEL = "176"   # Low noise model
    # EasyLoraStack nodes
    NODE_LORA_STACK_LOW = "187"   # easy loraStack (low noise)
    NODE_LORA_STACK_HIGH = "189"  # easy loraStack (high noise)

    # Model presets: (high_noise_file, low_noise_file)
    MODEL_PRESETS = {
        "default": (
            "Wan2.2-I2V-A14B-HighNoise-Q8_0.gguf",
            "Wan2.2-I2V-A14B-LowNoise-Q8_0.gguf",
        ),
        "smooth": (
            "smoothMixWan22I2VV20_highQ80.gguf",
            "smoothMixWan22I2VV20_lowQ80.gguf",
        ),
    }

    def _apply_lora_keywords(self, prompt: str, lora_keywords_enabled: bool, custom_mapping: Dict[str, List[str]]):
        """Apply LoRA keyword detection and update LoRA stack nodes"""
        if not lora_keywords_enabled:
            print("[LoRA] Keyword detection disabled, using workflow defaults")
            return

        # Use custom mapping if provided, otherwise use global mapping
        keyword_mapping = custom_mapping if custom_mapping else LORA_KEYWORD_MAPPING

        # Convert prompt to lowercase for matching
        prompt_lower = prompt.lower()

        # Find matching LoRAs based on keywords
        enabled_loras = set()
        for lora_pattern, keywords in keyword_mapping.items():
            for keyword in keywords:
                if keyword.lower() in prompt_lower:
                    enabled_loras.add(lora_pattern)
                    print(f"[LoRA] Keyword '{keyword}' detected → enabling: {lora_pattern}")
                    break

        # Update EasyLoraStack nodes
        for node_id in [self.NODE_LORA_STACK_LOW, self.NODE_LORA_STACK_HIGH]:
            if node_id not in self.prompt_data:
                continue

            node_data = self.prompt_data[node_id]
            if node_data.get("class_type") != "easy loraStack":
                continue

            # Get current inputs
            inputs = node_data.get("inputs", {})
            num_loras = inputs.get("num_loras", 0)

            # Check each LoRA slot
            for i in range(1, num_loras + 1):
                lora_name_key = f"lora_{i}_name"
                current_name = inputs.get(lora_name_key, "None")

                # Skip if already None or empty
                if not current_name or current_name == "None":
                    continue

                # Check if this LoRA matches any enabled pattern
                is_enabled = False
                for enabled_pattern in enabled_loras:
                    if enabled_pattern.lower() in current_name.lower():
                        is_enabled = True
                        break

                # Disable LoRA by setting name to "None" and strength to 0
                if not is_enabled:
                    print(f"[LoRA] Disabling: {current_name}")
                    self.prompt_data[node_id]["inputs"][lora_name_key] = "None"
                    # Also set strength to 0 for extra safety
                    strength_key = f"lora_{i}_strength"
                    if strength_key in inputs:
                        self.prompt_data[node_id]["inputs"][strength_key] = 0
                else:
                    print(f"[LoRA] Enabling: {current_name}")

    def set_parameters(self, params: ImageToVideoParams):
        """Set image-to-video parameters"""
        # Upload and set input image
        image_ref = self._upload_image(params.image_path, subfolder="")
        if self.NODE_LOAD_IMAGE in self.prompt_data:
            self.prompt_data[self.NODE_LOAD_IMAGE]["inputs"]["image"] = image_ref

        # Set model preset
        if params.model in self.MODEL_PRESETS:
            high_file, low_file = self.MODEL_PRESETS[params.model]
            if self.NODE_HIGH_MODEL in self.prompt_data:
                self.prompt_data[self.NODE_HIGH_MODEL]["inputs"]["unet_name"] = high_file
            if self.NODE_LOW_MODEL in self.prompt_data:
                self.prompt_data[self.NODE_LOW_MODEL]["inputs"]["unet_name"] = low_file
            print(f"[Model] Using preset '{params.model}': {high_file}")
        else:
            print(f"[Model] Unknown preset '{params.model}', using workflow defaults")

        # Set prompt
        if self.NODE_POSITIVE_CLIP in self.prompt_data:
            self.prompt_data[self.NODE_POSITIVE_CLIP]["inputs"]["text"] = params.prompt

        # Set negative prompt
        if self.NODE_NEGATIVE_CLIP in self.prompt_data:
            self.prompt_data[self.NODE_NEGATIVE_CLIP]["inputs"]["text"] = params.negative_prompt

        # Set video generation parameters
        if self.NODE_VIDEO_GEN in self.prompt_data:
            self.prompt_data[self.NODE_VIDEO_GEN]["inputs"].update({
                "width": params.width,
                "height": params.height,
                "length": params.length
            })

        # Apply LoRA keyword detection
        self._apply_lora_keywords(params.prompt, params.lora_keywords, params.lora_mapping)

    def execute(self, params: ImageToVideoParams, output_dir: str = "./outputs", reboot_first: bool = True) -> List[str]:
        """Execute image-to-video workflow"""
        import time
        start_time = time.time()

        # Ensure server is running
        if not self._ensure_server_running():
            raise ConnectionError("ComfyUI server is not available")

        # Service management for video generation
        if self.config.service_manager_enabled:
            # Use specified service if provided
            if params.service_name:
                self._switch_service(params.service_name, wait_for_recovery=True, timeout=120)
            else:
                # Auto-switch to no-cache service for memory-intensive video generation
                current_service = self._get_current_service()
                if current_service != "no-cache":
                    print(f"[Service Manager] Auto-switching to 'no-cache' service for video generation")
                    self._switch_service("no-cache", wait_for_recovery=True, timeout=120)
        # Fallback to reboot if service manager is not enabled and reboot_first is True
        elif reboot_first:
            print("[ComfyUI] Service manager not enabled, using reboot instead")
            self._reboot_server(wait_for_recovery=True, timeout=300)

        self.connect()
        try:
            self.set_parameters(params)
            prompt_id = self._queue_prompt()
            result = self._poll_completion(prompt_id)
            outputs = self._save_outputs(result, output_dir, params.seed)

            elapsed = time.time() - start_time
            print(f"[Image-to-Video] Completed in {elapsed:.2f}s ({elapsed/60:.1f} minutes)")
            return outputs
        finally:
            self.close()

    def _save_outputs(self, result: Dict, output_dir: str, seed: int) -> List[str]:
        """Save generated videos"""
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        saved_files = []

        for node_id, node_output in result.get("outputs", {}).items():
            # Check both 'videos' and 'images' (ComfyUI returns videos in 'images')
            media_list = node_output.get("videos", []) or node_output.get("images", [])

            for media in media_list:
                filename = media["filename"]
                subfolder = media.get("subfolder", "")
                folder_type = media.get("type", "output")

                # Check if it's a video file
                if not filename.endswith(('.mp4', '.webm', '.avi', '.mov')):
                    continue

                # Download video
                params = {
                    "filename": filename,
                    "subfolder": subfolder,
                    "type": folder_type
                }
                response = self.session.get(
                    f"http://{self.config.server_address}/view",
                    params=params,
                    timeout=self.config.request_timeout
                )
                response.raise_for_status()

                # Save with timestamp and seed
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                output_filename = f"i2v_{timestamp}_seed{seed}_{filename}"
                output_file_path = output_path / output_filename

                with open(output_file_path, "wb") as f:
                    f.write(response.content)

                saved_files.append(str(output_file_path))
                print(f"Saved: {output_file_path}")

        return saved_files


class AddAudioToVideoWorkflow(Workflow):
    """Add AI-generated audio to video workflow (MMAudio)"""

    # Node IDs in the workflow
    NODE_LOAD_VIDEO = "126"
    NODE_VIDEO_INFO = "112"
    NODE_MMAUDIO_SAMPLER = "92"
    NODE_MMAUDIO_FEATURES = "110"
    NODE_MMAUDIO_MODEL = "111"
    NODE_RIFE_INTERPOLATION = "119"
    NODE_VIDEO_COMBINE = "97"

    def set_parameters(self, params: AddAudioToVideoParams):
        """Set add-audio parameters"""
        # Upload and set input video
        video_ref = self._upload_video(params.video_path)
        if self.NODE_LOAD_VIDEO in self.prompt_data:
            self.prompt_data[self.NODE_LOAD_VIDEO]["inputs"]["video"] = video_ref

        # Set MMAudio parameters
        if self.NODE_MMAUDIO_SAMPLER in self.prompt_data:
            self.prompt_data[self.NODE_MMAUDIO_SAMPLER]["inputs"].update({
                "seed": params.seed,
                "steps": params.steps,
                "cfg": params.cfg,
                "prompt": params.prompt,
                "negative_prompt": params.negative_prompt
            })

        # Set RIFE interpolation parameters
        if self.NODE_RIFE_INTERPOLATION in self.prompt_data:
            self.prompt_data[self.NODE_RIFE_INTERPOLATION]["inputs"].update({
                "source_fps": params.source_fps,
                "target_fps": params.target_fps
            })

        # Set output filename prefix
        if self.NODE_VIDEO_COMBINE in self.prompt_data:
            self.prompt_data[self.NODE_VIDEO_COMBINE]["inputs"]["filename_prefix"] = params.filename_prefix

    def execute(self, params: AddAudioToVideoParams, output_dir: str = "./outputs") -> List[str]:
        """Execute add-audio-to-video workflow"""
        import time
        start_time = time.time()

        # Ensure server is running
        if not self._ensure_server_running():
            raise ConnectionError("ComfyUI server is not available")

        # Service management for audio generation
        if self.config.service_manager_enabled:
            if params.service_name:
                self._switch_service(params.service_name, wait_for_recovery=True, timeout=120)
            else:
                # Use normal service for audio generation
                current_service = self._get_current_service()
                if current_service != "normal":
                    print(f"[Service Manager] Auto-switching to 'normal' service for audio generation")
                    self._switch_service("normal", wait_for_recovery=True, timeout=120)

        self.connect()
        try:
            self.set_parameters(params)
            prompt_id = self._queue_prompt()
            result = self._poll_completion(prompt_id)
            outputs = self._save_outputs(result, output_dir, params.seed)

            elapsed = time.time() - start_time
            print(f"[Add Audio] Completed in {elapsed:.2f}s ({elapsed/60:.1f} minutes)")
            return outputs
        finally:
            self.close()

    def _upload_video(self, video_path: str) -> str:
        """Upload video to ComfyUI server via /upload/image endpoint"""
        filename = os.path.basename(video_path)
        with open(video_path, "rb") as f:
            files = {"image": (filename, f)}
            data = {"overwrite": "true"}
            response = self.session.post(
                f"http://{self.config.server_address}/upload/image",
                files=files,
                data=data,
                timeout=self.config.request_timeout
            )
            response.raise_for_status()
            result = response.json()
            print(f"[Audio] Uploaded video: {filename}")
            return result.get('name', filename)

    def _save_outputs(self, result: Dict, output_dir: str, seed: int) -> List[str]:
        """Save generated videos with audio"""
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        saved_files = []

        for node_id, node_output in result.get("outputs", {}).items():
            # VHS VideoCombine uses "gifs" key for video outputs
            video_list = node_output.get("videos") or node_output.get("gifs")
            if video_list:
                for video in video_list:
                    filename = video["filename"]
                    subfolder = video.get("subfolder", "")
                    folder_type = video.get("type", "output")

                    # Download video
                    params = {
                        "filename": filename,
                        "subfolder": subfolder,
                        "type": folder_type
                    }
                    response = self.session.get(
                        f"http://{self.config.server_address}/view",
                        params=params,
                        timeout=self.config.request_timeout
                    )
                    response.raise_for_status()

                    # Save with timestamp and seed
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    output_filename = f"audio_{timestamp}_seed{seed}_{filename}"
                    output_file_path = output_path / output_filename

                    with open(output_file_path, "wb") as f:
                        f.write(response.content)

                    saved_files.append(str(output_file_path))
                    print(f"Saved: {output_file_path}")

        return saved_files


# =============================================================================
# Workflow Factory
# =============================================================================

class WorkflowFactory:
    """Factory for creating workflow instances"""

    _workflows: Dict[WorkflowType, type] = {
        WorkflowType.TEXT_TO_IMAGE: TextToImageWorkflow,
        WorkflowType.IMAGE_EDIT: ImageEditWorkflow,
        WorkflowType.IMAGE_TO_VIDEO: ImageToVideoWorkflow,
        WorkflowType.ADD_AUDIO_TO_VIDEO: AddAudioToVideoWorkflow,
    }

    @classmethod
    def create(
        cls,
        workflow_type: WorkflowType,
        workflow_dir: str = None,
        config: ComfyUIConfig = None
    ) -> Workflow:
        """Create a workflow instance"""
        if config is None:
            config = ComfyUIConfig()

        # Use default workflows directory if not specified
        if workflow_dir is None:
            workflow_dir = str(_DEFAULT_WORKFLOWS_DIR)

        workflow_files = {
            WorkflowType.TEXT_TO_IMAGE: "image_workflow.json",
            WorkflowType.IMAGE_EDIT: "edit_workflow.json",
            WorkflowType.IMAGE_TO_VIDEO: "video_workflow.json",
            WorkflowType.ADD_AUDIO_TO_VIDEO: "audio_workflow.json",
        }

        if workflow_type not in cls._workflows:
            raise ValueError(f"Unknown workflow type: {workflow_type}")

        # Convert to Path for cross-platform compatibility
        workflow_dir_path = Path(workflow_dir)
        workflow_path = str(workflow_dir_path / workflow_files[workflow_type])
        workflow_class = cls._workflows[workflow_type]

        return workflow_class(workflow_path, config)

    @classmethod
    def register_workflow(cls, workflow_type: WorkflowType, workflow_class: type):
        """Register a new workflow type"""
        cls._workflows[workflow_type] = workflow_class


# =============================================================================
# Main Runner Class
# =============================================================================

class ComfyUIRunner:
    """Main runner class for ComfyUI workflows"""

    def __init__(self, config: ComfyUIConfig = None):
        self.config = config or ComfyUIConfig()
        self._current_workflow: Optional[Workflow] = None

    def generate_image(
        self,
        prompt: str,
        negative_prompt: str = "",
        width: int = 928,
        height: int = 1664,
        output_dir: str = "./outputs",
        seed: Optional[int] = None,
        **kwargs
    ) -> List[str]:
        """Generate image from text prompt"""
        params = TextToImageParams(
            positive_prompt=prompt,
            negative_prompt=negative_prompt,
            width=width,
            height=height,
            seed=seed,
            **kwargs
        )
        workflow = WorkflowFactory.create(WorkflowType.TEXT_TO_IMAGE, config=self.config)
        return workflow.execute(params, output_dir)

    def edit_image(
        self,
        image_path: str,
        edit_prompt: str,
        negative_prompt: str = "",
        output_dir: str = "./outputs",
        seed: Optional[int] = None,
        **kwargs
    ) -> List[str]:
        """Edit an image with text instructions"""
        params = ImageEditParams(
            image_path=image_path,
            edit_prompt=edit_prompt,
            negative_prompt=negative_prompt,
            seed=seed,
            **kwargs
        )
        workflow = WorkflowFactory.create(WorkflowType.IMAGE_EDIT, config=self.config)
        return workflow.execute(params, output_dir)

    def generate_video(
        self,
        image_path: str,
        prompt: str,
        negative_prompt: str = "",
        width: int = 480,
        height: int = 832,
        length: int = 81,
        output_dir: str = "./outputs",
        seed: Optional[int] = None,
        reboot_first: bool = True,
        service_name: Optional[str] = None,
        **kwargs
    ) -> List[str]:
        """Generate video from image"""
        params = ImageToVideoParams(
            image_path=image_path,
            prompt=prompt,
            negative_prompt=negative_prompt,
            width=width,
            height=height,
            length=length,
            seed=seed,
            service_name=service_name,
            **kwargs
        )
        workflow = WorkflowFactory.create(WorkflowType.IMAGE_TO_VIDEO, config=self.config)
        return workflow.execute(params, output_dir, reboot_first=reboot_first)

    def add_audio(
        self,
        video_path: str,
        prompt: str = "",
        negative_prompt: str = "",
        steps: int = 100,
        cfg: float = 6.0,
        source_fps: int = 16,
        target_fps: int = 25,
        output_dir: str = "./outputs",
        seed: Optional[int] = None,
        service_name: Optional[str] = None,
        **kwargs
    ) -> List[str]:
        """Add AI-generated audio to video using MMAudio"""
        params = AddAudioToVideoParams(
            video_path=video_path,
            prompt=prompt,
            negative_prompt=negative_prompt,
            steps=steps,
            cfg=cfg,
            source_fps=source_fps,
            target_fps=target_fps,
            seed=seed,
            service_name=service_name,
            **kwargs
        )
        workflow = WorkflowFactory.create(WorkflowType.ADD_AUDIO_TO_VIDEO, config=self.config)
        return workflow.execute(params, output_dir)


# =============================================================================
# CLI Interface
# =============================================================================

def main():
    """Command-line interface"""
    import argparse

    parser = argparse.ArgumentParser(
        description="ComfyUI Workflow Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Text to Image
  %(prog)s t2i "a beautiful sunset over mountains" --output ./outputs

  # Image Edit
  %(prog)s edit input.jpg "make the sky more dramatic" --output ./outputs

  # Image to Video
  %(prog)s i2v input.jpg "camera pans across the landscape" --output ./outputs

  # Add Audio to Video (MMAudio)
  %(prog)s audio input.mp4 "ambient music with gentle piano" --output ./outputs
        """
    )

    parser.add_argument(
        "command",
        choices=["t2i", "edit", "i2v", "audio"],
        help="Command: t2i (text-to-image), edit (image edit), i2v (image-to-video), audio (add audio to video)"
    )
    parser.add_argument("input", help="Input: prompt for t2i/i2v, or image path for edit/i2v")
    parser.add_argument("prompt", nargs="?", help="Prompt/edit instruction")
    parser.add_argument("--negative", default="", help="Negative prompt")
    parser.add_argument("--output", default="./outputs", help="Output directory")
    parser.add_argument("--server", default="192.168.1.179:8188", help="ComfyUI server address")
    parser.add_argument("--seed", type=int, help="Random seed")
    parser.add_argument("--width", type=int, help="Image width")
    parser.add_argument("--height", type=int, help="Image height")
    parser.add_argument("--no-reboot", action="store_true", help="Skip server reboot before i2v (not recommended)")
    parser.add_argument("--service", help="Service name to switch to (requires service manager)")
    parser.add_argument("--service-manager", help="Service manager address (e.g., 192.168.1.179:9999)")
    parser.add_argument("--disable-service-manager", action="store_true", help="Disable service manager integration (enabled by default)")
    parser.add_argument("--model", choices=["default", "smooth"], default="default",
                        help="Video model preset: 'default' (Wan2.2-I2V-A14B) or 'smooth' (smoothMixWan22I2VV20)")

    args = parser.parse_args()

    # Configure
    config = ComfyUIConfig(server_address=args.server)
    if args.disable_service_manager:
        config.service_manager_enabled = False
    if args.service_manager:
        config.service_manager_address = args.service_manager
    runner = ComfyUIRunner(config)

    try:
        if args.command == "t2i":
            print(f"Generating image: {args.input}")
            # Build kwargs with only provided values
            t2i_kwargs = {"output_dir": args.output}
            if args.negative:
                t2i_kwargs["negative_prompt"] = args.negative
            if args.seed is not None:
                t2i_kwargs["seed"] = args.seed
            if args.width is not None:
                t2i_kwargs["width"] = args.width
            if args.height is not None:
                t2i_kwargs["height"] = args.height
            outputs = runner.generate_image(
                prompt=args.input,
                **t2i_kwargs
            )
            print(f"Generated {len(outputs)} image(s)")

        elif args.command == "edit":
            print(f"Editing image: {args.input}")
            if not args.prompt:
                parser.error("edit command requires a prompt argument")
            outputs = runner.edit_image(
                image_path=args.input,
                edit_prompt=args.prompt,
                negative_prompt=args.negative,
                output_dir=args.output,
                seed=args.seed
            )
            print(f"Generated {len(outputs)} image(s)")

        elif args.command == "i2v":
            print(f"Generating video from: {args.input}")
            if not args.prompt:
                parser.error("i2v command requires a prompt argument")
            # Build kwargs with only provided values
            i2v_kwargs = {
                "output_dir": args.output,
                "reboot_first": not args.no_reboot
            }
            if args.negative:
                i2v_kwargs["negative_prompt"] = args.negative
            if args.seed is not None:
                i2v_kwargs["seed"] = args.seed
            if args.width is not None:
                i2v_kwargs["width"] = args.width
            if args.height is not None:
                i2v_kwargs["height"] = args.height
            if args.service:
                i2v_kwargs["service_name"] = args.service
            if args.model:
                i2v_kwargs["model"] = args.model
            outputs = runner.generate_video(
                image_path=args.input,
                prompt=args.prompt,
                **i2v_kwargs
            )
            print(f"Generated {len(outputs)} video(s)")

        elif args.command == "audio":
            print(f"Adding audio to video: {args.input}")
            # Build kwargs with only provided values
            audio_kwargs = {"output_dir": args.output}
            if args.negative:
                audio_kwargs["negative_prompt"] = args.negative
            if args.seed is not None:
                audio_kwargs["seed"] = args.seed
            if args.service:
                audio_kwargs["service_name"] = args.service
            outputs = runner.add_audio(
                video_path=args.input,
                prompt=args.prompt or "",
                **audio_kwargs
            )
            print(f"Generated {len(outputs)} video(s) with audio")

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    # Need to import time for polling
    import time
    main()
