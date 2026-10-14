export function DoNotBookBlock({ items }: { items: string[] }) {
  return (
    <ul className="list-disc space-y-1 rounded-md border border-destructive/40 bg-destructive/5 py-2 pr-3 pl-6 text-[13px] leading-relaxed text-destructive">
      {items.map((item) => (
        <li key={item}>{item}</li>
      ))}
    </ul>
  )
}
