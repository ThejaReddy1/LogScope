import js from "@eslint/js";
import globals from "globals";
import pluginReact from "eslint-plugin-react";

export default [
  js.configs.recommended,
  pluginReact.configs.flat.recommended,
  {
    files: ["**/*.{js,mjs,cjs,jsx}"],
    languageOptions: {
      globals: {
        ...globals.browser
      }
    },
    settings: {
      react: {
        version: "detect" // Automatically detects your React version to clear the warning
      }
    },
    rules: {
      "react/prop-types": "off", // Disables strict prop-type validation
      "react/no-unescaped-entities": "off" // Allows characters like ' and > in JSX text
    }
  }
];