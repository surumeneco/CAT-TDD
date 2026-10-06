---
name: tech-nextjs
description: "Implement or test Next.js routing, server/client rendering, data access, and route-handler boundaries against approved PI/TCE contracts. Use only when the documented component uses Next.js."
---

# Next.js application boundary work

1. Confirm the Next.js version, App Router or Pages Router, runtime/deployment target, data/cache/auth conventions, and build/test commands from project technical documents and current source. Do not assume App Router semantics in a Pages Router component or vice versa.
2. Preserve the project's server/client boundary. Keep browser-only interaction on the client side and server-only data or secrets on the server side; do not move the boundary merely to make a test pass.
3. Map PI/TCE to route parameters, search/query inputs, request/response data, rendered output, and Route Handler/API behavior where applicable. Treat cache, revalidation, and static/dynamic rendering as observable requirements only when the specification or project constraints make them relevant.
4. Test at the narrowest boundary that proves the contract: component, server function, route, or browser. Record the runtime actually exercised; a successful build does not prove deployed routing or external integration behavior.
