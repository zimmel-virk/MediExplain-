"""
End-to-end smoke test. Runs the AI pipeline against a sample text transcript
(skips STT) to verify LLM + translation + TTS are wired up correctly.

Usage (with Ollama running):
    cd backend
    source .venv/bin/activate
    python -m scripts.smoke_test
"""
import asyncio
import sys

from app.services import llm, translation, tts

# This smoke test provides a quick end-to-end check of the main MediExplain+ AI
# services without requiring a recorded consultation. It uses a fixed sample
# transcript to exercise the local LLM summarisation and structured extraction
# stages, translates the generated patient summary from English to Urdu, and then
# attempts to synthesise the translated text as speech. Each stage reports its
# result separately so model or service configuration problems can be identified
# before running the complete consultation workflow.

SAMPLE_TRANSCRIPT = """
Doctor: Hello, how are you feeling today?
Patient: I've had a fever for three days, around 101 degrees, and a sore throat.
Doctor: Any cough or difficulty breathing?
Patient: A dry cough, but no breathing problems.
Doctor: Let me examine you. Your throat is red and your lymph nodes are slightly swollen.
This looks like a viral upper respiratory infection. I'm going to prescribe paracetamol
500 milligrams, you should take one tablet every six hours as needed for fever, for the
next five days. Drink plenty of fluids and rest. If your fever goes above 103 degrees
or you have trouble breathing, come back immediately. We'll see you again in one week
if you're not better.
"""


async def main():
    print("─" * 60)
    print("Step 1: LLM summarisation")
    print("─" * 60)
    try:
        summary = await llm.summarise_consultation(SAMPLE_TRANSCRIPT)
    except Exception as e:
        print(f"❌ LLM failed: {e}")
        print("\nIs Ollama running?  Try:  ollama serve")
        print("Did you pull the model?  Try:  ollama pull llama3.1:8b")
        sys.exit(1)
    print("\n🩺 CLINICAL NOTE:\n", summary["clinical_note"])
    print("\n👤 PATIENT SUMMARY:\n", summary["patient_summary"])

    print("\n" + "─" * 60)
    print("Step 2: Structured extraction")
    print("─" * 60)
    structured = await llm.extract_structured_data(SAMPLE_TRANSCRIPT)
    import json
    print(json.dumps(structured, indent=2))

    print("\n" + "─" * 60)
    print("Step 3: Translation EN → Urdu (first run downloads ~2.5 GB)")
    print("─" * 60)
    try:
        translated = await asyncio.to_thread(
            translation.translate, summary["patient_summary"], "en", "ur"
        )
        print(translated)
    except Exception as e:
        print(f"❌ Translation failed: {e}")
        sys.exit(1)

    print("\n" + "─" * 60)
    print("Step 4: TTS (Urdu)")
    print("─" * 60)
    try:
        audio_path = await asyncio.to_thread(tts.synthesise, translated, "ur")
        print(f"✓ Audio written to: {audio_path}")
    except Exception as e:
        print(f"⚠ TTS failed (needs internet for gTTS): {e}")

    print("\n✅ Pipeline smoke test complete.")


if __name__ == "__main__":
    asyncio.run(main())
