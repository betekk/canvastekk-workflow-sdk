// DA-3314 compile-time fixture (arch review m2): a legacy-only uploader —
// `uploadFile` still parameterized on `string` — must remain assignable to
// `OutputUploader` after the DA-2886 target widening. This holds because the
// interface declares `uploadFile` as a METHOD (parameter bivariance under
// `strictFunctionTypes`); converting it to a property-arrow signature would
// break this fixture and every external custom uploader.
// Checked by: npx tsc --noEmit --strict tests/legacy-uploader-fixture.ts
import type { NodeExecutionResponse, OutputUploader } from "../src/index.js";

class LegacyOnlyUploader implements OutputUploader {
  async uploadFile(filePath: string, presignedUrl: string): Promise<void> {
    void filePath;
    void presignedUrl;
  }

  async uploadOutputs(
    response: NodeExecutionResponse,
    uploadUrls: Record<string, string>,
    fileOutputFields: string[],
  ): Promise<void> {
    void response;
    void uploadUrls;
    void fileOutputFields;
  }
}

// Assignment itself is the assertion — this file only typechecks.
const _legacyAssignable: OutputUploader = new LegacyOnlyUploader();
void _legacyAssignable;
