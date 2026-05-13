/**
 * Consistent page-top header in the Tavily style:
 *   tiny uppercase label  →  large bold title  →  optional muted subtitle
 *
 * Use on every top-level page so the visual rhythm stays uniform.
 */
export function PageHeader({
  label,
  title,
  description,
  action,
}: {
  label?: string;
  title: string;
  description?: string;
  action?: React.ReactNode;
}) {
  return (
    <header className="flex flex-wrap items-start justify-between gap-4 mb-2">
      <div className="max-w-3xl">
        {label ? <div className="label-micro mb-1.5">{label}</div> : null}
        <h1 className="text-3xl sm:text-4xl font-semibold tracking-tight leading-tight">
          {title}
        </h1>
        {description ? (
          <p className="text-sm sm:text-[15px] text-[var(--color-muted)] mt-2.5 leading-relaxed">
            {description}
          </p>
        ) : null}
      </div>
      {action ? <div className="shrink-0">{action}</div> : null}
    </header>
  );
}
