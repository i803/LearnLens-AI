from __future__ import annotations
import asyncio, hashlib, time
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from ..schemas import *
from ..services import analyze_work, persist_work_analysis_bounded, diagnose, generate_diagnostic, evaluate_diagnostic, lesson, quiz, evaluate_quiz, TopicContentUnavailable
from ..parsing import pdf_to_inputs, image_to_input
from ..cache import cache_get, cache_put
from ..notes import infer_misconception
from ..config import MAX_UPLOAD_MB
from ..demo_data import demo_analysis, DIAGNOSTICS, QUIZ_BANK, LESSONS, CONCEPTS

router = APIRouter(tags=["AI learning flow"])

# SHA-256 of web/public/sample_math_test.pdf. Only that exact bundled file may
# take the deterministic demo path; a user's file with the same name still gets analyzed.
BUNDLED_DEMO_PDF_SHA256 = "042891babf406ee9c119aac05afff344b029f4a3deb42069e1cdd5cc0cf8e0e2"

@router.post("/work/analyze", response_model=WorkAnalysis)
async def work_analyze(files: list[UploadFile] = File(default=[]), studentId: str = Form("demo-student"), demo: bool = False):
    if demo:
        return WorkAnalysis.model_validate({**demo_analysis(), "provider": "Bundled sample", "fromCache": False})
    if not files:
        result = await analyze_work("", [], student_id=studentId)
        return result
    total = 0
    text: list[str] = []
    images: list[tuple[str, bytes]] = []
    fingerprints: list[bytes] = []
    file_meta: list[tuple[str, str, bytes]] = []
    limit = int(MAX_UPLOAD_MB * 1024 * 1024)
    demo_file_candidate = len(files) == 1 and (files[0].filename or "").lower() == "sample_math_test.pdf"
    demo_file = False
    preprocess_started = time.perf_counter()
    preprocess_timeout_seconds = 12.0
    for upload in files[:6]:
        data = await upload.read()
        total += len(data)
        if total > limit:
            raise HTTPException(413, f"Files exceed the {MAX_UPLOAD_MB:g} MB upload limit")
        content_type = upload.content_type or ""
        filename = upload.filename or "uploaded-work"
        if not (data[:5] == b"%PDF-" or data[:8] == b"\x89PNG\r\n\x1a\n" or data[:3] == b"\xff\xd8\xff" or (data[:4] == b"RIFF" and data[8:12] == b"WEBP")):
            raise HTTPException(415, "Only real PDF, PNG, JPEG or WebP files are accepted.")
        fingerprints.append(filename.encode() + b"\0" + content_type.encode() + b"\0" + data)
        file_meta.append((filename, content_type, data))
        # The explicit bundled-demo action should never wait on a live model or render
        # the same static PDF. Require the exact bundled bytes so an ordinary user file
        # named sample_math_test.pdf is not mistaken for demo data.
        if demo_file_candidate and hashlib.sha256(data).hexdigest() == BUNDLED_DEMO_PDF_SHA256:
            demo_file = True
            continue
        remaining_preprocess = preprocess_timeout_seconds - (time.perf_counter() - preprocess_started)
        if remaining_preprocess <= 0:
            raise HTTPException(422, "File preprocessing exceeded 12 seconds. Upload fewer or smaller files.")
        if content_type == "application/pdf" or filename.lower().endswith(".pdf"):
            try:
                extracted_text, pages = await asyncio.wait_for(asyncio.to_thread(pdf_to_inputs, data), timeout=remaining_preprocess)
            except asyncio.TimeoutError as exc:
                raise HTTPException(422, "PDF processing took too long. Try a smaller PDF with fewer pages.") from exc
            except ValueError as exc:
                raise HTTPException(422, str(exc)) from exc
            text.append(extracted_text)
            images.extend(pages)
        elif content_type.startswith("image/"):
            try:
                extracted_text, pages = await asyncio.wait_for(asyncio.to_thread(image_to_input, data, content_type), timeout=remaining_preprocess)
            except asyncio.TimeoutError as exc:
                raise HTTPException(422, "Image processing took too long. Try a smaller image.") from exc
            text.append(extracted_text)
            images.extend(pages)
        else:
            raise HTTPException(415, f"Unsupported file type: {content_type or 'unknown'}")
    print(f"PREPROCESS_END elapsed_ms={(time.perf_counter()-preprocess_started)*1000:.1f} files={len(file_meta)} bytes={total}", flush=True)
    if demo_file:
        result = await analyze_work("", [], student_id=studentId)
        print(f"WORK_ANALYZE_DEMO_FAST_PATH elapsed_ms={(time.perf_counter()-preprocess_started)*1000:.1f}", flush=True)
        return result
    fingerprint = hashlib.sha256(b"learnlens-work-v2\0" + b"\0".join(fingerprints)).hexdigest()
    # Cache is still fingerprint-addressed, but scoped to a student to prevent cross-profile reuse.
    cache_key = hashlib.sha256((studentId + "\0" + fingerprint).encode()).hexdigest()
    cached = cache_get(cache_key, "work-analysis", student_id=studentId)
    if cached:
        cached["fromCache"] = True
        cached["provider"] = cached.get("provider") or ("Bundled sample" if cached.get("source") == "demo" else "Saved result")
        result = WorkAnalysis.model_validate(cached)
        await persist_work_analysis_bounded(studentId, result.model_dump(), filename=file_meta[0][0], file_type=file_meta[0][1])
        return result
    try:
        print(f"WORK_ANALYZE_START files={len(file_meta)} bytes={total}", flush=True)
        result = await analyze_work("\n".join(text), images, student_id=studentId, allow_demo_fallback=demo_file, filename=file_meta[0][0], file_type=file_meta[0][1])
    except RuntimeError as exc:
        raise HTTPException(503, detail=str(exc)) from exc
    print(f"WORK_ANALYZE_END source={result.source} questions={len(result.questions)}", flush=True)
    payload = result.model_dump()
    if result.source in {"ai", "demo"}:
        cache_put(cache_key, "work-analysis", payload, student_id=studentId)
    return result

@router.post("/diagnosis", response_model=DiagnosisResponse)
async def diagnosis_route(req: DiagnosisRequest, demo: bool = False):
    if demo:
        return DiagnosisResponse(weakestConceptId="sets-types", weakestConceptName="Types of sets", confidence=0.91,
            evidence=["Q2A: empty-set misconception", "Q3: finite versus infinite", "Q7: disjoint sets"],
            diagnosis="Several answers suggest confusion about empty, finite and infinite sets.",
            recommendation="Verify these concepts with three short questions.")
    return await diagnose(req)

@router.post("/diagnostic/generate", response_model=DiagnosticGenerateResponse)
async def diagnostic_generate(req: DiagnosticGenerateRequest, demo: bool = False):
    if demo:
        bank = DIAGNOSTICS.get(req.conceptId, DIAGNOSTICS["sets-types"])
        questions = [DiagnosticQuestion.model_validate(q) for q in (bank * 2)[:req.count]]
        # All returned IDs must be unique even for five-question topic flows.
        for i, question in enumerate(questions):
            question.questionId = f"demo-{req.conceptId}-{i + 1}"
        return DiagnosticGenerateResponse(questions=questions)
    try:
        return await generate_diagnostic(req)
    except TopicContentUnavailable as exc:
        raise HTTPException(503, detail=str(exc)) from exc

@router.post("/diagnostic/evaluate", response_model=DiagnosticEvaluateResponse)
async def diagnostic_evaluate(req: DiagnosticEvaluateRequest, demo: bool = False):
    if demo:
        bank = DIAGNOSTICS.get(req.conceptId, DIAGNOSTICS["sets-types"])
        correct = sum(1 for qid, answer in req.answers.items()
                      if qid.startswith(f"demo-{req.conceptId}-")
                      and qid.rsplit("-", 1)[-1].isdigit()
                      and answer.strip().casefold() == bank[(int(qid.rsplit("-", 1)[-1]) - 1) % len(bank)]["correctAnswer"].strip().casefold())
        total = len(req.answers)
        score = round(100 * correct / total, 1) if total else 0
        return DiagnosticEvaluateResponse(correct=correct, total=total, scorePercent=score,
            confirmedWeakness=score < 70, confidence=0.9, likelyMisconception="Types of sets",
            likelySkill=CONCEPTS.get(req.conceptId, CONCEPTS["sets-types"])["skill"],
            feedback="This is a deterministic sample assessment. Review the lesson and practice to strengthen the skill.")
    return await evaluate_diagnostic(req)

@router.post("/lesson/generate", response_model=LessonResponse)
async def lesson_generate(req: LessonGenerateRequest, demo: bool = False):
    if demo:
        return LessonResponse(lesson=LESSONS.get(req.conceptId, LESSONS["sets-types"]), language=req.language)
    return await lesson(req)

@router.post("/quiz/generate", response_model=QuizGenerateResponse)
async def quiz_generate(req: QuizGenerateRequest, demo: bool = False):
    if demo:
        bank = QUIZ_BANK.get(req.conceptId, QUIZ_BANK["sets-types"])
        available = [q for q in bank if f"demo-{q['questionId']}" not in req.previousQuestionIds]
        chosen = (available or bank)[0]
        return QuizGenerateResponse(question=QuizQuestion.model_validate({**chosen, "questionId": f"demo-{chosen['questionId']}"}))
    try:
        return await quiz(req)
    except TopicContentUnavailable as exc:
        raise HTTPException(503, detail=str(exc)) from exc

@router.post("/quiz/evaluate", response_model=QuizEvaluateResponse)
async def quiz_evaluate(req: QuizEvaluateRequest, demo: bool = False):
    if demo:
        bank = QUIZ_BANK.get(req.conceptId, QUIZ_BANK["sets-types"])
        question = next((q for q in bank if f"demo-{q['questionId']}" == req.questionId), None)
        if not question:
            raise HTTPException(400, "Unknown demo quiz question")
        correct = req.answer.strip().casefold() == question["correctAnswer"].strip().casefold()
        return QuizEvaluateResponse(correct=correct, mastery=75 if correct else 35,
            explanation=question["explanation"], confirmed=False, provisional=True)
    try:
        return await evaluate_quiz(req)
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc)) from exc
