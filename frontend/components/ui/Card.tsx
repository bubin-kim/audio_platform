export function Card({
  children,
  className = "",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  // className이 자체 bg-* 토큰을 지정하면 기본 배경(bg-surface-card)은 빼서
  // 유틸리티 클래스 두 개가 배경을 두고 충돌하지 않게 한다.
  const bg = className.includes("bg-") ? "" : "bg-surface-card";
  return (
    <div className={`rounded-lg border border-border p-6 ${bg} ${className}`}>
      {children}
    </div>
  );
}
