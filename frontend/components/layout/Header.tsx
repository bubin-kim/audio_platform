export function Header({ title }: { title: string }) {
  return (
    <header className="border-b border-border bg-surface-card px-8 py-4">
      <h1 className="text-lg font-semibold text-content">{title}</h1>
    </header>
  );
}
