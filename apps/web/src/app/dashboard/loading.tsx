// Shown while a dashboard page reads Supabase. Same grid as PageIntro / Section, so nothing jumps when it arrives.
export default function DashboardLoading() {
  return (
    <div role="status" className="animate-pulse">
      <span className="sr-only">Loading</span>
      <div className="grid gap-x-8 gap-y-3 lg:grid-cols-12" aria-hidden="true">
        <div className="h-3 w-20 rounded-[2px] bg-rule lg:col-span-3 lg:mt-3" />
        <div className="lg:col-span-9">
          <div className="h-3 w-40 rounded-[2px] bg-rule/70" />
          <div className="mt-4 h-9 w-2/3 max-w-md rounded-[3px] bg-rule" />
          <div className="mt-4 h-3 w-1/2 max-w-xs rounded-[2px] bg-rule/70" />
        </div>
      </div>
      <div className="mt-14 grid gap-x-8 gap-y-4 lg:grid-cols-12" aria-hidden="true">
        <div className="h-5 w-32 rounded-[2px] bg-rule lg:col-span-3" />
        <div className="border-t border-ink/30 lg:col-span-9">
          {[0, 1, 2].map((i) => (
            <div key={i} className="flex items-center justify-between border-b border-rule py-5">
              <div className="h-3 w-1/3 rounded-[2px] bg-rule" />
              <div className="h-3 w-20 rounded-[2px] bg-rule/70" />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
