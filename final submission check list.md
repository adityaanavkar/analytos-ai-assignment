# Final Submission Checklist

## 0-10 minutes: Verify

- [x] Start the local application.
- [x] Test one normal document question.
- [x] Test one missing-information question.
- [x] Test the indexed-document listing question.
- [ ] Capture useful screenshots.
- [x] Run the final automated tests.

Verification result: The Azure-backed application returned a grounded policy answer, safely refused an unsupported question, and reported exactly 11 indexed documents.

Quality result: All 180 tests, Ruff lint, Ruff formatting, and strict mypy checks passed.

Citation correction: Internal chunk identifiers remain available to the API for validation, but the browser now displays clean numbered citations and collapses accidental nested citation brackets.

Home-screen regression result: All four built-in prompts now return grounded answers after preserving concrete requirement rows and safely expanding grouped verified citations.

## 10-25 minutes: Architecture

- [x] Create the production Azure architecture diagram.
- [x] Show authentication, App Service, RAG API, Storage, AI Search, Azure OpenAI, Key Vault, Application Insights, scaling, cost controls, and department isolation.

## 25-35 minutes: Documentation

- [x] Finalize the README.
- [x] Include setup and run commands.
- [x] Include Azure services and architecture decisions.
- [x] Include baseline versus improved evaluation results.
- [x] Include security design, limitations, and production improvements.
- [x] Link the architecture diagram and evaluation artifacts.

## 35-40 minutes: GitHub

- [x] Confirm that `.env`, credentials, and secrets are not tracked.
- [x] Review `git status`.
- [x] Commit and push the final repository.
- [ ] Confirm that the GitHub repository link opens correctly.

Git result: `main` was pushed to `origin` at commit `7bd323b`.

Access result: The unauthenticated GitHub URL currently returns HTTP 404, so repository visibility or reviewer access must be changed manually before submission.

## 40-55 minutes: Video

- [ ] Record the required five-minute video.
- [ ] Explain the architecture and Azure services.
- [ ] Demonstrate the working chatbot.
- [ ] Show one successful answer and one insufficient-evidence response.
- [ ] Explain the main RAG failure and improvement.
- [ ] Show baseline versus improved evaluation results.
- [ ] State what would be added before production.
- [ ] Upload the video and confirm that its link is accessible.

## 55-60 minutes: Submit

- [ ] Attach or link the GitHub repository.
- [ ] Attach or link the architecture diagram.
- [ ] Attach or link the evaluation results.
- [ ] Include the video link.
- [ ] Attach the latest resume.
- [ ] Email `santosh.thota@analytos.ai` and CC `ashok.suthar@analytos.ai`.
- [ ] Use subject `Senior AI Engineer - Azure RAG Task - Aditya Anavkar`.

## Do Not Spend Time On

- Public App Service deployment.
- More UI polishing.
- New retrieval features.
- Large refactors.
- Additional evaluation cases.
- Full access-control implementation.
