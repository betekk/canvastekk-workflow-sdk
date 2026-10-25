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

const _sessionAssignable: OutputUploader = new SessionUploader();
void _sessionAssignable;
