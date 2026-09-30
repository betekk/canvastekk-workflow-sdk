// DA-3314 compile-time fixture (arch review m2), updated for DA-3340: a
// custom uploader parameterized on `UploadTarget` must remain assignable to
// `OutputUploader`. This holds because the interface declares `uploadFile`
// as a METHOD (parameter bivariance under `strictFunctionTypes`); converting
// it to a property-arrow signature would break this fixture and every
// external custom uploader.
// DA-3340 note: a STRING-only uploader no longer typechecks — the legacy
// presigned-PUT member was removed from `UploadTarget` (breaking, 0.36.0).
// Checked by: npx tsc --noEmit --strict tests/legacy-uploader-fixture.ts
import type { NodeExecutionResponse, OutputUploader, UploadTarget } from "../src/index.js";

class SessionUploader implements OutputUploader {
  async uploadFile(filePath: string, target: UploadTarget): Promise<void> {
    void filePath;
    void target;
  }

  async uploadOutputs(
    response: NodeExecutionResponse,
    uploadUrls: Record<string, UploadTarget>,
    fileOutputFields: string[],
  ): Promise<void> {
    void response;
    void uploadUrls;
    void fileOutputFields;
  }
}

// Assignment itself is the assertion — this file only typechecks.
const _sessionAssignable: OutputUploader = new SessionUploader();
void _sessionAssignable;
