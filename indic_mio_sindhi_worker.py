from __future__ import annotations

import gc
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent

os.environ.setdefault(
    "HF_HOME",
    str(PROJECT_ROOT / "indic_mio_cache"),
)
os.environ.setdefault(
    "TOKENIZERS_PARALLELISM",
    "false",
)
os.environ.setdefault(
    "OMP_NUM_THREADS",
    "2",
)
os.environ.setdefault(
    "MKL_NUM_THREADS",
    "2",
)

import soundfile as sf
import torch

from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
)

from miocodec import (
    MioCodecModel,
    load_audio,
)


MODEL = "SPRINGLab/Indic-Mio"
CODEC = "Aratako/MioCodec-25Hz-24kHz"

SPEECH_OFFSET = 151669


def main() -> None:
    payload = json.load(sys.stdin)

    text = str(
        payload.get("text") or ""
    ).strip()

    output = Path(
        payload["output"]
    )

    reference_path = Path(
        payload["reference"]
    )

    if not text:
        raise RuntimeError(
            "Sindhi TTS received empty text."
        )

    if not reference_path.exists():
        raise RuntimeError(
            "Sindhi speaker reference is missing."
        )

    output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    tokenizer = AutoTokenizer.from_pretrained(
        MODEL,
        trust_remote_code=True,
    )

    prompt = tokenizer.apply_chat_template(
        [
            {
                "role": "user",
                "content": text,
            }
        ],
        tokenize=False,
        add_generation_prompt=True,
    )

    inputs = tokenizer(
        prompt,
        return_tensors="pt",
    )

    model = (
        AutoModelForCausalLM
        .from_pretrained(
            MODEL,
            dtype=torch.float32,
            trust_remote_code=True,
            low_cpu_mem_usage=True,
        )
    )

    model.eval()
    model.cpu()

    with torch.inference_mode():
        generated_output = model.generate(
            **inputs,
            max_new_tokens=768,
            do_sample=True,
            temperature=0.9,
            top_p=0.9,
        )

    generated = generated_output[
        0,
        inputs["input_ids"].shape[1]:
    ]

    audio_codes = [
        token.item() - SPEECH_OFFSET
        for token in generated
        if (
            SPEECH_OFFSET
            <= token.item()
            < SPEECH_OFFSET + 12800
        )
    ]

    if not audio_codes:
        raise RuntimeError(
            "Indic-Mio generated no Sindhi "
            "speech tokens."
        )

    del model
    del generated
    del generated_output
    del inputs

    gc.collect()

    codec = MioCodecModel.from_pretrained(
        CODEC
    )

    codec.eval()
    codec.cpu()

    reference = load_audio(
        str(reference_path),
        sample_rate=codec.config.sample_rate,
    )

    reference = reference.cpu()

    with torch.inference_mode():
        features = codec.encode(
            reference,
            return_content=False,
            return_global=True,
        )

    global_embedding = (
        features.global_embedding
    )

    if global_embedding is None:
        raise RuntimeError(
            "MioCodec produced no "
            "speaker embedding."
        )

    if global_embedding.ndim != 1:
        raise RuntimeError(
            "Unexpected MioCodec "
            "speaker embedding shape."
        )

    codes = torch.tensor(
        audio_codes,
        dtype=torch.long,
    )

    if codes.ndim != 1:
        raise RuntimeError(
            "Unexpected Sindhi "
            "content-token shape."
        )

    with torch.inference_mode():
        waveform = codec.decode(
            content_token_indices=codes,
            global_embedding=global_embedding,
        )

    audio = (
        waveform
        .detach()
        .cpu()
        .float()
        .numpy()
    )

    sf.write(
        str(output),
        audio,
        codec.config.sample_rate,
    )

    if (
        not output.exists()
        or output.stat().st_size <= 1000
    ):
        raise RuntimeError(
            "Sindhi TTS output is invalid."
        )

    print(
        json.dumps(
            {
                "ok": True,
                "output": str(output),
                "speech_tokens": len(
                    audio_codes
                ),
                "sample_rate":
                    codec.config.sample_rate,
                "bytes":
                    output.stat().st_size,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
