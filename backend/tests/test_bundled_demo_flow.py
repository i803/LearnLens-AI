"""Regression: judge sample must never rely on AI or persistent storage."""
from fastapi.testclient import TestClient
from app.main import app


def test_full_bundled_demo_flow_without_model_or_database(monkeypatch):
    from app.routers import ai as routes

    async def forbidden(*args, **kwargs):
        raise AssertionError('Demo must not call live AI or persistence')

    for name in ('analyze_work', 'diagnose', 'generate_diagnostic', 'evaluate_diagnostic', 'lesson', 'quiz', 'evaluate_quiz'):
        monkeypatch.setattr(routes, name, forbidden)

    with TestClient(app) as client:
        def call(path, data):
            res = client.post(f'{path}?demo=true', json=data)
            assert res.status_code == 200, res.text
            return res.json()

        analysis = client.post('/work/analyze?demo=true', data={'studentId': 'judge-demo'})
        assert analysis.status_code == 200
        assert analysis.json()['source'] == 'demo'
        assert len(analysis.json()['questions']) == 8
        diagnosis = call('/diagnosis', {'studentId': 'judge-demo', 'extractedQuestions': analysis.json()['questions']})
        cid = diagnosis['weakestConceptId']
        generated = call('/diagnostic/generate', {'studentId': 'judge-demo', 'conceptId': cid, 'conceptName': diagnosis['weakestConceptName'], 'count': 5})
        questions = generated['questions']
        assert len({q['questionId'] for q in questions}) == 5
        checked = call('/diagnostic/evaluate', {'studentId': 'judge-demo', 'conceptId': cid, 'answers': {q['questionId']: q['correctAnswer'] for q in questions}})
        assert checked['scorePercent'] == 100
        lesson = call('/lesson/generate', {'studentId': 'judge-demo', 'conceptId': cid, 'conceptName': diagnosis['weakestConceptName']})
        assert lesson['lesson']
        quiz = call('/quiz/generate', {'studentId': 'judge-demo', 'conceptId': cid, 'conceptName': diagnosis['weakestConceptName']})['question']
        result = call('/quiz/evaluate', {'studentId': 'judge-demo', 'conceptId': cid, 'questionId': quiz['questionId'], 'answer': quiz['correctAnswer']})
        assert result['correct'] is True
