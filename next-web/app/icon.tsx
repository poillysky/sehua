import { renderAppIcon } from "@/lib/appIcon";

export const runtime = "edge";

export function generateImageMetadata() {
  return [
    {
      contentType: "image/png",
      size: { width: 32, height: 32 },
      id: "favicon",
    },
    {
      contentType: "image/png",
      size: { width: 192, height: 192 },
      id: "192",
    },
    {
      contentType: "image/png",
      size: { width: 512, height: 512 },
      id: "512",
    },
  ];
}

export default function Icon({ id }: { id: string }) {
  const size = id === "512" ? 512 : id === "192" ? 192 : 32;

  return renderAppIcon(size);
}
