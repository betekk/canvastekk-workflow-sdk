import { timingSafeEqual } from "node:crypto";

/**
 * Checks if dev mode is enabled via CANVASTEKK_DEV_MODE env var.
 *
 * ⚠️ **WARNING**: Dev mode bypasses ALL authentication. Never enable in production.
 * @returns True if dev mode is active
 */
function isDevMode(): boolean {
  return ["true", "1", "yes"].includes(
    (process.env.CANVASTEKK_DEV_MODE ?? "").toLowerCase(),
  );
}

/**
 * Minimal request surface read by auth middleware. Structural — express's
 * `Request` satisfies it without importing express types into the core
 * declaration output.
 */
export interface AuthRequest {
  /** Raw headers; narrow with the module-local `header()` helper. */
  headers: unknown;
}

/** Minimal response surface used by auth middleware (express-compatible). */
export interface AuthResponse {
  status(code: number): { json(body: unknown): unknown };
}

/** Continuation callback for auth middleware (express-compatible). */
export type AuthNext = () => void;

/** Authentication result. */
export interface AuthResult {
  authMode: string;
  payload?: Record<string, unknown>;
}

/** Server middleware function for authentication. */
export type AuthMiddleware = (
  req: AuthRequest,
  res: AuthResponse,
  next: AuthNext,
) => void;

/** Reads a single header value as a string (first member when repeated). */
function header(req: AuthRequest, name: string): string | undefined {
  const raw = (req.headers as Record<string, unknown> | null | undefined)?.[name];
  if (Array.isArray(raw)) return typeof raw[0] === "string" ? raw[0] : undefined;
  return typeof raw === "string" ? raw : undefined;
}

/**
 * Property tagged on middleware produced by NodeAuth factories so callers
 * (e.g. createNodeApp) can detect that authentication is configured.
 */
export const CANVASTEKK_AUTH_MARKER = "_canvastekkAuth";

/** Tags an auth middleware with the detection marker and returns it. */
function markAuth<T extends AuthMiddleware>(mw: T): T {
  return Object.assign(mw, { [CANVASTEKK_AUTH_MARKER]: true });
}


/**
 * Sends a 401 Unauthorized JSON response.
 *
 * @param res - Express response object
 * @param detail - Error detail message
 */
function unauthorized(res: AuthResponse, detail: string): void {
  res.status(401).json({ detail });
}

/**
 * Authentication middleware for CanvasTEKK nodes.
 */
export class NodeAuth {
  /**
   * Creates API key authentication middleware.
   * @param keyEnvVar - Environment variable name for API key
   * @returns Express middleware function
   */
  static apiKey(keyEnvVar = "CANVASTEKK_API_KEY"): AuthMiddleware {
    return markAuth((req: AuthRequest, res: AuthResponse, next: AuthNext) => {
      if (isDevMode()) {
        next();
        return;
      }

      // Rotation window (DA-3191): <keyEnvVar>_NEXT is accepted alongside the
      // current key; empty values are ignored.
      const expectedKeys = [
        process.env[keyEnvVar] ?? "",
        process.env[`${keyEnvVar}_NEXT`] ?? "",
      ].filter((key) => key.length > 0);

      if (expectedKeys.length === 0) {
        unauthorized(res, "Authentication not configured");
        return;
      }

      const providedKey = header(req, "x-api-key") ?? "";
      const provided = Buffer.from(providedKey);

      const matches = expectedKeys.some((key) => {
        const expected = Buffer.from(key);
        return expected.length === provided.length && timingSafeEqual(provided, expected);
      });

      if (!matches) {
        unauthorized(res, "Invalid API key");
        return;
      }

      next();
    });
  }

  /**
   * Creates JWT authentication middleware.
   * @param opts - JWT options including secret variable and algorithm
   * @returns Express middleware function
   */
  static jwt(opts?: {
    secretEnvVar?: string;
    algorithm?: string;
    audience?: string;
  }): AuthMiddleware {
    const secretEnvVar = opts?.secretEnvVar ?? "CANVASTEKK_JWT_SECRET";
    const algorithm = opts?.algorithm ?? "HS256";
    const audience = opts?.audience;

    return markAuth(async (req: AuthRequest, res: AuthResponse, next: AuthNext) => {
      if (isDevMode()) {
        next();
        return;
      }

      const secret = process.env[secretEnvVar] ?? "";
      if (!secret) {
        unauthorized(res, "JWT authentication not configured");
        return;
      }

      const authHeader = header(req, "authorization") ?? "";
      if (!authHeader.startsWith("Bearer ")) {
        unauthorized(res, "Missing Bearer token");
        return;
      }

      const token = authHeader.substring(7);

      try {
        const jwt = await import("jsonwebtoken");
        const decodeOpts: Record<string, unknown> = { algorithms: [algorithm] };
        if (audience) decodeOpts.audience = audience;
        jwt.verify(token, secret, decodeOpts);
        next();
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : String(err);
        if (msg.includes("expire")) {
          unauthorized(res, "Token has expired");
        } else {
          unauthorized(res, `Invalid token: ${msg}`);
        }
      }
    });
  }

  /**
   * Creates Keycloak JWT authentication middleware.
   *
   * Note: Only JWK keys containing an `x5c` (X.509 certificate chain) field
   * are supported. Keys with only RSA `n`/`e` parameters are not parsed.
   * If your Keycloak realm issues non-x5c keys, consider migrating to the
   * `jose` library for full JWK format support.
   *
   * @param opts - Keycloak options including server URL and realm
   * @returns Express middleware function
   */
  static keycloak(opts?: {
    serverUrl?: string;
    realm?: string;
    audience?: string;
    algorithm?: string;
  }): AuthMiddleware {
    const serverUrl = opts?.serverUrl ?? process.env.CANVASTEKK_KEYCLOAK_SERVER_URL ?? "";
    const realm = opts?.realm ?? process.env.CANVASTEKK_KEYCLOAK_REALM ?? "";
    const audience = opts?.audience ?? process.env.CANVASTEKK_KEYCLOAK_AUDIENCE;
    const algorithm = opts?.algorithm ?? "RS256";

    let jwksKeys: Map<string, string> | null = null;
    let jwksFetchedAt = 0;
    const jwksTtl = 300_000;
    let lastRefreshAttempt = 0;
    const refreshCooldown = 10_000;

    /**
     * Converts a base64-encoded certificate to PEM format.
     * @param b64 - Base64-encoded certificate
     * @returns PEM-formatted certificate
     */
    function b64ToPem(b64: string): string {
      const lines: string[] = [];
      for (let i = 0; i < b64.length; i += 64) {
        lines.push(b64.slice(i, i + 64));
      }
      return `-----BEGIN CERTIFICATE-----\n${lines.join("\n")}\n-----END CERTIFICATE-----`;
    }

    /**
     * Fetches JWKS from Keycloak endpoint.
     *
     * Only keys containing an x5c (X.509 certificate chain) field are parsed.
     * Keys with only RSA n/e parameters are ignored.
     *
     * @returns Map of key ID to PEM certificate string
     * @throws {Error} If server URL or realm not configured
     * @throws {Error} If network fetch fails (thrown as JwksNetworkError)
     */
    async function fetchJwks(): Promise<Map<string, string>> {
      if (!serverUrl || !realm) {
        throw new Error("Keycloak server URL and realm must be configured");
      }
      const jwksUrl = `${serverUrl.replace(/\/$/, "")}/realms/${realm}/protocol/openid-connect/certs`;
      let resp: globalThis.Response;
      try {
        resp = await fetch(jwksUrl, { signal: AbortSignal.timeout(10_000) });
      } catch {
        const err = new Error("Failed to connect to Keycloak JWKS endpoint");
        err.name = "JwksNetworkError";
        throw err;
      }
      if (!resp.ok) {
        const err = new Error(`Failed to fetch JWKS: HTTP ${resp.status}`);
        err.name = "JwksNetworkError";
        throw err;
      }
      const data = await resp.json() as { keys?: Array<{ kid?: string; x5c?: string[]; n?: string; e?: string; kty?: string }> };
      const map = new Map<string, string>();
      if (data.keys) {
        for (const key of data.keys) {
          if (key.kid && key.x5c?.[0]) {
            map.set(key.kid, b64ToPem(key.x5c[0]));
          }
        }
      }
      return map;
    }

    return markAuth(async (req: AuthRequest, res: AuthResponse, next: AuthNext) => {
      if (isDevMode()) {
        next();
        return;
      }

      const authHeader = header(req, "authorization") ?? "";
      if (!authHeader.startsWith("Bearer ")) {
        unauthorized(res, "Missing Bearer token");
        return;
      }

      const token = authHeader.substring(7);

      try {
        const jwt = await import("jsonwebtoken") as unknown as {
          verify: (token: string, secretOrPublicKey: string, options?: Record<string, unknown>) => unknown;
          decode: (token: string, options?: Record<string, unknown>) => { header?: { kid?: string } } | null;
        };

        const now = Date.now();
        if (!jwksKeys || (now - jwksFetchedAt) > jwksTtl) {
          jwksKeys = await fetchJwks();
          jwksFetchedAt = now;
        }

        const decoded = jwt.decode(token, { complete: true });
        const kid = decoded?.header?.kid;

        if (!kid) {
          unauthorized(res, "Token header missing required 'kid' field");
          return;
        }

        let signingKey: string | undefined;
        if (jwksKeys.has(kid)) {
          signingKey = jwksKeys.get(kid);
        }

        if (!signingKey) {
          if (now - lastRefreshAttempt < refreshCooldown) {
            console.warn(
              `[auth] Token kid '${kid}' not found in JWKS — refresh skipped (cooldown ${Math.ceil((refreshCooldown - (now - lastRefreshAttempt)) / 1000)}s remaining)`,
            );
            unauthorized(res, `Token signing key (kid='${kid}') not found in JWKS`);
            return;
          }
          console.warn(
            `[auth] Token kid '${kid}' not found in cached JWKS — forcing refresh (available: ${[...jwksKeys.keys()].join(", ")})`,
          );
          lastRefreshAttempt = now;
          jwksKeys = null;
          jwksFetchedAt = 0;
          try {
            jwksKeys = await fetchJwks();
            jwksFetchedAt = now;
          } catch (err) {
            if (err instanceof Error && err.name === "JwksNetworkError") throw err;
            unauthorized(res, `Token signing key (kid='${kid}') not found in JWKS`);
            return;
          }
          if (jwksKeys.has(kid)) {
            signingKey = jwksKeys.get(kid);
          }
        }

        if (!signingKey) {
          unauthorized(res, `Token signing key (kid='${kid}') not found in JWKS`);
          return;
        }

        const decodeOpts: Record<string, unknown> = { algorithms: [algorithm] };
        if (audience) decodeOpts.audience = audience;
        jwt.verify(token, signingKey, decodeOpts);
        next();
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : String(err);
        if (err instanceof Error && err.name === "JwksNetworkError") {
          res.status(503).json({ detail: `Keycloak unavailable: ${msg}` });
        } else {
          unauthorized(res, `Invalid token: ${msg}`);
        }
      }
    });
  }
}
