import { base64ToHex } from "@/utils";
import { resourceByHash } from "@/app/api/graphql/service";
import { isResourceHash } from "@/utils/resource";

export const fail = (message: string, status: number = 500) => {
  return Response.json(
    {
      message,
      status,
    },
    {
      status,
      headers: {
        "Content-Type": "application/json; charset=utf-8",
      },
    },
  );
};

export const success = (data: unknown) => {
  return Response.json(
    {
      data,
      message: "success",
      status: 200,
    },
    {
      status: 200,
      headers: {
        "Content-Type": "application/json; charset=utf-8",
      },
    },
  );
};

export async function getPreviewInfo(hash64: string) {
  const hash = base64ToHex(hash64);

  // 支持 ed2k 32 位 / 磁力 infohash 40 位
  if (!isResourceHash(hash)) {
    throw new Error("Invalid hash");
  }

  const resource = await resourceByHash(null, { hash: hash.toUpperCase() });

  if (!resource) {
    throw new Error("Resource not found");
  }

  return {
    name: resource.name,
    size: resource.size,
    screenshots: (resource.preview_images || []).map((url) => ({
      screenshot: url,
    })),
  };
}
