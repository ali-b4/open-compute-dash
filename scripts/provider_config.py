"""Fixed-model direct endpoints shared by runners and reports."""
MODEL = "qwen/qwen3.8-27b"
PROVIDERS = {
    "venice": ("https://api.venice.ai/api/v1/chat/completions", "qwen-3-8-27b"),
    "chutes": ("https://llm.chutes.ai/v1/chat/completions", "Qwen/Qwen3.8-27B-TEE"),
    "darkbloom": ("https://api.darkbloom.dev/v1/chat/completions", "EigenLabs/Qwen3.8-27B-4bit-mtp"),
    "ionet": ("https://api.intelligence.io.solutions/api/v1/chat/completions", "Qwen/Qwen3.8-27B"),
}
PROVIDER_LABELS = {name: name.title() for name in PROVIDERS}
PROVIDER_LABELS["ionet"] = "io.net"
