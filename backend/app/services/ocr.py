"""Prescription OCR with image preprocessing and Tesseract/PaddleOCR comparison."""
from __future__ import annotations
import logging,shutil
from pathlib import Path
from app.core.config import settings
logger=logging.getLogger(__name__)

# This function prepares an uploaded prescription image before OCR is applied.
# It handles HEIC images when support is available, corrects image orientation,
# enlarges small images and improves contrast and sharpness so medicine names,
# strengths and instructions are easier for the OCR engines to recognise.

def _open(path:Path):
    from PIL import Image,ImageOps,ImageEnhance,ImageFilter
    if path.suffix.lower() in {".heic",".heif"}:
        try:
            import pillow_heif
            pillow_heif.register_heif_opener()
        except Exception as exc:
            raise RuntimeError("HEIC support requires pillow-heif") from exc
    img=Image.open(path)
    img=ImageOps.exif_transpose(img).convert("RGB")
    # Upscale small photos, grayscale, autocontrast and mild sharpening.
    if min(img.size)<1600:
        scale=1600/min(img.size)
        img=img.resize((int(img.width*scale),int(img.height*scale)))
    gray=ImageOps.grayscale(img)
    gray=ImageOps.autocontrast(gray)
    gray=ImageEnhance.Contrast(gray).enhance(1.5)
    gray=gray.filter(ImageFilter.SHARPEN)
    return gray

# This helper saves the cleaned prescription image as a temporary PNG that can
# be passed consistently to either OCR engine.

def _preprocess(path:Path)->Path:
    img=_open(path)
    out=path.with_suffix(".pre.png")
    img.save(out)
    return out


# This function runs Tesseract OCR on the preprocessed prescription image.
# It extracts the recognised text and also collects word-level confidence values
# so the system can estimate how reliable the OCR result is before doctor review.
def _tesseract(path:Path)->dict|None:
    if not shutil.which("tesseract"):return None
    try:
        import pytesseract
        from pytesseract import Output
        text=pytesseract.image_to_string(str(path),lang=settings.OCR_LANGS).strip()
        data=pytesseract.image_to_data(str(path),lang=settings.OCR_LANGS,output_type=Output.DICT)
        confs=[]
        for c in data.get("conf",[]):
            try:
                v=float(c)
                if v>=0:confs.append(v)
            except Exception:pass
        conf=(sum(confs)/len(confs)/100) if confs else 0.0
        return {"text":text,"confidence":round(conf,3),"engine":"tesseract"}
    except Exception as exc:
        logger.warning("Tesseract OCR failed: %s",exc);return None

# This function runs PaddleOCR as the alternative prescription-recognition engine.
# PaddleOCR detects and recognises text from the image and returns confidence
# scores for the detected lines, allowing its result to be compared with the
# Tesseract output when both engines are enabled.
def _paddle(path:Path)->dict|None:
    try:
        from paddleocr import PaddleOCR
    except Exception:return None
    try:
        ocr=PaddleOCR(use_angle_cls=True,lang="en",show_log=False)
        result=ocr.ocr(str(path),cls=True)
        lines=[];confs=[]
        for page in result or []:
            for item in page or []:
                if len(item)>=2 and isinstance(item[1],(list,tuple)):
                    lines.append(str(item[1][0]));confs.append(float(item[1][1]))
        return {"text":"\n".join(lines).strip(),"confidence":round(sum(confs)/len(confs),3) if confs else 0.0,"engine":"paddleocr"}
    except Exception as exc:
        logger.warning("PaddleOCR failed: %s",exc);return None

# This is the main OCR extraction function. It preprocesses the prescription,
# runs whichever OCR engines are enabled in the application settings and selects
# the result with the highest confidence. The other engine scores are retained
# for comparison, while low-confidence output is explicitly flagged so the
# recognised prescription text can be checked and corrected by the doctor.
def extract_text(image_path:str|Path)->dict:
    src=Path(image_path)
    if not src.exists():return {"text":"","confidence":0.0,"available":False,"engine":None,"warning":"Image not found"}
    try: prep=_preprocess(src)
    except Exception as exc:
        return {"text":"","confidence":0.0,"available":False,"engine":None,"warning":str(exc)}
    results=[]
    if settings.OCR_ENGINE in {"auto","tesseract"}:
        r=_tesseract(prep)
        if r:results.append(r)
    if settings.OCR_ENGINE in {"auto","paddle"}:
        r=_paddle(prep)
        if r:results.append(r)
    if not results:
        return {"text":"","confidence":0.0,"available":False,"engine":None,
                "warning":"No OCR engine is available. Install Tesseract or optional PaddleOCR."}
    best=max(results,key=lambda r:r["confidence"])
    best["available"]=True
    best["alternatives"]=[{"engine":r["engine"],"confidence":r["confidence"]} for r in results]
    best["warning"]=(
        "Low OCR confidence. Doctor review and correction are required."
        if best["confidence"]<settings.OCR_LOW_CONFIDENCE else None
    )
    return best

# After OCR has converted the prescription image into text, this function sends
# that text into the same local LLM structured-extraction pipeline used elsewhere
# in MediExplain+. The LLM organises the recognised prescription information into
# structured clinical fields, while the OCR text remains the source that the
# extracted medication information must be grounded in.
async def structure_ocr_text(text:str)->dict:
    from app.services import llm
    return await llm.extract_structured_data(f"PRESCRIPTION OCR TEXT:\n{text}") if text.strip() else {}


# This function combines both stages of prescription processing. It first runs
# image OCR to obtain the recognised prescription text and confidence result,
# then passes that text to the LLM structured-extraction step so the application
# can return both the original OCR evidence and the structured information for
# later doctor review.
async def extract_prescription_structure(image_path:str|Path)->dict:
    ocr=extract_text(image_path)
    structured=await structure_ocr_text(ocr["text"]) if ocr.get("text") else None
    return {"ocr":ocr,"structured":structured}
