import type { NodeExecutionResponse, NodeOutputUploader, NodeOutputUploadTarget } from "../src/index.js";

class SessionUploader implements NodeOutputUploader {
  async uploadFile(filePath: string, target: NodeOutputUploadTarget): Promise<void> {
    void filePath;
    void target;
  }

  async uploadOutputs(
    response: NodeExecutionResponse,
    uploadUrls: Record<string, NodeOutputUploadTarget>,
    fileOutputFields: string[],
  ): Promise<void> {
    void response;
    void uploadUrls;
    void fileOutputFields;
  }
}

const _sessionAssignable: NodeOutputUploader = new SessionUploader();
void _sessionAssignable;
