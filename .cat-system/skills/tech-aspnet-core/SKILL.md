---
name: tech-aspnet-core
description: "Implement or test ASP.NET Core HTTP, dependency-injection, middleware, validation, authorization, and hosting boundaries against approved PI/TCE contracts."
---

# ASP.NET Core web boundary work

1. Confirm the ASP.NET Core/.NET version, hosting model, controller or minimal-API style, middleware order, DI conventions, authentication/authorization, serialization, and test host from project documents and current source.
2. Map PI request path/query/header/body inputs through binding and validation to response status, headers, and body. Map TCE effects to the service/persistence boundary without inventing behavior from framework defaults.
3. Preserve middleware ordering, DI lifetime assumptions, error mapping, authorization boundaries, and transaction semantics. A mocked service or repository test proves only the mocked boundary.
4. Choose unit, focused integration, or application-host testing according to the contract being proved and the project's established test setup. Record whether real databases or external services were exercised.
