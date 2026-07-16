/* eslint-disable */
/**
 * Generated `api` utility.
 *
 * THIS CODE IS AUTOMATICALLY GENERATED.
 *
 * To regenerate, run `npx convex dev`.
 * @module
 */

import type * as agent from "../agent.js";
import type * as auth from "../auth.js";
import type * as guardianLinks from "../guardianLinks.js";
import type * as hazard from "../hazard.js";
import type * as hazardAgent from "../hazardAgent.js";
import type * as healthCheck from "../healthCheck.js";
import type * as http from "../http.js";
import type * as overwatch from "../overwatch.js";
import type * as overwatchAgent from "../overwatchAgent.js";
import type * as privateData from "../privateData.js";
import type * as userProfiles from "../userProfiles.js";

import type {
  ApiFromModules,
  FilterApi,
  FunctionReference,
} from "convex/server";

declare const fullApi: ApiFromModules<{
  agent: typeof agent;
  auth: typeof auth;
  guardianLinks: typeof guardianLinks;
  hazard: typeof hazard;
  hazardAgent: typeof hazardAgent;
  healthCheck: typeof healthCheck;
  http: typeof http;
  overwatch: typeof overwatch;
  overwatchAgent: typeof overwatchAgent;
  privateData: typeof privateData;
  userProfiles: typeof userProfiles;
}>;

/**
 * A utility for referencing Convex functions in your app's public API.
 *
 * Usage:
 * ```js
 * const myFunctionReference = api.myModule.myFunction;
 * ```
 */
export declare const api: FilterApi<
  typeof fullApi,
  FunctionReference<any, "public">
>;

/**
 * A utility for referencing Convex functions in your app's internal API.
 *
 * Usage:
 * ```js
 * const myFunctionReference = internal.myModule.myFunction;
 * ```
 */
export declare const internal: FilterApi<
  typeof fullApi,
  FunctionReference<any, "internal">
>;

export declare const components: {
  betterAuth: import("@convex-dev/better-auth/_generated/component.js").ComponentApi<"betterAuth">;
};
