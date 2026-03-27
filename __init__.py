"""
ComfyUI Generator Skill Package

A unified interface for executing ComfyUI workflows including:
- Text-to-Image generation
- Image editing
- Image-to-Video generation

Example usage:
    from skills.comfyui_generator import ComfyUIRunner, ComfyUIConfig

    config = ComfyUIConfig(server_address="192.168.1.179:8188")
    runner = ComfyUIRunner(config)

    # Text to Image
    runner.generate_image("a beautiful landscape", output_dir="./outputs")

    # Image Edit
    runner.edit_image("input.jpg", "make the colors more vibrant")

    # Image to Video
    runner.generate_video("input.jpg", "camera slowly pans right")
"""

from .comfyui_runner import (
    # Main runner
    ComfyUIRunner,

    # Configuration
    ComfyUIConfig,
    WorkflowType,

    # Workflow parameters
    WorkflowParams,
    TextToImageParams,
    ImageEditParams,
    ImageToVideoParams,

    # Workflow factory
    WorkflowFactory,

    # Workflow classes
    Workflow,
    TextToImageWorkflow,
    ImageEditWorkflow,
    ImageToVideoWorkflow,
)

__all__ = [
    "ComfyUIRunner",
    "ComfyUIConfig",
    "WorkflowType",
    "WorkflowParams",
    "TextToImageParams",
    "ImageEditParams",
    "ImageToVideoParams",
    "WorkflowFactory",
    "Workflow",
    "TextToImageWorkflow",
    "ImageEditWorkflow",
    "ImageToVideoWorkflow",
]

__version__ = "1.0.0"
