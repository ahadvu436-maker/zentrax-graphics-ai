"use client";

import { useEffect, useState } from "react";
import Image from "next/image";

// --------------------------------------------------------------------------- //
// Types
// --------------------------------------------------------------------------- //

export type DesignType = "logo" | "banner" | "image";

export interface ResultDisplayProps {
  /** URL of the generated image. Undefined/null = nothing generated yet. */
  imageUrl ? : string | null;
  /** Alt text — ideally the original prompt. */
  alt ? : string;
  /** Used to pick a sensible placeholder and aspect ratio. */
  designType ? : DesignType;
  /** External loading flag (e.g. while the API request is in flight). */
  isGenerating ? : boolean;
  /** Optional error message surfaced above the image area. */
  errorMessage ? : string | null;
  /** Show a download link/button once an image is loaded. */
  showDownload ? : boolean;
  className ? : string;
}

const PLACEHOLDER_BY_TYPE: Record < DesignType, string > = {
  logo: "/images/placeholders/logo-placeholder.png",
  banner: "/images/placeholders/banner-placeholder.png",
  image: "/images/placeholders/image-placeholder.png",
};

const ASPECT_BY_TYPE: Record < DesignType, string > = {
  logo: "aspect-square",
  banner: "aspect-[3/1]",
  image: "aspect-square",
};

// --------------------------------------------------------------------------- //
// Component
// --------------------------------------------------------------------------- //

export default function ResultDisplay({
  imageUrl,
  alt = "Generated design",
  designType = "image",
  isGenerating = false,
  errorMessage,
  showDownload = true,
  className = "",
}: ResultDisplayProps) {
  const [imgFailed, setImgFailed] = useState(false);
  const [imgLoaded, setImgLoaded] = useState(false);
  
  const placeholder = PLACEHOLDER_BY_TYPE[designType];
  const aspectClass = ASPECT_BY_TYPE[designType];
  
  const hasValidImage = Boolean(imageUrl) && !imgFailed;
  const displaySrc = hasValidImage ? (imageUrl as string) : placeholder;
  
  // Reset load/error state whenever a new image URL comes in.
  useEffect(() => {
    setImgFailed(false);
    setImgLoaded(false);
  }, [imageUrl]);
  
  return (
    <div
      className={`zx-card flex w-full flex-col items-center p-6 ${className}`}
    >
      <div
        className={`relative w-full max-w-sm overflow-hidden rounded-xl border border-white/10 bg-neutral-950 ${aspectClass}`}
      >
        {/* Skeleton shimmer while generating or while the real image is still loading */}
        {(isGenerating || (hasValidImage && !imgLoaded)) && (
          <div className="absolute inset-0 z-10 animate-pulse bg-gradient-to-br from-neutral-800 via-neutral-900 to-neutral-800" />
        )}

        {/* Spinner overlay specifically for the "generating" state */}
        {isGenerating && (
          <div className="absolute inset-0 z-20 flex flex-col items-center justify-center gap-3 bg-neutral-950/60">
            <span className="h-8 w-8 animate-spin rounded-full border-2 border-amber-500 border-t-transparent" />
            <span className="text-sm text-neutral-300">Generating…</span>
          </div>
        )}

        {/* Error message overlay */}
        {!isGenerating && errorMessage && (
          <div className="absolute inset-0 z-20 flex items-center justify-center bg-neutral-950/80 px-6 text-center">
            <p className="text-sm text-red-400">{errorMessage}</p>
          </div>
        )}

        {/* The image itself — real image, or placeholder as graceful fallback */}
        {!isGenerating && (
          <Image
            key={displaySrc}
            src={displaySrc}
            alt={hasValidImage ? alt : "No design generated yet"}
            fill
            unoptimized={hasValidImage} // remote/generated URLs skip Next's optimizer; local placeholders keep it
            sizes="(max-width: 640px) 90vw, 384px"
            className={`object-cover transition-opacity duration-300 ${
              imgLoaded || !hasValidImage ? "opacity-100" : "opacity-0"
            } ${!hasValidImage ? "opacity-50" : ""}`}
            onLoad={() => setImgLoaded(true)}
            onError={() => setImgFailed(true)}
            priority={false}
          />
        )}

        {/* Empty-state hint text, only shown over the placeholder */}
        {!isGenerating && !hasValidImage && !errorMessage && (
          <div className="absolute inset-0 z-10 flex items-center justify-center px-6 text-center">
            <span className="text-sm text-neutral-500">
              {imgFailed
                ? "Couldn't load the generated image"
                : "Your generated design will appear here"}
            </span>
          </div>
        )}
      </div>

      {/* Footer: metadata + download, only for a real, successfully loaded image */}
      {hasValidImage && imgLoaded && !isGenerating && (
        <div className="mt-4 flex w-full max-w-sm items-center justify-between text-xs text-neutral-500">
          <span className="truncate capitalize">{designType}</span>
          {showDownload && (
            <a
              href={imageUrl as string}
              download
              className="font-medium text-amber-500 transition hover:text-amber-400 hover:underline"
            >
              Download
            </a>
          )}
        </div>
      )}
    </div>
  );
}