# LearnLens AI --- Understand the Mistake. Fix the Idea.

**Craft N Code Karnataka 2026 · AI for Education**

LearnLens AI is an AI-assisted learning platform designed to help
students understand the reasoning behind mistakes, revisit concepts, and
check their understanding. It also explores how patterns in learning
difficulties can help teachers plan focused follow-up instruction.

## Project links

-   **Live website:** https://learnlens-ai-beta.vercel.app/
-   **Source code:** https://github.com/i803/LearnLens-AI
-   **Demo video (Google Drive):**
    https://drive.google.com/file/d/1XwmMzWBTFPK11WL_-1suAzWI6Z-Z6sfn/view?usp=sharing
-   **Google Slides:**
    https://docs.google.com/presentation/d/1q64tbaRnrShLjewuNOyLIGgVQteb5G1RzcAqud16Mis/edit?usp=sharing

## 1. Problem and target users

Students may receive a score or correction without understanding the
misconception that led to an incorrect answer. Teachers can also have
limited time to identify recurring learning gaps and prepare targeted
revision.

-   **Primary users:** Students who want to understand and learn from
    mistakes.
-   **Secondary users:** Teachers who want to identify learning gaps and
    plan follow-up instruction.

## 2. Solution and workflow

LearnLens is built around a learning-support loop:

1.  **Submit work or answer a diagnostic:** The learner provides an
    answer or learning input through the available interface.
2.  **Explore the mistake:** AI-assisted feedback can help explain the
    likely reasoning gap, depending on the implemented feature.
3.  **Review the concept:** The learner uses the explanation and any
    available practice support to revisit the topic.
4.  **Check understanding:** A follow-up question or retest, where
    implemented, can help the learner check their understanding.
5.  **Support teaching:** Teacher-facing views, where implemented, can
    help surface patterns that may need additional instruction.

The live site is the deployed demonstration of the project. During
judging, demonstrate only features that are working in the current
build; do not describe planned features as completed functionality.

## 3. AI and data

-   **AI access:** OpenRouter API.
-   **AI model:** The underlying model is the model selected in the
    application's OpenRouter configuration. OpenRouter is the gateway,
    not the model itself; identify the configured model name/ID from the
    project configuration before final submission.
-   **AI tasks:** AI-assisted learning feedback and explanations, to the
    extent implemented in the current application. Describe the exact
    input and output shown in the demo.
-   **Data:** No public dataset is identified in the project information
    used to prepare this README. If the project uses sample questions,
    synthetic examples, or a public dataset, name the source and clearly
    label synthetic data.
-   **Evaluation:** Do not claim measured accuracy or learning gains
    without test records. Before submission, describe the manual test
    cases run, what was checked, and any observed failures or
    limitations.

## 4. Technology and deployment

-   **Frontend:** See the frontend application's package manifest and
    source code in this repository.
-   **Backend/API:** See the backend application's source code and
    configuration in this repository.
-   **Database/storage:** Describe the database or storage service
    actually used; if none is used, state that explicitly.
-   **AI integration:** OpenRouter API; the configured model identifier
    should be documented from the app configuration.
-   **Deployment:** Vercel --- https://learnlens-ai-beta.vercel.app/

For a stronger reproducibility record, add the exact frontend framework,
backend framework, database (if any), and relevant library names after
checking the repository's package manifests and source code.

## 5. Run locally

Clone the project:

``` bash
git clone https://github.com/i803/LearnLens-AI.git
cd LearnLens-AI
```

The repository contains separate application areas if the project is
organized into frontend and backend folders. Check the root README,
package manifests, and available scripts to determine the exact
installation and startup commands for each service. Verify those
commands from a clean checkout before publishing them here.

### Environment variables and secrets

Configure required environment variables locally using the variable
names expected by the application. Never commit API keys, passwords,
access tokens, or production secrets. If the project has an
`.env.example` file, use it as the reference for required variable
names. Keep the actual values private.

## 6. AI development tools, APIs, and reused code

-   **AI API:** OpenRouter.
-   **AI development tools:** Disclose the coding assistants actually
    used by the team.
-   **Third-party libraries and services:** List the main dependencies
    and services from the repository's package manifests and
    configuration.
-   **Reused code/templates:** Disclose any starter templates, copied
    snippets, external repositories, or adapted code. If none were used,
    state that explicitly.

This section should reflect the team's actual development process rather
than assumed tools or dependencies.

## 7. Responsible use, privacy, and accessibility

LearnLens is intended to support learning, not replace a learner's
reasoning or a teacher's judgment. AI-generated explanations may be
incorrect or incomplete and should be checked against reliable learning
materials. Avoid submitting sensitive personal information. Do not
publish secrets in the repository.

Describe the privacy, retention, language-support, and accessibility
behavior that is actually implemented. Do not promise data deletion,
language coverage, or accessibility features unless they have been
tested.

## 8. Current limitations

Known general limitations of an AI-assisted learning tool include the
possibility of incorrect explanations and inconsistent performance
across subjects, question types, and languages. The project's actual
limitations should be demonstrated and documented honestly, including:

-   The AI may misinterpret a learner's reasoning or provide an
    incorrect explanation.
-   The level of testing and evidence for learning improvement may be
    limited.
-   Any planned, incomplete, or externally dependent features should be
    clearly identified during the demo.

Update these points if the team has verified more specific limitations
during testing.

## 9. Demo Video Plan (3 Minutes Maximum)

1. **0:00–0:30 — Problem and Product Introduction:** Explain why a score alone may not help learners understand their mistakes. Introduce LearnLens AI, its purpose, and its target users.

2. **0:30–1:15 — Student Workflow:** Demonstrate joining a fictional classroom, loading the bundled mathematics worksheet, reviewing detected questions and marks, and verifying a suspected misconception.

3. **1:15–1:40 — Targeted Learning and Progress:** Show a focused lesson, a practice question with feedback, and a brief view of progress tracking or student privacy controls.

4. **1:40–2:35 — Teacher Dashboard and Analytics:** Highlight the mastery heatmap, misconception summary, draft reteaching plan, CSV export, and teacher analytics. Explain how these features can help teachers identify concepts that may need further attention.

5. **2:35–3:00 — AI Implementation, Impact, and Limitations:** Briefly explain the OpenRouter integration and identify the configured AI model, if verified. Mention the use of bundled worksheet and synthetic classroom data, acknowledge that classroom pilots and independent evaluation are still needed to establish learning impact, and finish by displaying the project name and live website.


## 10. Team

-   **Team name:** Learn Lens
-   **College:** RV College of Engineering
-   **Kenver Daren D Cunha** --- Team Leader, Full-Stack Integration
-   **Iswar Iyer** --- AI Engineer
-   **Saksham Garg** --- Data QA Research Lead
-   **Sarthak Shetty** --- Product, UX, and Pitch Lead

## 11. Hackathon submission

-   **Event:** Craft N Code Karnataka 2026
-   **Theme:** AI for Education
-   **Live URL:** https://learnlens-ai-beta.vercel.app/
-   **Official submission method:** Open a pull request to the official
    hackathon repository. Place the completed submission file at
    `submissions/_TEMPLATE/submission.md`, following the official
    template exactly.

Before submitting, ensure the source repository is public, the demo
video is no longer than five minutes, the slide deck contains no more
than eight slides, and every link opens without requiring the judges to
request access.
