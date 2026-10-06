---
name: tech-fastapi
description: "Implement or test FastAPI request validation, dependency, response, lifespan, and ASGI boundaries against approved PI/TCE contracts."
---

# FastAPI web boundary work

1. Confirm FastAPI, Pydantic, ASGI/runtime versions, route/dependency/auth/database conventions, lifespan handling, and test client from project documents and current source.
2. Map PI path/query/header/body inputs through validation and dependencies to response models, status codes, headers, and error forms. Generated OpenAPI is a derived artifact, not the specification oracle.
3. When tests override dependencies, keep the override scope explicit, distinguish mocked and real dependencies, and restore project state after the test.
4. Async execution, lifespan hooks, databases, and external services require the integration boundary appropriate to the TCE effect. Record whether the test exercised an in-process ASGI app or a real deployed/runtime boundary.
