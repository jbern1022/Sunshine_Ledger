import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

export default defineConfig([
  ...nextVitals,
  ...nextTs,
  {
    // These two React-hooks rules flag the fetch-in-effect pattern the pages
    // and ImpactLens use today (app/page.tsx, app/people/page.tsx,
    // components/ImpactLens.tsx). Kept visible as warnings rather than
    // rewriting working data-fetching components just to turn lint on;
    // revisit when those components are next reworked.
    rules: {
      "react-hooks/set-state-in-effect": "warn",
      "react-hooks/refs": "warn",
    },
  },
  globalIgnores([".next/**", "out/**", "build/**", "next-env.d.ts", "coverage/**"]),
]);
