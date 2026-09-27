# Multilingual implementation

Supported patient-output codes:
- `en` English
- `ur` Urdu
- `ar` Arabic
- `pa_shah` Punjabi Shahmukhi
- `pa` Punjabi Gurmukhi
- `ps` Pashto
- `sd` Sindhi

## STT
faster-whisper stores segment timestamps, average log probability, no-speech probability and a derived review confidence. Optional primary/secondary passes are merged by temporal overlap/confidence for code-switching. This is a prototype strategy and must be evaluated with WER on real mixed-language recordings.

## Translation
NLLB produces patient-language text from the doctor-approved English explanation. Safety checks compare:
- numbers/units,
- medication names/tokens,
- expected script,
- back-translation semantic entailment where supported.

Urdu output is validated for Arabic-script content and significant Devanagari leakage is rejected/flagged.

## Punjabi Shahmukhi
NLLB's Punjabi path is Gurmukhi. MediExplain+ mechanically transliterates that translation to Shahmukhi for display. It does not ask an LLM to “polish” medical instructions because free-form polishing can change clinical meaning. For speech, the original Gurmukhi translation is sent to the Punjabi MMS voice, avoiding the old Urdu-voice substitute.

## TTS
MMS-TTS is local-first. gTTS remains available only as an explicit opt-in cloud fallback (`ALLOW_CLOUD_TTS_FALLBACK=true`) because it transfers text to an external service.

## Evaluation
Do not label a language “high quality” from configuration. Final quality claims must come from BLEU/chrF/COMET (where appropriate), critical-token preservation and human bilingual review.
