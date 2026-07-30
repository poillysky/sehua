export default function BoardLoading() {
  return (
    <div className="mx-auto w-full max-w-6xl animate-pulse px-3 py-6 md:px-4 lg:max-w-7xl">
      <div className="mb-4 h-8 w-40 rounded-lg bg-default-200/70 dark:bg-slate-800" />
      <div className="space-y-4">
        {Array.from({ length: 3 }).map((_, i) => (
          <div
            key={i}
            className="rounded-2xl border border-default-200/60 p-4 dark:border-slate-700/60"
          >
            <div className="mb-3 h-5 w-1/3 rounded bg-default-200/70 dark:bg-slate-800" />
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5">
              {Array.from({ length: 5 }).map((__, j) => (
                <div
                  key={j}
                  className="h-[4.5rem] rounded-xl bg-default-100 dark:bg-slate-800/80"
                />
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
