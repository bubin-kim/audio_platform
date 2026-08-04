import type { Config } from "tailwindcss";

/**
 * Grayish-Blue 미니멀 테마 토큰.
 * 컴포넌트는 색을 하드코딩하지 않고 여기 정의된 토큰만 쓴다(CLAUDE.md §4, 03 §2).
 * 색을 바꾸려면 이 파일만 고친다.
 */
const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // 회청색(Grayish-Blue) 스케일 — 배경·테두리·텍스트 위계
        surface: {
          DEFAULT: "#f6fafc", // 페이지 배경
          card: "#ffffff",     // 카드 배경
          muted: "#eaf3f8",    // 옅은 구역
        },
        border: {
          DEFAULT: "#d5e5ee",
        },
        content: {
          DEFAULT: "#2a3441", // 본문 텍스트
          muted: "#5b6b7d",   // 보조 텍스트
          subtle: "#8a99a8",  // 라벨/캡션
        },
        // 강조색 (회청 톤의 blue)
        accent: {
          DEFAULT: "#6b93c4",
          hover: "#5a82b3",
          soft: "#e7f0f9",
        },
        // 상태색 (Job/진행률용)
        status: {
          ok: "#4d9c77",
          warn: "#c39344",
          error: "#c96a58",
        },
        // 스펙트로그램 순차 램프 — viridis (보라→청록→노랑, 오디오 분야 표준).
        // 저에너지=어두운 보라, 고에너지=밝은 노랑이라 이벤트가 눈에 튄다(docs/16).
        // 지각적으로 균일하고 색맹 안전성이 검증된 팔레트. 캔버스는 CSS 클래스를
        // 못 쓰므로 Spectrogram.tsx가 이 값을 직접 import한다.
        spectro: {
          0: "#440154",
          1: "#414487",
          2: "#2a788e",
          3: "#22a884",
          4: "#7ad151",
          5: "#fde725",
        },
        // 대시보드 KPI 카드 등, 카드별로 구분이 필요할 때 순서대로 돌려 쓰는 톤 팔레트.
        chip: {
          1: "#D1EAF0",
          2: "#BCD4E6",
          3: "#9DB8C6",
          4: "#AFDBF5",
        },
      },
    },
  },
  plugins: [],
};

export default config;
