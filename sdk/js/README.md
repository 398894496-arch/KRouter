# krouter (JavaScript / TypeScript)

Ask your [KRouter](https://github.com/398894496-arch/KRouter) memory from Node 18+: the page that answers, its
one-line answer, or "not in the vault". No dependencies; it speaks MCP to KRouter's own server.

```js
import { KRouter } from "krouter";

const kr = KRouter.local();                     // starts the local server over stdio (after the one-line install)
const a = await kr.ask("how do we ship a release?");
a.page;      // the page it came from
a.how;       // the one-line answer
a.refused;   // true when the memory does not know
await kr.close();

const team = KRouter.remote("https://krouter.example/mcp/team", { token: process.env.KROUTER_TOKEN });
```

`KRouter.local({ vault, python, server })` picks another vault, interpreter or server path. Tests:
`node --test test/krouter.test.js` (runs the real server over stdio and HTTP). Not published to npm yet.
