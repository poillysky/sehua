import { getTranslations } from "next-intl/server";

export default async function NotFound() {
  const t = await getTranslations("ERROR_MESSAGE");

  return (
    <div className="flex flex-col justify-center mx-auto w-4/5 pb-[10vh] max-w-lg h-full">
      <h1 className="mb-4 text-[60px] md:text-[100px] leading-tight font-medium text-foreground">
        404
      </h1>

      <div className="flex flex-col gap-y-1 w-full mb-6 break-words text-sm md:text-lg text-default-600">
        {t("NOT_FOUND")}
      </div>

      <a
        className="mr-auto rounded-full bg-primary px-5 py-2.5 font-medium text-primary-foreground shadow-soft transition-opacity duration-200 hover:opacity-90"
        href="/"
      >
        {t("GoHome")}
      </a>
    </div>
  );
}
