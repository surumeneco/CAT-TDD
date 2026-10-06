---
name: tech-spring-boot
description: "Implement or test Spring Boot HTTP, dependency-injection, configuration, data, security, and application-context boundaries against approved PI/TCE contracts."
---

# Spring Boot application boundary work

1. Confirm Spring Boot/Spring versions, MVC or WebFlux, configuration/profile conventions, DI, data/security modules, and test setup from build files, technical documents, and current source.
2. Map PI/TCE through request binding and validation, controller/handler, service, repository/external boundaries, and response/error mapping. Do not treat framework defaults as specification unless the project explicitly adopts them.
3. Use a plain unit test where no Spring context is required; use a focused slice or full application context only when that boundary is part of the behavior under test. Mocked infrastructure is not evidence for the real integration.
4. Keep profiles, properties, transactions, security configuration, and context initialization aligned with the environment being tested, and record which context and external dependencies actually ran.
