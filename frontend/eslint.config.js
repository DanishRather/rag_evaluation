import boundaries from "eslint-plugin-boundaries";
import tseslint from "typescript-eslint";

export default tseslint.config(
  {
    files: ["src/**/*.{ts,tsx}"],
    languageOptions: {
      parser: tseslint.parser,
      parserOptions: {
        ecmaFeatures: { jsx: true },
      },
    },
    plugins: { boundaries },
    settings: {
      "boundaries/elements": [
        { type: "view", pattern: "src/view/**" },
        { type: "controller", pattern: "src/controller/**" },
        { type: "services", pattern: "src/services/**" },
        { type: "model-api", pattern: "src/model/api/**" },
        { type: "model-types", pattern: "src/model/types/**" },
        { type: "model-stores", pattern: "src/model/stores/**" },
        { type: "http", pattern: "src/http/**" },
        { type: "app", pattern: "src/app/**" },
        { type: "main", pattern: "src/main.tsx" },
      ],
    },
    rules: {
      "boundaries/element-types": [
        "error",
        {
          default: "disallow",
          rules: [
            { from: "view", allow: ["view", "model-types"] },
            { from: "controller", allow: ["controller", "view", "services", "model-types", "model-stores"] },
            { from: "services", allow: ["services", "model-api", "model-types"] },
            { from: "model-api", allow: ["model-api", "model-types"] },
            { from: "model-types", allow: ["model-types"] },
            { from: "model-stores", allow: ["model-stores", "model-types"] },
            { from: "http", allow: ["http", "model-api", "model-types"] },
            { from: "app", allow: ["app", "controller", "view", "model-stores", "model-types"] },
            { from: "main", allow: ["app", "http", "services", "controller", "model-stores"] },
          ],
        },
      ],
    },
  },
);
