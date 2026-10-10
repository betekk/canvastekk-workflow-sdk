import { defineConfig } from "tsup";

export default defineConfig({
  entry: ["src/index.ts", "src/cli.ts", "src/express.ts"],
  format: ["esm", "cjs"],
  dts: {
    resolve: true,
    compilerOptions: {
      target: "es2024",
    },
  },
  target: "node24",
  clean: true,
  sourcemap: true,
});
