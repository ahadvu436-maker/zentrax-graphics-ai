/**
 * frontend/src/services/api.ts
 *
 * Centralized Axios client for the Zentrax AI platform.
 * Wraps all calls to the FastAPI backend (design generation, status
 * polling, auth) so components never talk to fetch/axios directly.
 */

import axios, {
  AxiosError,
  AxiosInstance,
  InternalAxiosRequestConfig,
} from "axios";

// --------------------------------------------------------------------------- //
// Types (mirrors backend/app/models/schemas.py)
// --------------------------------------------------------------------------- //

export type DesignType = "logo" | "banner" | "image";
export type DesignStyle = |
  "minimalist" |
  "realistic" |
  "cartoon" |
  "vintage" |
  "abstract" |
  "corporate" |
  "3d_render";
export type ColorMode = "color" | "monochrome" | "duotone";
export type Resolution = |
  "512x512" |
  "1024x1024" |
  "1500x500" |
  "1200x628" |
  "1920x1080";
export type GenerationStatus = |
  "pending" |
  "processing" |
  "completed" |
  "failed";

export interface GeneratedAsset {
  asset_id: string;
  file_url: string;
  thumbnail_url ? : string;
  resolution: Resolution;
}

export interface GenerationResponse {
  request_id: string;
  status: GenerationStatus;
  design_type: DesignType;
  prompt: string;
  style: DesignStyle;
  assets: GeneratedAsset[];
  error_message ? : string | null;
  created_at: string;
  completed_at ? : string | null;
}

export interface LogoGenerationPayload {
  prompt: string;
  brand_name: string;
  tagline ? : string;
  style ? : DesignStyle;
  color_mode ? : ColorMode;
  resolution ? : Resolution;
  transparent_background ? : boolean;
  negative_prompt ? : string;
  seed ? : number;
}

export interface ImageGenerationPayload {
  prompt: string;
  design_type ? : Extract < DesignType,
  "banner" | "image" > ;
  style ? : DesignStyle;
  color_mode ? : ColorMode;
  resolution ? : Resolution;
  num_variations ? : number;
  negative_prompt ? : string;
  seed ? : number;
}

export interface ApiErrorShape {
  detail ? : string | { msg: string;loc: (string | number)[] } [];
}

// --------------------------------------------------------------------------- //
// Axios instance
// --------------------------------------------------------------------------- //

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export const apiClient: AxiosInstance = axios.create({
  baseURL: `${API_BASE_URL}/api/v1`,
  timeout: 45_000, // generation can be slow — allow more headroom than a typical CRUD call
  headers: {
    "Content-Type": "application/json",
  },
});

// Attach auth token (if present) to every outgoing request.
apiClient.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  if (typeof window !== "undefined") {
    const token = window.localStorage.getItem("zentrax_token");
    if (token) {
      config.headers.set("Authorization", `Bearer ${token}`);
    }
  }
  return config;
});

// Normalize errors into a single readable message.
apiClient.interceptors.response.use(
  (response) => response,
  (error: AxiosError < ApiErrorShape > ) => {
    const detail = error.response?.data?.detail;
    
    let message = "Something went wrong. Please try again.";
    if (typeof detail === "string") {
      message = detail;
    } else if (Array.isArray(detail) && detail.length > 0) {
      message = detail.map((d) => d.msg).join(", ");
    } else if (error.message) {
      message = error.message;
    }
    
    return Promise.reject(new Error(message));
  }
);

// --------------------------------------------------------------------------- //
// API methods
// --------------------------------------------------------------------------- //

/** Generate a logo from a text prompt + brand details. */
export async function generateLogo(
  payload: LogoGenerationPayload
): Promise < GenerationResponse > {
  const { data } = await apiClient.post < GenerationResponse > (
    "/design/logo/generate",
    payload
  );
  return data;
}

/** Generate a generic image or banner from a text prompt. */
export async function generateImage(
  payload: ImageGenerationPayload
): Promise < GenerationResponse > {
  const { data } = await apiClient.post < GenerationResponse > (
    "/design/image/generate",
    payload
  );
  return data;
}

/** Poll the status of an in-progress generation request. */
export async function getGenerationStatus(
  requestId: string
): Promise < GenerationResponse > {
  const { data } = await apiClient.get < GenerationResponse > (
    `/design/status/${requestId}`
  );
  return data;
}

/**
 * Poll a generation request until it completes or fails.
 * Useful if the backend returns `pending`/`processing` immediately
 * and does the actual generation asynchronously.
 */
export async function pollGenerationUntilDone(
  requestId: string, { intervalMs = 2000, timeoutMs = 60_000 }: { intervalMs ? : number;timeoutMs ? : number } = {}
): Promise < GenerationResponse > {
  const start = Date.now();
  
  while (Date.now() - start < timeoutMs) {
    const result = await getGenerationStatus(requestId);
    if (result.status === "completed" || result.status === "failed") {
      return result;
    }
    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }
  
  throw new Error("Generation timed out. Please try again.");
}

const api = {
  generateLogo,
  generateImage,
  getGenerationStatus,
  pollGenerationUntilDone,
};

export default api;