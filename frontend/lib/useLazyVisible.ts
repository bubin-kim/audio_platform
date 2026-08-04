"use client";

import { useEffect, useRef, useState } from "react";

/**
 * 뷰포트에 들어올 때만 true가 되는 훅 — 파형·스펙트로그램처럼 세그먼트마다
 * 1개씩 붙는 미니 시각화가 테이블 마운트 즉시 전부 fetch되는 것을 막는다.
 *
 * 실사고(2026-08-04): 세그먼트 37개 × (파형+스펙트럼) = 74개 요청이 페이지
 * 로드와 동시에 나가 DB 커넥션 풀(5+10)이 고갈 → TimeoutError로 절반 가까이
 * 실패("파형 없음"/"스펙트럼 없음"). 뷰포트 진입 시에만 요청해 동시 요청 수를
 * 실제로 화면에 보이는 행 수준으로 낮춘다.
 */
export function useLazyVisible<T extends Element>(): [React.RefObject<T | null>, boolean] {
  const ref = useRef<T>(null);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    if (visible || !ref.current) return;
    const el = ref.current;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setVisible(true);
          observer.disconnect();
        }
      },
      { rootMargin: "200px" }, // 스크롤 전에 미리 로드 시작
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, [visible]);

  return [ref, visible];
}
