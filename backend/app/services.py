from __future__ import annotations
from typing import Any
import asyncio
import json
import re
import time
from .openrouter import client
from .demo_data import demo_analysis, QUIZ_BANK, LESSONS, CONCEPTS
from .schemas import *
from .parsing import normalize_question, unit_interval
from .persistence import persistence
from .notes import search_notes, misconception_prompt, infer_misconception, get_misconception
from .config import RAG_ENABLED, DEMO_TIME_TRAVEL, WORK_ANALYSIS_TIMEOUT_SECONDS
from .mastery import iso

class TopicContentUnavailable(RuntimeError):
    """No trustworthy offline content is available for the requested topic."""

WORK_SYSTEM = """You are LearnLens work-analysis AI. Analyze the ENTIRE supplied school worksheet/test as uncertain evidence, not as perfect grading.

HANDWRITTEN/PHOTO RULES:
- The submitted pages may be photographed handwritten work. Read pen/pencil strokes, crossings-out, underlines, circled marks, ticks and teacher annotations as visual evidence.
- Use the rendered image pages as the source of truth for handwriting and visual marks; the text layer may be incomplete.
- Mentally zoom into each question area before extracting. Preserve fractions, exponents, minus signs, decimal points, brackets and units carefully.
- If a handwritten symbol is ambiguous, do not guess: preserve uncertainty and set needsHumanReview=true.

Return JSON only. Keys: subject, topic, totalMarks, marksPossible, scorePercent, questions, possibleLearningGaps, overallConfidence, source.

Also infer the broad school subject and primary topic from the visible work when it is reasonably clear. Use empty strings rather than guessing when it is not clear.

Coverage rules:
- Identify every visible numbered question you can read. Do not skip later questions just because earlier questions were easy.
- Preserve each question number and the actual question text.
- Extract the student's answer/working, marks awarded, marks possible, teacher feedback/markings and the concept/skill being tested when supported by the work.
- Use multiple questions to identify repeated concepts and error patterns.
- possibleLearningGaps should list concept names that appear weak based on repeated evidence, not generic study advice.

Each question MUST include: questionId, questionNumber, questionText, studentAnswer, correctAnswer, marksAwarded, marksPossible, marksSource, gradingConfidence, teacherFeedback, conceptId, conceptName, skill, errorType, extractionConfidence, diagnosisConfidence, needsHumanReview, misconceptionTag. Select misconceptionTag from the supplied misconception library or "other". Tag only if supported by an incorrect response; use "other" for correct or uncertain answers.

ANSWER AND MARKING RULES:
- correctAnswer is your best solution/answer to the visible question, not the student's answer.
- marksAwarded should reflect visible teacher marks when present. If teacher marks are absent, estimate only when the question and marking basis are sufficiently clear, set marksSource="estimated", and give gradingConfidence. Otherwise use marksSource="unknown" and 0 for marksAwarded.
- Never present an estimate as a teacher-awarded mark.
errorType MUST be one of none, conceptual, procedural, arithmetic, sign_error, misreading, incomplete_reasoning, careless, unknown. diagnosisConfidence MUST be a number. Use unknown/0 when uncertain.
Never invent unreadable handwriting, marks, teacher comments, or student answers. Do not infer a genuine concept weakness from one isolated mistake. If handwriting or marks are unclear, flag needsHumanReview=true."""

DIAG_SYSTEM = """You are the diagnosis component of LearnLens. Given extracted school-work evidence and concept hints, identify ONE likely concept-level weakness. Treat this as a hypothesis, not certainty. Aggregate repeated evidence. Distinguish conceptual misunderstanding from procedural, arithmetic, sign, misreading, incomplete-reasoning and careless errors. Return JSON only with weakestConceptId, weakestConceptName, confidence, evidence, diagnosis, recommendation. Do not invent evidence."""

DIAG_Q_SYSTEM = """You are LearnLens's adaptive diagnostic-question generator.

The student provides an EXACT subject and topic. Treat those two strings as the requested learning target. Do not silently substitute a broader subject or a related topic.

Return JSON only: {\"questions\":[...]}.
Each question MUST contain questionId, conceptId, conceptName, question, exactly four options, correctAnswer, difficulty (1-4), and skill.

TOPIC MODE:
- Create a real academic diagnostic about the requested subject/topic, not a question about how to study.
- Cover distinct dimensions such as definition/representation, direct application, common misconception, and transfer/application.
- Use terminology, calculations, examples, or scenarios that genuinely belong to the requested topic.
- Do not ask generic questions such as “what is the best way to learn this topic?” or “how do you know you understand?”.
- Do not invent fake prerequisite facts merely to sound specific.

WORK MODE:
- Use extracted question text, student answers, marks, error type, skill and concept as evidence.
- Test the same underlying skills with new values/scenarios; never copy or lightly rewrite the original questions.
- Distractors should represent plausible misunderstandings visible in the work.

GLOBAL:
- Start easier and progress toward moderate difficulty.
- One clearly correct answer must be present in options.
- Options must be distinct and plausible.
- Every questionId is unique in the response.
- Return valid JSON only."""

DIAG_EVAL_SYSTEM = """You are a careful educational diagnostic reviewer.
Given a short diagnostic, the student's selected answers, the correct answers, and each question's skill, infer the most likely misconception or skill gap.

Rules:
- Treat the inference as a hypothesis, not certainty.
- Use repeated wrong-answer patterns when available.
- Do not call a single arithmetic/sign/careless slip a conceptual weakness.
- Prefer a specific skill-level explanation over a generic statement.
- Return JSON only with: likelyMisconception, likelySkill, confidence, feedback.
- If evidence is insufficient, say so explicitly in likelyMisconception."""

LESSON_SYSTEM = """You are LearnLens lesson-writing AI. Write a short personalized micro-lesson using the exact subject, topic, verified skill/misconception and supplied evidence. Return JSON: {\"lesson\":\"...\",\"sourceIds\":[...]}. Explain the likely misunderstanding, one worked example and one remember-this rule. Never invent unsupported facts. Only use a sourceId if a supplied source is explicitly provided; otherwise return an empty sourceIds array and write a clearly labeled general explanation."""

QUIZ_SYSTEM = """You are LearnLens adaptive-practice AI.
Generate ONE genuinely new academic practice question for the EXACT subject/topic/concept.
The question must target the supplied skill or misconception when present, respect mastery and previousQuestionIds, and be objectively scorable.
Return JSON only: {\"question\":{questionId,conceptId,conceptName,question,options,correctAnswer,difficulty,explanation}}.
Use exactly four options. Do not copy previous questions. Do not turn the question into generic study advice."""

SOURCE_NOTES = {
    "sets-types": "A set may be empty, finite, or infinite. Empty means no elements; finite means a list with a finite number of elements; infinite means the elements do not run out. Disjoint sets have no common elements.",
    "sets-builder": "Set-builder notation describes members by a condition, such as {x in Z : x²=9}. Every member must satisfy the condition. Interval parentheses exclude endpoints; square brackets include them.",
    "sets-operations": "A−B keeps members in A that are not in B. A∪B contains elements in either set. For finite sets, n(A∪B)=n(A)+n(B)−n(A∩B).",
}


_LESSON_STOPWORDS = {"the", "and", "for", "with", "of", "to", "in", "on", "a", "an", "is", "are", "s", "how", "what", "basic", "basics", "introduction", "general"}


def _relevant_notes(notes: list[dict[str, Any]], *labels: str) -> list[dict[str, Any]]:
    """Keep only notes whose title/topic shares a meaningful word with the requested topic.

    Keyword retrieval returns *something* for almost any query (for example every
    Mathematics note matches the word "Mathematics"); showing those as lesson sources is misleading.
    """
    terms = {t for label in labels for t in re.findall(r"[a-z0-9]+", str(label).lower()) if len(t) > 2 and t not in _LESSON_STOPWORDS}
    if not terms:
        return notes
    return [n for n in notes if terms & set(re.findall(r"[a-z0-9]+", f"{n.get('title', '')} {n.get('topic', '')}".lower()))]


def _difficulty(value: Any) -> int:
    try:
        return min(4, max(1, int(float(value))))
    except (TypeError, ValueError):
        return 2


def slugify(text: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return value[:64] or "topic"


def _validated_questions(raw: dict[str, Any]) -> list[dict[str, Any]]:
    return [normalize_question(q, i) for i, q in enumerate(raw.get("questions") or [], 1)]

def _visible_question_count(text: str) -> int:
    if not text.strip():
        return 0
    hits = re.findall(r"(?m)^\s*(?:Q\s*)?(\d{1,2})\s*[\).:-]\s+", text)
    nums = {int(x) for x in hits if 1 <= int(x) <= 50}
    return len(nums)


def _topic_label(req: DiagnosticGenerateRequest) -> str:
    return req.topic.strip() or req.conceptName.split(":", 1)[-1].strip() or req.conceptName


def _fallback_topic_diagnostic(req: DiagnosticGenerateRequest) -> list[DiagnosticQuestion]:
    """Emergency offline questions for prepared demo topics only.

    For arbitrary topics we refuse to invent academic facts. Previously generated
    topic questions can still be reused by the persistence layer before this function is called.
    """
    subject = (req.subject or req.conceptName.split(":", 1)[0]).strip()
    topic = _topic_label(req)
    key = f"{subject} {topic}".lower()
    cid = req.conceptId

    packs: list[tuple[str, list[str], str, str]] = []
    if "math" in key and "set" in key:
        packs = [
            ("Which of these is a finite set?", ["{2, 4, 6, 8}", "{1, 2, 3, ...}", "All real numbers", "All points on a line"], "{2, 4, 6, 8}", "Classify finite and infinite sets"),
            ("If A = {1, 2, 3} and B = {3, 4}, which is A ∪ B?", ["{1, 2, 3, 4}", "{3}", "{1, 2}", "{4}"], "{1, 2, 3, 4}", "Apply set union"),
            ("For a finite set A, what does n(A) represent?", ["The number of elements in A", "The largest element of A", "The sum of all elements of A", "The number of subsets of A"], "The number of elements in A", "Interpret cardinality"),
            ("Which statement is true for two disjoint sets A and B?", ["A ∩ B = ∅", "A ∪ B = ∅", "A = B", "Both must be infinite"], "A ∩ B = ∅", "Recognize disjoint sets"),
        ]
    elif "math" in key and "quadratic" in key:
        packs = [
            ("For x² - 5x + 6 = 0, what are the roots?", ["2 and 3", "-2 and -3", "1 and 6", "-1 and -6"], "2 and 3", "Solve a quadratic by factorisation"),
            ("For ax²+bx+c=0, which expression is the discriminant?", ["b² - 4ac", "b² + 4ac", "4ac - b", "a² - 4bc"], "b² - 4ac", "Use the discriminant"),
            ("If the discriminant of a quadratic is zero, how many distinct real roots does it have?", ["One", "Two", "None", "Infinitely many"], "One", "Interpret discriminant cases"),
            ("Which method is most direct when x²+7x+12=0 factors over the integers?", ["Factorisation", "Numerical integration", "Differentiation only", "Matrix inversion"], "Factorisation", "Choose a suitable solution method"),
        ]
    elif "math" in key and "integration" in key:
        packs = [
            ("What is an antiderivative of 2x?", ["x² + C", "2x² + C", "x + C", "ln|x| + C"], "x² + C", "Find a basic antiderivative"),
            ("Which rule is used directly for ∫ x^n dx when n ≠ -1?", ["Power rule", "Product rule", "Quotient rule", "Chain rule only"], "Power rule", "Select the power rule"),
            ("What should be added to an indefinite integral?", ["A constant of integration C", "A second derivative", "A logarithm in every case", "Nothing"], "A constant of integration C", "Handle indefinite integrals"),
            ("Which change of variable is most natural for ∫2x(x²+1)^5 dx?", ["u = x²+1", "u = x", "u = 2x", "u = 5x"], "u = x²+1", "Recognize substitution"),
        ]
    elif "physics" in key and "newton" in key:
        packs = [
            ("Which statement matches Newton's first law when the net external force is zero?", ["An object keeps its state of motion", "An object must accelerate", "The object's mass becomes zero", "Gravity stops existing"], "An object keeps its state of motion", "Interpret inertia and net force"),
            ("If the net force on a 2 kg object is 10 N, what is its acceleration?", ["5 m/s²", "20 m/s²", "8 m/s²", "0.2 m/s²"], "5 m/s²", "Apply F = ma"),
            ("For every force exerted by one object on another, what does Newton's third law provide?", ["An equal and opposite force on the first object", "A larger force on the first object", "No force in return", "A force only if the objects have equal mass"], "An equal and opposite force on the first object", "Identify action-reaction pairs"),
            ("A constant net force acts on an object. Which quantity changes as a result?", ["Its velocity", "Its mass", "Its identity", "Its units"], "Its velocity", "Connect force and acceleration"),
        ]
    elif "physics" in key and ("projectile" in key or "motion" in key):
        packs = [
            ("Ignoring air resistance, which acceleration acts on a projectile near Earth's surface?", ["Downward gravitational acceleration", "Upward constant acceleration", "Zero acceleration in both directions", "Acceleration toward the launch point"], "Downward gravitational acceleration", "Resolve projectile acceleration"),
            ("At the highest point of an ideal projectile's path, what is its vertical velocity?", ["Zero", "Maximum", "Equal to horizontal velocity", "Negative maximum"], "Zero", "Interpret vertical velocity"),
            ("In ideal projectile motion, which component of velocity remains constant?", ["Horizontal component", "Vertical component", "Both components", "Neither component"], "Horizontal component", "Separate horizontal and vertical motion"),
            ("Increasing the launch speed while keeping the angle fixed generally increases the range when air resistance is ignored. What is the main reason?", ["The projectile stays in motion longer and travels faster horizontally", "Gravity becomes weaker", "Mass increases", "The angle automatically changes"], "The projectile stays in motion longer and travels faster horizontally", "Connect velocity to range"),
        ]
    elif "computer" in key and ("recursion" in key or "algorithm" in key):
        packs = [
            ("What essential component prevents a recursive function from calling itself forever?", ["A base case", "A global variable", "A second function", "A print statement"], "A base case", "Recognize the base case"),
            ("In recursion, what happens when the base case is reached?", ["The recursive calls stop", "The function must call itself again", "The stack doubles automatically", "The input becomes random"], "The recursive calls stop", "Trace a recursive process"),
            ("Which structure is most directly involved in tracking nested recursive calls?", ["The call stack", "A queue only", "A hash table only", "A network socket"], "The call stack", "Understand recursive state"),
            ("A recursive solution reduces the input from n to n-1 each call. What should you check first for correctness?", ["That the base case is reachable", "That the function has no parameters", "That every call increases n", "That all variables are global"], "That the base case is reachable", "Reason about termination"),
        ]

    if not packs:
        raise TopicContentUnavailable(
            f'Live AI is unavailable and LearnLens has no trusted offline content for “{subject} → {topic}” yet. '
            'Try again while live AI is available.'
        )

    return [
        DiagnosticQuestion(
            questionId=f"fallback-topic-{slugify(subject)}-{slugify(topic)}-{i+1}",
            conceptId=cid,
            conceptName=topic,
            question=q,
            options=opts,
            correctAnswer=ans,
            difficulty=min(i + 1, 4),
            skill=skill,
        ) for i, (q, opts, ans, skill) in enumerate(packs[:req.count])
    ]


def _fallback_quiz(req: QuizGenerateRequest) -> QuizQuestion:
    subject = (req.subject or req.conceptName.split(":", 1)[0]).strip()
    topic = (req.topic or req.conceptName.split(":", 1)[-1]).strip()
    key = f"{subject} {topic}".lower()

    packs: list[tuple[str, list[str], str, str]] = []
    if "math" in key and "set" in key:
        packs = [
            ("If A = {1, 2, 3} and B = {2, 3, 4}, how many elements are in A ∩ B?", ["2", "1", "3", "4"], "2", "Find an intersection"),
            ("Which interval includes both endpoints 1 and 4?", ["[1,4]", "(1,4)", "[1,4)", "(1,4]"], "[1,4]", "Interpret interval notation"),
            ("If A = {a, b} and B = {b, c}, what is A − B?", ["{a}", "{b}", "{c}", "{a,b,c}"], "{a}", "Apply set difference"),
            ("How many subsets does a two-element set have?", ["4", "2", "3", "6"], "4", "Count subsets"),
            ("Which pair of sets is disjoint?", ["{1,2} and {3,4}", "{1,2} and {2,3}", "{a,b} and {b,c}", "{0,1} and {1,2}"], "{1,2} and {3,4}", "Identify disjoint sets"),
            ("If n(A)=5 and n(B)=4 with n(A ∩ B)=2, what is n(A ∪ B)?", ["7", "9", "6", "3"], "7", "Use the union-cardinality rule"),
        ]
    elif "math" in key and "quadratic" in key:
        packs = [
            ("What is the discriminant of x² + 6x + 5 = 0?", ["16", "36", "56", "-16"], "16", "Calculate the discriminant"),
            ("What are the roots of x² - 9 = 0?", ["3 and -3", "9 and -9", "0 and 9", "3 and 3"], "3 and -3", "Solve by factoring a difference of squares"),
            ("Which quadratic has two equal real roots?", ["x² + 2x + 1 = 0", "x² + 1 = 0", "x² - 4 = 0", "x² + 3 = 0"], "x² + 2x + 1 = 0", "Recognize a repeated root"),
            ("For x² - 7x + 10 = 0, which factor pair gives the roots?", ["5 and 2", "7 and 10", "-5 and -2", "1 and 10"], "5 and 2", "Connect factors to roots"),
            ("If b² - 4ac is negative for a real quadratic equation, how many real roots does it have?", ["None", "One", "Two", "Infinitely many"], "None", "Interpret a negative discriminant"),
            ("Which method is efficient for 2x² + 7x + 3 = 0 when it factors over the integers?", ["Factorisation", "Integration", "Differentiation", "Trigonometric substitution"], "Factorisation", "Choose a suitable solution method"),
        ]
    elif "math" in key and "integration" in key:
        packs = [
            ("What is ∫ 3x² dx?", ["x³ + C", "3x³ + C", "x² + C", "6x + C"], "x³ + C", "Apply the power rule"),
            ("What is d/dx (x⁴/4)?", ["x³", "4x³", "x⁴", "x²"], "x³", "Connect derivatives and antiderivatives"),
            ("Which substitution simplifies ∫ 6x(x²+2)^4 dx?", ["u=x²+2", "u=6x", "u=x²", "u=4x"], "u=x²+2", "Choose a useful substitution"),
            ("What is ∫ 1/x dx?", ["ln|x| + C", "x⁻¹ + C", "1/x² + C", "eˣ + C"], "ln|x| + C", "Recognize the logarithmic antiderivative"),
            ("What is ∫₀¹ 2x dx?", ["1", "2", "0", "1/2"], "1", "Evaluate a definite integral"),
            ("Why is +C included in an indefinite integral?", ["Different antiderivatives can differ by a constant", "Every integral must contain a variable", "C is the area under the graph", "C changes the derivative"], "Different antiderivatives can differ by a constant", "Interpret the constant of integration"),
        ]
    elif "physics" in key and "newton" in key:
        packs = [
            ("Which statement matches Newton's first law when the net external force is zero?", ["An object keeps its state of motion", "An object must accelerate", "The object's mass becomes zero", "Gravity stops existing"], "An object keeps its state of motion", "Interpret inertia and net force"),
            ("If the net force on a 2 kg object is 10 N, what is its acceleration?", ["5 m/s²", "20 m/s²", "8 m/s²", "0.2 m/s²"], "5 m/s²", "Apply F = ma"),
            ("For every force exerted by one object on another, what does Newton's third law provide?", ["An equal and opposite force on the first object", "A larger force on the first object", "No force in return", "A force only if the objects have equal mass"], "An equal and opposite force on the first object", "Identify action-reaction pairs"),
            ("A constant net force acts on an object. Which quantity changes as a result?", ["Its velocity", "Its mass", "Its identity", "Its units"], "Its velocity", "Connect force and acceleration"),
        ]
    elif "physics" in key and ("projectile" in key or "motion" in key):
        packs = [
            ("For ideal projectile motion, which velocity component changes because of gravity?", ["Vertical", "Horizontal", "Neither", "Both remain constant"], "Vertical", "Separate velocity components"),
            ("A projectile is launched horizontally. What is its initial vertical velocity?", ["0", "Equal to its horizontal velocity", "g", "Maximum possible"], "0", "Interpret initial component velocity"),
            ("If air resistance is ignored, what is the horizontal acceleration of a projectile?", ["0", "g", "2g", "It depends on mass"], "0", "Identify horizontal acceleration"),
            ("At the top of a projectile's path, which statement is correct?", ["Vertical velocity is zero while acceleration is downward", "Both velocity and acceleration are zero", "Acceleration is upward", "Horizontal velocity is zero"], "Vertical velocity is zero while acceleration is downward", "Distinguish velocity from acceleration"),
            ("Two projectiles have the same launch speed and complementary launch angles. Under ideal conditions, what is true of their ranges?", ["They are equal", "The first is always double the second", "They are both zero", "Range depends only on mass"], "They are equal", "Reason about launch angle"),
            ("Which motion can be analyzed independently of the other in ideal projectile motion?", ["Horizontal and vertical components", "Mass and time", "Gravity and mass", "Energy and charge"], "Horizontal and vertical components", "Use component analysis"),
        ]
    elif "computer" in key and "recursion" in key:
        packs = [
            ("What is the base case in a recursive function?", ["The stopping condition", "The largest input", "The first loop", "A global variable"], "The stopping condition", "Identify a base case"),
            ("If f(n) calls f(n-1) until n=0, what happens at n=0?", ["Recursion stops", "n becomes negative first", "The function doubles", "The call stack is reset by magic"], "Recursion stops", "Trace termination"),
            ("Which data structure naturally records active recursive calls?", ["Call stack", "Queue", "Heap only", "Graph"], "Call stack", "Understand stack frames"),
            ("Why can naive Fibonacci recursion be slow?", ["It recomputes the same subproblems", "It never uses arithmetic", "It always sorts the input", "It cannot return values"], "It recomputes the same subproblems", "Recognize repeated work"),
            ("What must decrease or otherwise move toward a base case for recursion to terminate?", ["The problem size/state", "The number of variables in the program", "The screen resolution", "The number of comments"], "The problem size/state", "Reason about termination"),
            ("Which strategy can improve repeated recursive subproblems?", ["Memoization", "Adding more recursive calls", "Removing the base case", "Using random values"], "Memoization", "Recognize memoization"),
        ]
    else:
        packs = []
    if not packs:
        raise TopicContentUnavailable(
            f'Live AI is unavailable and LearnLens has no trusted offline practice content for “{subject} → {topic}” yet. Try again while live AI is available.'
        )
    start = len(req.previousQuestionIds) % len(packs)
    for offset in range(len(packs)):
        candidate = packs[(start + offset) % len(packs)]
        stable_id = f"fallback-practice-{slugify(req.conceptId)}-{packs.index(candidate)+1}"
        if stable_id not in req.previousQuestionIds:
            q, opts, ans, skill = candidate
            return QuizQuestion(questionId=stable_id, conceptId=req.conceptId, conceptName=topic, question=q, options=opts, correctAnswer=ans, difficulty=2 if req.mastery < 70 else 3, explanation=f"This practice question checks: {skill}.")
    q, opts, ans, skill = packs[0]
    return QuizQuestion(questionId=f"fallback-practice-{slugify(req.conceptId)}-fresh", conceptId=req.conceptId, conceptName=topic, question=q, options=opts, correctAnswer=ans, difficulty=3, explanation=f"This practice question checks: {skill}.")


async def persist_work_analysis_bounded(student_id: str, analysis: dict[str, Any], filename: str = "uploaded-work", file_type: str = "", timeout_seconds: float = 6.0) -> None:
    """Keep slow/broken best-effort persistence from consuming the whole serverless budget."""
    started = time.perf_counter()
    try:
        await asyncio.wait_for(
            persistence.save_work_analysis(student_id, analysis, filename=filename, file_type=file_type),
            timeout=max(0.1, timeout_seconds),
        )
        print(f"WORK_PERSIST_END elapsed_ms={(time.perf_counter()-started)*1000:.1f}", flush=True)
    except asyncio.TimeoutError:
        print(f"WORK_PERSIST_TIMEOUT elapsed_ms={(time.perf_counter()-started)*1000:.1f}", flush=True)
    except Exception as exc:
        # Learning analysis should remain available even if optional persistence is degraded.
        print(f"WORK_PERSIST_ERROR elapsed_ms={(time.perf_counter()-started)*1000:.1f} error_type={type(exc).__name__}", flush=True)


async def analyze_work(text: str, images: list[tuple[str, bytes]], student_id: str = "demo-student", allow_demo_fallback: bool = False, filename: str = "uploaded-work", file_type: str = ""):
    if not text.strip() and not images:
        result = WorkAnalysis.model_validate(demo_analysis())
        result.provider = "Bundled sample"
        result.fromCache = False
        return result
    prompt = "Analyze the supplied school work. Concept hints: " + json.dumps(CONCEPTS, ensure_ascii=False) + "\nMisconception library (choose an ID only when evidence supports it): " + json.dumps(misconception_prompt(), ensure_ascii=False) + "\nVisible text layer: " + text[:18000]
    # All provider attempts, including a coverage-repair attempt, share one deadline.
    # Provider fallback must not add 25 seconds per provider *and* per repair pass.
    analysis_deadline = time.perf_counter() + WORK_ANALYSIS_TIMEOUT_SECONDS
    try:
        validation_started = time.perf_counter()
        print("VALIDATION_START pass=initial", flush=True)
        remaining = analysis_deadline - time.perf_counter()
        if remaining <= 0:
            raise TimeoutError("analysis time budget exhausted before provider call")
        raw = await asyncio.wait_for(client.complete_json(WORK_SYSTEM, prompt, images), timeout=remaining)
        provider = str(raw.pop("_learnlens_provider", "unknown"))
        raw["questions"] = _validated_questions(raw)
        for question in raw["questions"]:
            if question.get("errorType") == "none":
                question["misconceptionTag"] = "other"
            else:
                question["misconceptionTag"] = infer_misconception(question)
        visible_count = _visible_question_count(text)
        print(f"VALIDATION_END pass=initial elapsed_ms={(time.perf_counter()-validation_started)*1000:.1f} questions={len(raw['questions'])} visible_questions={visible_count}", flush=True)
        # A text layer that clearly contains more numbered questions than the model returned
        # is a strong signal that coverage is incomplete. Give the model one repair pass.
        if images and len(raw["questions"]) < 1:
            raise ValueError("no readable questions returned")
        if visible_count >= 4 and len(raw["questions"]) < max(1, int(visible_count * 0.65)):
            repair_prompt = prompt + f"\nCOVERAGE REPAIR: the visible text suggests at least {visible_count} numbered questions. Re-scan every supplied page and return all readable questions, not only the first few."
            repair_started = time.perf_counter()
            remaining = analysis_deadline - time.perf_counter()
            if remaining < 6.0:
                print(f"REPAIR_SCAN_SKIPPED reason=insufficient_budget remaining_ms={max(0, remaining)*1000:.1f}", flush=True)
                raise TimeoutError("Not enough time remained to verify question coverage. Please retry with fewer pages or a smaller file.")
            print(f"REPAIR_SCAN_START visible_questions={visible_count} initial_questions={len(raw['questions'])} budget_ms={remaining*1000:.1f}", flush=True)
            raw = await asyncio.wait_for(client.complete_json(WORK_SYSTEM, repair_prompt, images), timeout=remaining)
            provider = str(raw.pop("_learnlens_provider", provider))
            raw["questions"] = _validated_questions(raw)
            for question in raw["questions"]:
                question["misconceptionTag"] = "other" if question.get("errorType") == "none" else infer_misconception(question)
            print(f"REPAIR_SCAN_END elapsed_ms={(time.perf_counter()-repair_started)*1000:.1f} questions={len(raw['questions'])}", flush=True)
            if len(raw["questions"]) < max(1, int(visible_count * 0.65)):
                raise ValueError("coverage remains incomplete after repair pass")
        total = sum(q["marksAwarded"] for q in raw["questions"])
        poss = sum(q["marksPossible"] for q in raw["questions"])
        raw["totalMarks"] = float(total)
        raw["marksPossible"] = float(poss)
        raw["scorePercent"] = min(100.0, max(0.0, round((total / poss) * 100, 1))) if poss else 0
        raw["possibleLearningGaps"] = raw.get("possibleLearningGaps") or []
        raw["overallConfidence"] = unit_interval(raw.get("overallConfidence"))
        raw["source"] = "ai"
        raw["provider"] = provider
        raw["fromCache"] = False
        model_validation_started = time.perf_counter()
        result = WorkAnalysis.model_validate(raw)
        print(f"STRUCTURED_VALIDATION_END elapsed_ms={(time.perf_counter()-model_validation_started)*1000:.1f} questions={len(result.questions)}", flush=True)
        await persist_work_analysis_bounded(student_id, result.model_dump(), filename=filename, file_type=file_type)
        return result
    except Exception as exc:
        if isinstance(exc, TimeoutError):
            message = f"Work analysis exceeded its {WORK_ANALYSIS_TIMEOUT_SECONDS:g}-second AI processing budget. Please retry or upload fewer pages."
        else:
            message = str(exc) or type(exc).__name__
        print(f"WORK_ANALYSIS_FAILED elapsed_ms={(time.perf_counter()-(analysis_deadline-WORK_ANALYSIS_TIMEOUT_SECONDS))*1000:.1f} error_type={type(exc).__name__}", flush=True)
        if allow_demo_fallback:
            sample_payload = demo_analysis()
            for question in sample_payload.get("questions", []):
                question["misconceptionTag"] = "other" if question.get("errorType") == "none" else infer_misconception(question)
            sample_payload["provider"] = "Bundled sample"
            sample_payload["fromCache"] = False
            result = WorkAnalysis.model_validate(sample_payload)
            await persist_work_analysis_bounded(student_id, result.model_dump(), filename=filename, file_type=file_type)
            return result
        raise RuntimeError(f"Work analysis could not be completed safely: {message}") from exc


async def diagnose(req: DiagnosisRequest) -> DiagnosisResponse:
    evidence = [
        f"Q{q.questionNumber}: {q.conceptName} — {q.teacherFeedback or q.errorType}"
        for q in req.extractedQuestions
        if q.errorType != "none" or q.marksAwarded < q.marksPossible
    ] or ["No strong negative evidence was extracted."]
    try:
        prompt = "Extracted evidence:\n" + json.dumps([q.model_dump() for q in req.extractedQuestions]) + "\nConcept taxonomy:\n" + json.dumps(CONCEPTS) + "\nMisconception library:\n" + json.dumps(misconception_prompt()) + "\nReturn misconceptionTag from this list or other."
        raw = await client.complete_json(DIAG_SYSTEM, prompt)
        raw["confidence"] = unit_interval(raw.get("confidence"))
        resp = DiagnosisResponse.model_validate(raw)
    except Exception:
        counts: dict[str, int] = {}
        names: dict[str, str] = {}
        for q in req.extractedQuestions:
            if q.errorType in {"conceptual", "procedural", "incomplete_reasoning"} or q.marksAwarded < q.marksPossible:
                counts[q.conceptId] = counts.get(q.conceptId, 0) + 1
                names[q.conceptId] = q.conceptName
        if counts:
            cid = max(counts, key=counts.get)
            name = names.get(cid, "Possible learning gap")
            conf = min(0.95, 0.55 + 0.12 * counts[cid])
        else:
            cid = req.extractedQuestions[0].conceptId if req.extractedQuestions else "unknown-topic"
            name = req.extractedQuestions[0].conceptName if req.extractedQuestions else "Possible learning gap"
            conf = 0.4
        resp = DiagnosisResponse(weakestConceptId=cid, weakestConceptName=name, confidence=conf, evidence=evidence[:5], diagnosis=f"The strongest repeated signal is difficulty with {name}.", recommendation=f"Verify {name} with targeted questions before teaching it.")
    await persistence.save_diagnosis(req.studentId, resp.model_dump(), resp.weakestConceptName, req.subject, req.topic)
    return resp


async def generate_diagnostic(req: DiagnosticGenerateRequest) -> DiagnosticGenerateResponse:
    source_payload = [{
        "questionNumber": q.get("questionNumber"), "questionText": q.get("questionText"), "studentAnswer": q.get("studentAnswer"),
        "marksAwarded": q.get("marksAwarded"), "marksPossible": q.get("marksPossible"), "conceptId": q.get("conceptId"),
        "conceptName": q.get("conceptName"), "skill": q.get("skill"), "errorType": q.get("errorType"), "teacherFeedback": q.get("teacherFeedback"),
    } for q in req.sourceQuestions[:20]]

    topic = req.topic.strip() or req.conceptName.split(":", 1)[-1].strip()
    subject = req.subject.strip() or (req.conceptName.split(":", 1)[0].strip() if ":" in req.conceptName else "")
    prompt_parts = [
        f"Mode: {req.mode}",
        f"EXACT SUBJECT: {subject}",
        f"EXACT TOPIC: {topic}",
        f"Concept ID: {req.conceptId}",
        f"Generate exactly {req.count} fresh questions.",
    ]
    if req.sourceTopics:
        prompt_parts.append("Topics/concepts present in submitted work: " + json.dumps(req.sourceTopics, ensure_ascii=False))
    if req.mode == 'work':
        if source_payload:
            prompt_parts.append("Extracted student work evidence:\n" + json.dumps(source_payload, ensure_ascii=False))
        prompt_parts.append("WORK MODE: target the student's actual mistakes and use new numbers/scenarios. Never copy the original question.")
    else:
        if source_payload:
            prompt_parts.append("TOPIC MODE evidence: use the student's diagnostic responses as evidence about the exact requested topic, but create new academic questions that probe the same underlying skills.")
            prompt_parts.append("Diagnostic response evidence:\n" + json.dumps(source_payload, ensure_ascii=False))
        else:
            prompt_parts.append("TOPIC MODE: produce real academic questions about the exact requested topic. Never use generic study-advice questions.")

    async def call_once(extra: str = ""):
        raw = await client.complete_json(DIAG_Q_SYSTEM, "\n".join(prompt_parts) + ("\n" + extra if extra else ""))
        qs = []
        for item in (raw.get("questions") or []):
            if isinstance(item, dict):
                # Models often change the concept id, omit its name or return an out-of-range difficulty.
                item = {**item, "conceptId": req.conceptId, "conceptName": item.get("conceptName") or topic, "difficulty": _difficulty(item.get("difficulty"))}
            qs.append(DiagnosticQuestion.model_validate(item))
        if len(qs) != req.count:
            raise ValueError(f"expected {req.count} questions, got {len(qs)}")
        ids = [q.questionId for q in qs]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate question IDs")
        forbidden = ("best way to learn", "how do you know you understand", "study this topic", "memorize one example")
        for q in qs:
            if q.conceptId != req.conceptId or q.correctAnswer not in q.options or len({x.strip().lower() for x in q.options}) != 4:
                raise ValueError("invalid diagnostic question")
            if any(p in q.question.lower() for p in forbidden):
                raise ValueError("generic study-advice question rejected")
            if not q.skill.strip():
                raise ValueError("missing skill")
        return qs

    try:
        qs = await call_once()
    except Exception:
        try:
            qs = await call_once("REPAIR: regenerate all questions from scratch. Make every question academically specific to the exact subject/topic, with a concrete skill and plausible distractors. Do not use generic learning-advice wording.")
        except Exception:
            cached = await persistence.get_cached_questions(req.studentId, req.conceptId, mode=req.mode)
            if len(cached) >= req.count:
                qs = [DiagnosticQuestion(
                    questionId=str(row["question_id"]),
                    conceptId=req.conceptId,
                    conceptName=topic,
                    question=str(row.get("question_text") or ""),
                    options=list(row.get("options") or []),
                    correctAnswer=str(row.get("correct_answer") or ""),
                    difficulty=max(1, min(4, int(row.get("difficulty") or 2))),
                    skill=str((row.get("source_context") or {}).get("skill") or ""),
                ) for row in cached[:req.count]]
            else:
                qs = _fallback_topic_diagnostic(req)

    await persistence.save_diagnostic_questions(req.studentId, req.conceptId, [q.model_dump() for q in qs], mode=req.mode, subject=subject, topic=topic)
    return DiagnosticGenerateResponse(questions=qs)


async def evaluate_diagnostic(req: DiagnosticEvaluateRequest) -> DiagnosticEvaluateResponse:
    question_map = await persistence.get_diagnostic_questions(req.studentId, req.conceptId)
    records = []
    for qid, answer in req.answers.items():
        q = question_map.get(qid)
        if not q:
            continue
        expected = str(q.get("correct_answer") or q.get("correctAnswer") or "")
        records.append({"questionId": qid, "question": q.get("question_text", ""), "options": q.get("options", []), "selectedAnswer": answer, "correctAnswer": expected, "skill": (q.get("source_context") or {}).get("skill", "")})
    correct = sum(1 for r in records if r["selectedAnswer"].strip().lower() == r["correctAnswer"].strip().lower())
    total = len(records) or len(req.answers)
    score = round((correct / total) * 100, 1) if total else 0

    likely = "Not enough evidence for a specific misconception."
    skill = ""
    confidence = 0.4
    feedback = "We need more evidence before calling this a confirmed gap."
    try:
        raw = await client.complete_json(DIAG_EVAL_SYSTEM, json.dumps(records, ensure_ascii=False))
        likely = str(raw.get("likelyMisconception") or likely)
        skill = str(raw.get("likelySkill") or "")
        confidence = max(0, min(1, float(raw.get("confidence") or 0.5)))
        feedback = str(raw.get("feedback") or feedback)
    except Exception:
        wrong = [r for r in records if r["selectedAnswer"].strip().lower() != r["correctAnswer"].strip().lower()]
        if wrong:
            skills = [r["skill"] for r in wrong if r["skill"]]
            skill = skills[0] if skills else "the tested skill"
            likely = f"The wrong responses suggest difficulty with {skill}. This is a hypothesis that should improve with targeted practice."
            confidence = min(0.9, 0.5 + 0.1 * min(4, len(wrong)))
            feedback = "The response pattern gives us a specific skill to check next."

    confirmed = score < 70 and bool(records)
    await persistence.save_diagnosis(req.studentId, {
        "weakestConceptId": req.conceptId,
        "weakestConceptName": next((r.get("conceptName") for r in records if r.get("conceptName")), req.conceptId),
        "confidence": confidence,
        "evidence": [f"{r['questionId']}: {r['selectedAnswer']}" for r in records],
        "diagnosis": likely,
        "recommendation": skill or "Continue with targeted practice.",
    }, concept_name=req.conceptId, subject="", topic="")
    return DiagnosticEvaluateResponse(correct=correct, total=total, scorePercent=score, confirmedWeakness=confirmed, confidence=confidence, feedback=feedback, likelyMisconception=likely, likelySkill=skill)


async def lesson(req: LessonGenerateRequest) -> LessonResponse:
    language_names = {"en": "English", "kn": "Kannada", "hi": "Hindi"}
    query = " ".join([req.subject, req.topic, req.conceptName, req.misconceptionTag, *req.evidence])
    notes = _relevant_notes(search_notes(query, limit=8), req.topic or req.conceptName, req.conceptName)[:4] if RAG_ENABLED else []
    legacy_note = SOURCE_NOTES.get(req.conceptId, "")
    if not notes and legacy_note:
        notes = [{"id": f"legacy-{slugify(req.conceptId)}", "title": req.conceptName, "content": legacy_note, "snippet": legacy_note[:240], "url": "", "attribution": "Bundled legacy teaching note", "license": "Project content"}]
    allowed_ids = {str(note["id"]) for note in notes}
    tag = get_misconception(req.misconceptionTag) or get_misconception("other") or {}
    lesson_system = LESSON_SYSTEM + "\nReturn JSON keys: lesson, sourceIds, glossary. sourceIds must be selected only from the allowed IDs. Keep technical English terms in parentheses when writing Kannada/Hindi. Prefer a short definition, one worked example, one remember-this rule, and a quick self-check. Do not claim a source says anything beyond the notes supplied."
    prompt = "\n".join([
        f"Subject: {req.subject or 'General'}",
        f"Topic: {req.topic or req.conceptName}",
        f"Concept/skill: {req.conceptName}",
        f"Likely misconception hypothesis: {tag.get('label', req.misconceptionTag)}",
        f"Observed evidence: {json.dumps(req.evidence, ensure_ascii=False)}",
        f"Requested explanation language: {language_names.get(req.language, 'English')} (code {req.language})",
        "Explain in the requested language. Preserve important English technical terms in brackets/parentheses.",
        "Allowed note IDs and content: " + json.dumps([{"id": n["id"], "title": n["title"], "content": n["content"]} for n in notes], ensure_ascii=False),
        "If no notes were supplied, clearly state this is a general explanation and return no source IDs.",
    ])
    try:
        raw = await client.complete_json(lesson_system, prompt)
        lesson_text = str(raw.get("lesson", "")).strip()
        cited = [str(value) for value in (raw.get("sourceIds") or []) if str(value) in allowed_ids]
        glossary = raw.get("glossary") if isinstance(raw.get("glossary"), list) else []
        if lesson_text and (cited or not notes):
            selected = [note for note in notes if note["id"] in cited]
            return LessonResponse(
                lesson=lesson_text,
                sourceIds=cited,
                sources=[{"id": n["id"], "title": n["title"], "url": n.get("url", ""), "snippet": n.get("snippet", n["content"][:240]), "attribution": n.get("attribution", "Bundled teaching note; provenance unspecified"), "license": n.get("license", "Review licensing before external reuse")} for n in selected],
                language=req.language,
                glossary=[g for g in glossary if isinstance(g, dict) and g.get("en") and g.get("local")][:8],
            )
    except Exception:
        pass
    # Reviewed deterministic fallback: the student still receives notes-grounded content without inventing citations.
    base_english = "\n\n".join(str(n["content"]) for n in notes[:3]) if notes else "No approved note matched this topic. Use a textbook or teacher-approved source before relying on this general explanation."
    bilingual = {
      "sets-types": {
        "kn": "ಸೆಟ್ ಎಂದರೆ ಸ್ಪಷ್ಟವಾಗಿ ನಿರ್ಧರಿಸಲಾದ ವಿಭಿನ್ನ ಅಂಶಗಳ ಸಂಗ್ರಹ. ಖಾಲಿ ಸೆಟ್‌ನಲ್ಲಿ ಯಾವುದೇ ಅಂಶಗಳಿರುವುದಿಲ್ಲ. ಸೀಮಿತ ಸೆಟ್‌ನ ಅಂಶಗಳನ್ನು ಎಣಿಸಿ ಮುಗಿಸಬಹುದು; ಅನಂತ ಸೆಟ್‌ನ ಅಂಶಗಳು ಮುಗಿಯುವುದಿಲ್ಲ. ಉದಾಹರಣೆ: 3 ಮತ್ತು 4ರ ನಡುವೆ ಇರುವ ಸ್ವಾಭಾವಿಕ ಸಂಖ್ಯೆಗಳ ಸೆಟ್ ಖಾಲಿಯಾಗಿದೆ, ಏಕೆಂದರೆ ಅವುಗಳ ಮಧ್ಯೆ ಸ್ವಾಭಾವಿಕ ಸಂಖ್ಯೆ ಇಲ್ಲ. ನೆನಪಿಡಿ: ಸೆಟ್‌ನ ಗಾತ್ರವನ್ನು ಊಹಿಸದೇ, ಷರತ್ತನ್ನು ಪೂರೈಸುವ ಅಂಶಗಳನ್ನು ಪರಿಶೀಲಿಸಿ.",
        "hi": "समुच्चय (set) अलग-अलग और स्पष्ट रूप से निर्धारित वस्तुओं का संग्रह है। रिक्त समुच्चय में कोई तत्व नहीं होता। सीमित समुच्चय के तत्वों को गिनकर समाप्त किया जा सकता है; अनंत समुच्चय के तत्व समाप्त नहीं होते। उदाहरण: 3 और 4 के बीच प्राकृतिक संख्याओं का समुच्चय रिक्त है, क्योंकि इनके बीच कोई प्राकृतिक संख्या नहीं है। याद रखें: आकार का अनुमान लगाने के बजाय, शर्त पूरी करने वाले तत्वों की जाँच करें।"},
      "sets-builder": {
        "kn": "Set-builder notation ಒಂದು ಸೆಟ್‌ನ ಅಂಶಗಳನ್ನು ಷರತ್ತಿನ ಮೂಲಕ ವಿವರಿಸುತ್ತದೆ. {x ∈ Z : x² = 9} ನಲ್ಲಿ x ಪೂರ್ಣಾಂಕವಾಗಿರಬೇಕು ಮತ್ತು ಅದರ ವರ್ಗ 9 ಆಗಿರಬೇಕು. ಆದ್ದರಿಂದ -3 ಮತ್ತು 3 ಎರಡೂ ಸರಿಯಾಗಿವೆ; ಸೆಟ್ {-3, 3}. ನೆನಪಿಡಿ: domain ಮತ್ತು condition ಎರಡನ್ನೂ ಪರೀಕ್ಷಿಸಿ. Interval ನಲ್ಲಿ parentheses endpoint ಅನ್ನು ಹೊರಗಿಡುತ್ತದೆ; square brackets endpoint ಅನ್ನು ಸೇರಿಸುತ್ತದೆ.",
        "hi": "समुच्चय-निर्माण रूप (set-builder notation) किसी शर्त से तत्वों का वर्णन करता है। {x ∈ Z : x² = 9} में x पूर्णांक होना चाहिए और उसका वर्ग 9 होना चाहिए। इसलिए -3 और 3 दोनों सही हैं; समुच्चय {-3, 3} है। याद रखें: domain और condition दोनों जाँचें। Interval में parentheses endpoint को बाहर रखते हैं, जबकि square brackets endpoint को शामिल करते हैं."},
      "sets-operations": {
        "kn": "A ∪ B ಎಂದರೆ A ಅಥವಾ Bಯಲ್ಲಿರುವ ಎಲ್ಲ ಅಂಶಗಳು; ಒಂದೇ ಅಂಶವನ್ನು ಎರಡು ಬಾರಿ ಎಣಿಸಬೇಡಿ. A ∩ B ಎಂದರೆ ಎರಡೂ ಸೆಟ್‌ಗಳಲ್ಲಿ ಸಾಮಾನ್ಯವಾಗಿರುವ ಅಂಶಗಳು. A − B ಎಂದರೆ Aಯಲ್ಲಿರುವ ಆದರೆ Bಯಲ್ಲಿಲ್ಲದ ಅಂಶಗಳು. ಸೀಮಿತ ಸೆಟ್‌ಗಳಿಗೆ n(A ∪ B) = n(A) + n(B) − n(A ∩ B). ನೆನಪಿಡಿ: overlap ಅನ್ನು ಒಂದೇ ಬಾರಿ ಕಡಿತಗೊಳಿಸಿ.",
        "hi": "A ∪ B में वे सभी तत्व हैं जो A या B में हों; किसी तत्व को दो बार न गिनें। A ∩ B में केवल वे तत्व हैं जो दोनों समुच्चयों में हों। A − B में वे तत्व हैं जो A में हों लेकिन B में नहीं। सीमित समुच्चयों के लिए n(A ∪ B) = n(A) + n(B) − n(A ∩ B)। याद रखें: overlap को एक बार घटाएँ।"}
    }
    language_lesson = base_english
    if req.language in {"kn", "hi"}:
        translated = bilingual.get(req.conceptId, {}).get(req.language)
        language_lesson = translated or (("ಈ ವಿಷಯಕ್ಕೆ ಪರಿಶೀಲಿತ ಅನುವಾದ ಇನ್ನೂ ಸೇರಿಸಲಾಗಿಲ್ಲ. ಕೆಳಗಿನ ಇಂಗ್ಲಿಷ್ ಟಿಪ್ಪಣಿಯನ್ನು ಓದಿ, ಶಿಕ್ಷಕರ ಸಹಾಯ ಪಡೆಯಿರಿ." if req.language == "kn" else "इस विषय का सत्यापित अनुवाद अभी उपलब्ध नहीं है। नीचे दिए गए अंग्रेज़ी नोट्स पढ़ें और शिक्षक से सहायता लें।") + "\n\n" + base_english)
    source_ids = [str(n["id"]) for n in notes[:3]]
    source_rows = [{"id": n["id"], "title": n["title"], "url": n.get("url", ""), "snippet": n.get("snippet", n["content"][:240]), "attribution": n.get("attribution", "Bundled teaching note; provenance unspecified"), "license": n.get("license", "Review licensing before external reuse")} for n in notes[:3]]
    glossary_terms = {
      "kn": [{"en":"set","local":"ಸೆಟ್"},{"en":"empty set","local":"ಖಾಲಿ ಸೆಟ್"},{"en":"finite","local":"ಸೀಮಿತ"},{"en":"infinite","local":"ಅನಂತ"},{"en":"endpoint","local":"ಅಂತ್ಯ ಬಿಂದು"}],
      "hi": [{"en":"set","local":"समुच्चय"},{"en":"empty set","local":"रिक्त समुच्चय"},{"en":"finite","local":"सीमित"},{"en":"infinite","local":"अनंत"},{"en":"endpoint","local":"अंतिम बिंदु"}],
      "en": []
    }
    return LessonResponse(lesson=language_lesson, sourceIds=source_ids, sources=source_rows, language=req.language, glossary=glossary_terms[req.language])


async def quiz(req: QuizGenerateRequest) -> QuizGenerateResponse:
    topic = (req.topic or req.conceptName).strip()
    subject = (req.subject or "General").strip()
    all_existing = await persistence.get_diagnostic_questions(req.studentId, req.conceptId)
    existing_ids = {str(k) for k in all_existing.keys()}
    forbidden_ids = set(req.previousQuestionIds) | existing_ids
    existing_texts = {
        re.sub(r"\s+", " ", str(r.get("question_text") or r.get("question") or "").strip().lower())
        for r in all_existing.values()
        if r.get("question_text") or r.get("question")
    }

    work_context = list(req.evidenceContext or [])
    diagnosis = None
    if req.mode == "retest":
        stored_work = await persistence.get_recent_work_context(req.studentId, req.conceptId)
        if stored_work:
            work_context = stored_work
        diagnosis = await persistence.get_latest_diagnosis(req.studentId, req.conceptId)

    prompt_parts = [
        "Generate ONE genuinely new academic question.",
        f"Exact subject: {subject}",
        f"Exact topic: {topic}",
        f"Exact concept: {req.conceptName}",
        f"Mode: {req.mode}",
        f"Requested feedback language: {req.language}",
        f"Current mastery: {req.mastery}",
        f"Target skill: {req.skill or 'derive the most appropriate academic skill from the evidence'}",
        f"Target misconception: {req.misconception or 'derive only when evidence supports it'}",
        f"Previously used question IDs: {sorted(forbidden_ids)}",
        "Never reuse any previous question ID and never repeat the wording or structure of an earlier question.",
        "The correct answer must be exactly one of four options.",
        "Return JSON only.",
    ]
    if diagnosis:
        prompt_parts.append("Latest diagnosis:\n" + json.dumps({
            "diagnosis": diagnosis.get("diagnosis"), "recommendation": diagnosis.get("recommendation"),
            "confidence": diagnosis.get("confidence"), "evidence": diagnosis.get("evidence", []),
        }, ensure_ascii=False))
    if work_context:
        prompt_parts.append("Student evidence from the original uploaded work:\n" + json.dumps(work_context, ensure_ascii=False))
        prompt_parts.append("RETEST RULE: test the same underlying skill with new values, arrangement, or scenario. Do not copy the old problem.")
    elif req.mode == "retest":
        prompt_parts.append("For retest, stay tightly aligned to the exact requested topic and diagnosed skill and create a new transfer problem.")

    async def call_once(extra: str = ""):
        raw = await client.complete_json(QUIZ_SYSTEM, "\n".join(prompt_parts) + ("\n" + extra if extra else ""))
        if isinstance(raw.get("question"), dict):
            raw["question"] = {**raw["question"], "conceptId": req.conceptId, "conceptName": raw["question"].get("conceptName") or topic, "difficulty": _difficulty(raw["question"].get("difficulty"))}
        response = QuizGenerateResponse.model_validate(raw)
        q = response.question
        if q.conceptId != req.conceptId:
            raise ValueError("model changed conceptId")
        if q.questionId in forbidden_ids:
            raise ValueError("model reused an existing questionId")
        normalized_q = re.sub(r"\s+", " ", q.question.strip().lower())
        if normalized_q in existing_texts:
            raise ValueError("model repeated an existing question")
        if q.correctAnswer not in q.options or len({x.strip().lower() for x in q.options}) != 4:
            raise ValueError("invalid answer options")
        if not q.question.strip() or not q.explanation.strip():
            raise ValueError("missing question/explanation")
        return response

    try:
        response = await call_once()
    except Exception:
        try:
            response = await call_once(
                "REPAIR: regenerate from scratch. Make the question materially different from every previous question and directly test the exact skill/topic."
            )
        except Exception:
            cached_any = await persistence.get_cached_questions(req.studentId, req.conceptId, mode=req.mode)
            cached_row = next((row for row in cached_any if str(row.get("question_id")) not in forbidden_ids), None)
            if cached_row:
                response = QuizGenerateResponse(question=QuizQuestion(
                    questionId=str(cached_row["question_id"]), conceptId=req.conceptId, conceptName=topic,
                    question=str(cached_row.get("question_text") or ""), options=list(cached_row.get("options") or []),
                    correctAnswer=str(cached_row.get("correct_answer") or ""),
                    difficulty=max(1, min(4, int(cached_row.get("difficulty") or 2))),
                    explanation=str(cached_row.get("explanation") or "Previously generated question."),
                ))
            else:
                # Practice may use a reviewed prepared pack. Retest should not jump
                # back to the old quadratic/demo bank for an arbitrary concept.
                bank = [] if req.mode == "retest" else QUIZ_BANK.get(req.conceptId, [])
                if bank:
                    chosen = next((q for q in bank if q["questionId"] not in forbidden_ids), bank[0])
                    response = QuizGenerateResponse(question=QuizQuestion.model_validate(chosen))
                else:
                    response = QuizGenerateResponse(question=_fallback_quiz(req))

    await persistence.persist_quiz_question(req.studentId, response.question.model_dump(), mode=req.mode, subject=subject, topic=topic)
    return response

async def evaluate_quiz(req: QuizEvaluateRequest) -> QuizEvaluateResponse:
    q = await persistence.get_question(req.studentId, req.conceptId, req.questionId)
    if not q:
        raise ValueError("The question could not be verified on the server. Generate a fresh question and try again.")
    expected = str(q.get("correct_answer") or q.get("correctAnswer") or "").strip()
    if not expected:
        raise ValueError("The stored question has no answer key.")
    correct = req.answer.strip().lower() == expected.lower()
    as_of = req.asOf if DEMO_TIME_TRAVEL else None
    mastery = await persistence.record_attempt(
        req.studentId,
        req.conceptId,
        {
            "questionId": req.questionId,
            "conceptName": q.get("source_context", {}).get("topic") or req.conceptId,
            "correct": correct,
            "answer": req.answer,
            "expectedAnswer": expected,
            "source": req.mode,
            "mode": req.mode,
            "as_of": as_of,
        },
    )
    state = await persistence.get_mastery_state(req.studentId, req.conceptId)
    confirmed = bool(state.get("confirmed", False))
    next_due = state.get("next_due")
    if correct and req.mode == "retest" and not confirmed:
        explanation = "Correct answer, but the retest was early. Mastery remains provisional until a retest is passed after the 24-hour spacing window."
    elif correct and confirmed:
        explanation = "Correct delayed retest. Mastery is now confirmed for this concept."
    elif correct:
        explanation = "Correct. Mastery is still provisional until a delayed retest is passed."
    else:
        explanation = "Review the targeted skill and try another variation. Mastery remains provisional."
    return QuizEvaluateResponse(correct=correct, mastery=mastery, explanation=explanation, confirmed=confirmed, provisional=not confirmed, nextDue=str(next_due) if next_due else None)
