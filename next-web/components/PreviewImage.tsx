"use client";

import { useState } from "react";

import { buildImageProxyUrl } from "@/lib/imageProxy";

type PreviewImageProps = {
  src: string;
  alt: string;
  className?: string;
  loading?: "lazy" | "eager";
};

export function PreviewImage({
  src,
  alt,
  className,
  loading = "lazy",
}: PreviewImageProps) {
  const [imgSrc, setImgSrc] = useState(src);

  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      alt={alt}
      className={className}
      loading={loading}
      referrerPolicy="strict-origin-when-cross-origin"
      src={imgSrc}
      onError={() => {
        if (imgSrc === src) {
          setImgSrc(buildImageProxyUrl(src));
        }
      }}
    />
  );
}
